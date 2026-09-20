"""Generic free-form text completion across free-first providers.

Separate from llm_extractor (which is JSON-mode). Used by the weekly brief (#6),
content angles (#9) and re-verification (#7). Returns "" if no provider works —
callers fall back to a template so nothing crashes without keys.
"""
from __future__ import annotations

import structlog

from src.config import settings

log = structlog.get_logger(__name__)


async def _groq(prompt: str, max_tokens: int) -> str | None:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    candidates = [settings.groq_model]
    for fb in ["llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
        if fb not in candidates:
            candidates.append(fb)

    for m in candidates:
        try:
            r = await client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=max_tokens,
            )
            return r.choices[0].message.content
        except Exception:
            continue
    return None


async def _gemini(prompt: str, max_tokens: int) -> str | None:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    candidates = [settings.gemini_model]
    for fb in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        if fb not in candidates:
            candidates.append(fb)

    for m in candidates:
        try:
            model = genai.GenerativeModel(m)
            r = await model.generate_content_async(
                prompt, generation_config={"temperature": 0.3, "max_output_tokens": max_tokens})
            return r.text
        except Exception:
            continue
    return None


async def _openai(prompt: str, max_tokens: int) -> str | None:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    r = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3, max_tokens=max_tokens,
    )
    return r.choices[0].message.content


_FNS = {"groq": _groq, "gemini": _gemini, "openai": _openai}
_ORDER = ["groq", "gemini", "openai"]


async def complete_text(prompt: str, max_tokens: int = 900) -> str:
    provider = settings.resolved_llm_provider()
    order = ([provider] if provider else []) + [p for p in _ORDER if p != provider]
    for name in order:
        if not getattr(settings, f"{name}_api_key"):
            continue
        try:
            out = await _FNS[name](prompt, max_tokens)
            if out:
                return out.strip()
        except Exception as exc:
            log.warning("llm.text_failed", provider=name, error=str(exc))
    return ""
