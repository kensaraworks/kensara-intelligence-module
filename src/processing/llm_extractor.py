"""LLM structured entity extractor for enforcement actions.

Provider-agnostic: tries the configured/free provider first (Groq → Gemini →
OpenAI). Every provider is asked for strict JSON matching ``ExtractedEnforcement``.
Claude is intentionally NOT wired in (reserved per project constraints).

If no LLM key is available the extractor returns a *heuristic* extraction so the
pipeline still surfaces candidates for human review — just with lower confidence.
"""
from __future__ import annotations

import json
import re

import structlog
from pydantic import BaseModel, Field, ValidationError

from src.config import settings
from src.processing.scoring import classify_sector

log = structlog.get_logger(__name__)


class ExtractedEnforcement(BaseModel):
    is_genuine_enforcement: bool = Field(
        description="True ONLY for a real regulatory order, fine, penalty, inquiry or court "
        "ruling. False for advisory, opinion, or generic commentary."
    )
    authority: str = Field(default="Unknown")
    company: str = Field(default="Industry-wide")
    sector: str = Field(default="Other")
    violation_type: str = Field(default="")
    dpdpa_section: str = Field(default="")
    penalty_amount: str = Field(default="")
    penalty_inr_numeric: float = Field(default=0.0)
    outcome: str = Field(default="Investigation Ongoing")
    executive_summary: str = Field(default="")
    confidence_score: str = Field(default="medium")


_SYSTEM = (
    "You are a senior Indian regulatory-compliance attorney specialising in DPDPA, "
    "CERT-In and IT Act enforcement. Extract structured enforcement data from the "
    "article. If it is merely opinion, an educational guide, or generic discussion "
    "with no actual enforcement action, set is_genuine_enforcement to false."
)

_SCHEMA_HINT = """Respond with ONLY a valid JSON object with these keys:
{
 "is_genuine_enforcement": boolean,
 "authority": one of ["Data Protection Board of India","CERT-In","MeitY","Reserve Bank of India","Competition Commission of India","IRDAI","SEBI","High Court / Supreme Court","Unknown"],
 "company": string,
 "sector": one of ["Fintech","Social Media / Tech","Healthcare","Government","Other"],
 "violation_type": short string,
 "dpdpa_section": string e.g. "DPDPA Section 8(6)" / "IT Act Section 43A" / "CERT-In 2022 Direction",
 "penalty_amount": string e.g. "₹25 Lakh" / "₹10 Crore" / "No financial penalty (Warning/Order)",
 "penalty_inr_numeric": number in INR (0 if none),
 "outcome": one of ["Fine Imposed","Investigation Ongoing","Compliance Achieved","Business Ban / Restriction","Adjudication Order Issued"],
 "executive_summary": objective 2-sentence summary,
 "confidence_score": one of ["high","medium","low"]
}"""


def _prompt(title: str, content: str, url: str, few_shot: str = "") -> str:
    return (
        f"{_SYSTEM}{few_shot}\n\nArticle Title: {title}\nSource URL: {url}\n"
        f"Article Content:\n{content}\n\n{_SCHEMA_HINT}"
    )


def _parse(raw: str) -> ExtractedEnforcement | None:
    raw = raw.strip()
    # Strip markdown fences / prose around the JSON if the model added any.
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return ExtractedEnforcement(**data)
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("llm.parse_failed", error=str(exc))
        return None


