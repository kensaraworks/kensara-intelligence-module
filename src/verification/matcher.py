"""Does this document actually support the claim?

Phase 2's "grounding" only asked whether a URL sat on a government domain. That
is domain-matching, not verification: it never opened the document. This module
opens it and checks that the claimed entity and amount are genuinely present.

Deterministic and explainable — every verdict carries the reasons and the
matched excerpt, which is what makes an entry defensible if challenged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.graph.entities import normalize
from src.verification.amounts import Amount, contains_amount, parse_amount

# Tokens too generic to prove an entity match on their own.
_WEAK_TOKENS = {
    "india", "indian", "limited", "ltd", "private", "pvt", "company", "corp",
    "services", "technologies", "solutions", "bank", "finance", "financial",
    "insurance", "data", "digital", "group", "holdings", "international",
}


@dataclass
class MatchResult:
    entity_matched: bool = False
    amount_matched: bool = False
    date_matched: bool = False
    excerpt: str = ""
    matched_amount: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        """An entity match alone is not proof — a regulator page may merely
        mention a company. We require the entity AND a corroborating fact."""
        return self.entity_matched and (self.amount_matched or self.date_matched)

    @property
    def strength(self) -> str:
        if self.entity_matched and self.amount_matched:
            return "strong"
        if self.verified:
            return "moderate"
        return "weak"


def _entity_tokens(name: str) -> list[str]:
    toks = [t for t in normalize(name).split() if len(t) > 2 and t not in _WEAK_TOKENS]
    return toks


def entity_in_text(name: str, text: str) -> bool:
    """Distinctive tokens of the entity name must appear in the document."""
    toks = _entity_tokens(name)
    if not toks:
        return False
    low = text.lower()
    hits = sum(1 for t in toks if re.search(rf"\b{re.escape(t)}", low))
    # One distinctive token is enough for a single-word brand ("Mastercard"),
    # otherwise require the majority to appear.
    return hits >= 1 if len(toks) == 1 else hits >= max(2, (len(toks) + 1) // 2)


def _excerpt_around(text: str, needle: str, width: int = 260) -> str:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - width // 2)
    return " ".join(text[start:start + width].split())


def match_document(document_text: str, *, company: str, penalty: str = "",
                   date: str = "") -> MatchResult:
    """Check a fetched official document against the claimed facts."""
    res = MatchResult()
    if not document_text or len(document_text) < 100:
        res.reasons.append("document_empty_or_too_short")
        return res

    text = document_text

    if entity_in_text(company, text):
        res.entity_matched = True
        res.reasons.append("entity_found")
        toks = _entity_tokens(company)
        if toks:
            res.excerpt = _excerpt_around(text, toks[0])
    else:
        res.reasons.append("entity_not_found")

    target: Amount | None = parse_amount(penalty) if penalty else None
    if target:
        found = contains_amount(text, target)
        if found:
            res.amount_matched = True
            res.matched_amount = found.raw
            res.reasons.append(f"amount_matched:{found.raw}")
            better = _excerpt_around(text, found.raw)
            if better:
                res.excerpt = better
        else:
            res.reasons.append("amount_not_found")
    elif penalty:
        res.reasons.append("penalty_not_numeric")

    if date and len(date) >= 10:
        y, m, d = date[:4], date[5:7], date[8:10]
        patterns = [date, f"{d}/{m}/{y}", f"{d}-{m}-{y}", f"{d}.{m}.{y}"]
        try:
            import datetime as _dt
            dt = _dt.date(int(y), int(m), int(d))
            patterns += [dt.strftime("%d %B %Y"), dt.strftime("%B %d, %Y"),
                         dt.strftime("%d %b %Y")]
        except Exception:
            pass
        if any(p.lower() in text.lower() for p in patterns if p):
            res.date_matched = True
            res.reasons.append("date_matched")

    return res
