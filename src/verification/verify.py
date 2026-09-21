"""Verification orchestrator → trust tier.

    candidate → find official document → FETCH it → match entity+amount
              → corroboration count → trust tier + evidence

Replaces Phase 2's naive grounding, which only checked whether a URL sat on a
government domain without ever opening it.

Trust tiers (see docs/ARCHITECTURE_V2.md §2.4):
    primary_confirmed  official document fetched AND entity + amount matched
    press_reported     named sources only; independent-domain count recorded
    ai_detected        never published

Best-effort: a verification failure downgrades the tier, it never breaks a run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

import structlog

from src.processing.fulltext import fetch_article_text
from src.processing.grounding import find_official_source, is_trusted
from src.publish.model import TIER_AI, TIER_PRESS, TIER_PRIMARY
from src.verification.archive import MAX_ARCHIVES_PER_RUN, Evidence, build_evidence
from src.verification.matcher import MatchResult, match_document

log = structlog.get_logger(__name__)


def registrable_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in ("co", "com", "gov", "org", "net", "ac"):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def independent_source_count(urls: list[str]) -> int:
    """Five links from one outlet are not five sources."""
    return len({d for d in (registrable_domain(u) for u in urls) if d})


@dataclass
class VerificationResult:
    trust_tier: str = TIER_AI
    official_url: str = ""
    match: MatchResult | None = None
    evidence: Evidence | None = None
    independent_sources: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "trust_tier": self.trust_tier,
            "official_url": self.official_url,
            "verified": bool(self.match and self.match.verified),
            "strength": self.match.strength if self.match else "none",
            "independent_sources": self.independent_sources,
            "archived_url": self.evidence.archived_url if self.evidence else "",
            "excerpt": (self.evidence.excerpt if self.evidence else "")[:400],
            "reasons": self.match.reasons if self.match else self.notes,
        }


class Verifier:
    """Stateful across a run so archival stays capped."""

    def __init__(self, archive: bool = True) -> None:
        self.archive = archive
        self._archived = 0

    async def verify(self, *, company: str, authority: str, penalty: str = "",
                     date: str = "", source_urls: list[str] | None = None,
                     violation: str = "") -> VerificationResult:
        source_urls = [u for u in (source_urls or []) if u]
        res = VerificationResult()
        res.independent_sources = independent_source_count(source_urls)

        # 1. Locate a candidate official document.
        official = next((u for u in source_urls if is_trusted(u)), "")
        if not official:
            official = await find_official_source(company, authority,
                                                  keywords=violation) or ""
        if not official:
            res.trust_tier = TIER_PRESS if source_urls else TIER_AI
            res.notes.append("no_official_source_found")
            return res
        res.official_url = official

        # 2. ACTUALLY OPEN IT. This is the step Phase 2 skipped.
        text = await fetch_article_text(official, fallback="")
        if not text:
            res.trust_tier = TIER_PRESS if source_urls else TIER_AI
            res.notes.append("official_source_unreachable")
            return res

        # 3. Does the document support the claim?
        match = match_document(text, company=company, penalty=penalty, date=date)
        res.match = match

        if match.verified:
            res.trust_tier = TIER_PRIMARY
            do_archive = self.archive and self._archived < MAX_ARCHIVES_PER_RUN
            res.evidence = build_evidence(official, text, match.excerpt,
                                          archive=do_archive)
            if do_archive and res.evidence.archived_url:
                self._archived += 1
            log.info("verify.confirmed", company=company, strength=match.strength,
                     amount=match.matched_amount or None)
        else:
            # Found an official page but it does not substantiate the claim —
            # that is a downgrade, not a promotion.
            res.trust_tier = TIER_PRESS if source_urls else TIER_AI
            log.info("verify.not_substantiated", company=company,
                     reasons=match.reasons)
        return res


async def verify_candidate(row: dict, verifier: Verifier | None = None) -> VerificationResult:
    """Convenience wrapper for an enforcement candidate row."""
    v = verifier or Verifier()
    urls = [row.get("source_url", "")] + [
        s.get("url", "") for s in (row.get("sources") or []) if isinstance(s, dict)]
    if row.get("official_source_url"):
        urls.insert(0, row["official_source_url"])
    return await v.verify(
        company=row.get("company", ""), authority=row.get("authority", ""),
        penalty=row.get("penalty_amount", ""), date=row.get("date", ""),
        source_urls=urls, violation=row.get("violation_type", ""))