# ── Provider calls ─────────────────────────────────────────────────────────
async def _via_groq(prompt: str) -> str | None:
    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        candidates = [settings.groq_model]
        for fb in ["llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
            if fb not in candidates:
                candidates.append(fb)

        last_exc = None
        for model_name in candidates:
            try:
                resp = await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                return resp.choices[0].message.content
            except Exception as e:
                last_exc = e
                continue
        if last_exc:
            log.warning("llm.groq_failed", error=str(last_exc))
        return None
    except Exception as exc:
        log.warning("llm.groq_failed", error=str(exc))
        return None


async def _via_gemini(prompt: str) -> str | None:
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        candidates = [settings.gemini_model]
        for fb in ["gemini-2.5-flash", "gemini-1.5-flash"]:
            if fb not in candidates:
                candidates.append(fb)

        last_exc = None
        for model_name in candidates:
            try:
                model = genai.GenerativeModel(model_name)
                resp = await model.generate_content_async(
                    prompt,
                    generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
                )
                return resp.text
            except Exception as e:
                last_exc = e
                continue
        if last_exc:
            log.warning("llm.gemini_failed", error=str(last_exc))
        return None
    except Exception as exc:
        log.warning("llm.gemini_failed", error=str(exc))
        return None


async def _via_openai(prompt: str) -> str | None:
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        log.warning("llm.openai_failed", error=str(exc))
        return None


_PROVIDERS = {"groq": _via_groq, "gemini": _via_gemini, "openai": _via_openai}
_ORDER = ["groq", "gemini", "openai"]


async def extract_enforcement(
    title: str, snippet: str, url: str, *, full_text: str = "", few_shot: str = "",
    diag: dict | None = None,
) -> ExtractedEnforcement | None:
    """Run extraction. Returns None for non-enforcement or on total failure.

    ``full_text`` (from fetch_article_text, #1) is preferred over the snippet;
    ``few_shot`` (from ReviewMemory, #4) conditions the model to the reviewer's bar.

    ``diag`` (optional) is filled with why this returned what it did — which
    provider answered, whether the JSON parsed, and the model's own
    is_genuine_enforcement verdict. Returning None for "not enforcement" and
    None for "everything failed" are very different outcomes, and the
    inspection lab has to be able to tell them apart.
    """
    if diag is not None:
        diag.update(provider=None, parsed=False, is_genuine=None,
                    heuristic_used=False, content_chars=len(full_text or snippet),
                    used_full_text=bool(full_text), outcome="no_provider")
    provider = settings.resolved_llm_provider()
    content = full_text or snippet
    prompt = _prompt(title, content, url, few_shot)

    # Try preferred provider, then the rest in free-first order.
    tried: list[str] = []
    order = ([provider] if provider else []) + [p for p in _ORDER if p != provider]
    for name in order:
        if name in tried or not getattr(settings, f"{name}_api_key"):
            continue
        tried.append(name)
        raw = await _PROVIDERS[name](prompt)
        if raw:
            parsed = _parse(raw)
            if diag is not None:
                diag.update(provider=name, parsed=bool(parsed))
            if parsed:
                if diag is not None:
                    diag.update(is_genuine=parsed.is_genuine_enforcement,
                                fields=parsed.model_dump(),
                                outcome=("extracted" if parsed.is_genuine_enforcement
                                         else "rejected_not_enforcement"))
                log.info("llm.extracted", provider=name, company=parsed.company)
                return parsed if parsed.is_genuine_enforcement else None

    # No LLM available/worked → heuristic fallback keeps a review lead alive.
    fallback = _heuristic(title, content)
    if diag is not None:
        diag.update(heuristic_used=True, is_genuine=fallback is not None,
                    fields=(fallback.model_dump() if fallback else None),
                    outcome=("heuristic_extracted" if fallback
                             else "heuristic_rejected"))
    return fallback


_SIGNAL_RE = re.compile(
    r"\b(?:penalty|penalti(?:es|se|ze)d?|fine[ds]?|fined|order(?:ed|s)?|ban(?:ned|s)?|"
    r"adjudicat\w*|investigat\w*|notice|direct(?:s|ed|ion)?|imposed|prosecut\w*|"
    r"restrict\w*|barred)\b"
)
_MONEY_HEUR_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s?[\d,]+(?:\.\d+)?\s?(?:lakh|crore|cr|million|bn|billion)?"
    r"|[\d,]+(?:\.\d+)?\s?(?:lakh|crore|million|billion)",
    re.IGNORECASE,
)


def _heuristic(title: str, snippet: str) -> ExtractedEnforcement | None:
    text = f"{title} {snippet}".lower()
    if not _SIGNAL_RE.search(text):
        return None
    money = _MONEY_HEUR_RE.search(f"{title} {snippet}")
    return ExtractedEnforcement(
        is_genuine_enforcement=True,
        authority="Unknown",
        company="[Needs review — see source]",
        sector=classify_sector(text),
        violation_type="[Auto-flagged — verify]",
        penalty_amount=(money.group(0).strip() if money else ""),
        outcome="Investigation Ongoing",
        executive_summary=f"AUTO-DETECTED: {title}. Snippet: {snippet[:280]}",
        confidence_score="low",
    )
