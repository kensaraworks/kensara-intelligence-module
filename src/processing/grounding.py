"""Primary-source grounding (#3).

For a news-sourced candidate, run ONE targeted search for the official notice on
a regulator domain. If found, we attach the official URL and raise confidence to
'high' (making it eligible for auto-publish). One query per candidate keeps the
Serper/Tavily spend bounded (guardrail).
"""
from __future__ import annotations

import structlog

from src.config import TRUSTED_SOURCE_DOMAINS, settings
from src.ingestion import search_sweep

log = structlog.get_logger(__name__)

# Authority → the official domain(s) most likely to carry the order.
_AUTHORITY_DOMAIN = {
    "Data Protection Board of India": ["meity.gov.in", "pib.gov.in"],
    "MeitY": ["meity.gov.in", "egazette.gov.in", "pib.gov.in"],
    "CERT-In": ["cert-in.org.in"],
    "Reserve Bank of India": ["rbi.org.in"],
    "Competition Commission of India": ["cci.gov.in"],
    "IRDAI": ["irdai.gov.in"],
    "SEBI": ["sebi.gov.in"],
    "High Court / Supreme Court": ["sci.gov.in", "indiankanoon.org"],
}


def is_trusted(url: str) -> bool:
    return any(d in (url or "") for d in TRUSTED_SOURCE_DOMAINS)


async def find_official_source(company: str, authority: str, keywords: str = "") -> str | None:
    """Return an official-source URL corroborating the case, or None."""
    if not settings.grounding_enabled or not settings.has_search:
        return None
    domains = _AUTHORITY_DOMAIN.get(authority)
    site_clause = (
        " OR ".join(f"site:{d}" for d in domains) if domains
        else " OR ".join(f"site:{d}" for d in TRUSTED_SOURCE_DOMAINS[:6])
    )
    company_term = company if company and "review" not in company.lower() else ""
    query = f"({site_clause}) {company_term} {keywords}".strip()
    try:
        results = await search_sweep.search(query, num=5)
    except Exception as exc:
        log.warning("grounding.search_failed", error=str(exc))
        return None
    for r in results:
        if is_trusted(r.url):
            log.info("grounding.official_found", authority=authority, url=r.url)
            return r.url
    return None
