"""Declarative source registry — the sensing net (Phase 2).

Sources are DATA, not code, so widening coverage is a one-line change and the
admin can report health per source.

Three sensor types, cheapest first:
  • ``rss``      — a real feed. Free.
  • ``docwatch`` — fetch a listing page and diff its links against what we have
                   already seen. New link = new document. Free, no keywords, and
                   the highest-signal sensor for regulators that publish orders
                   without a feed.
  • ``gnews``    — Google News RSS (``news.google.com/rss/search``). Free, keyless,
                   and covers essentially all Indian press. This is what lets us
                   stop spending paid-search credits on *discovery*.

Every source may carry ``gnews_fallback``: if its feed dies or the site blocks
us, Google News still surfaces its stories via a ``site:`` query. Coverage
therefore degrades gracefully instead of silently going dark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote_plus

# Cadence tiers (relaxed by design — we optimise for completeness, not minutes)
TIER_PRIMARY = 0   # regulators / government — 2-4x daily
TIER_PRESS = 1     # news — daily
TIER_ANALYSIS = 2  # law firms / commentary — every few days
TIER_AUDIT = 3     # deep sweeps, gap audits — weekly


def gnews_rss(query: str, region: str = "IN", lang: str = "en") -> str:
    """Google News RSS. Free, keyless, no quota."""
    return (f"https://news.google.com/rss/search?q={quote_plus(query)}"
            f"&hl={lang}-{region}&gl={region}&ceid={region}:{lang}")


@dataclass
class Source:
    name: str
    kind: str                       # rss | docwatch | gnews
    tier: int
    url: str = ""                   # feed url, listing url, or gnews query
    domain: str = ""
    selector: str = "a[href]"       # docwatch only
    is_primary_source: bool = False  # official/authoritative publisher
    always_relevant: bool = False    # EVERY item from this source is in scope.
                                     # Only for narrow sources (CERT-In advisories).
                                     # Broad feeds (RBI circulars) must still match
                                     # a topic anchor or they flood the queue.
    gnews_fallback: str = ""        # site: query used if the direct sensor fails
    enabled: bool = True

    def resolved_url(self) -> str:
        return gnews_rss(self.url) if self.kind == "gnews" else self.url

    def fallback_url(self) -> str:
        return gnews_rss(self.gnews_fallback) if self.gnews_fallback else ""


# ── Tier 0: primary sources (regulators, government) ──────────────────────
PRIMARY_SOURCES = [
    Source("PIB", "rss", TIER_PRIMARY, "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
           domain="pib.gov.in", is_primary_source=True,
           gnews_fallback="site:pib.gov.in data protection OR privacy OR DPDP"),
    Source("MeitY notifications", "docwatch", TIER_PRIMARY,
           "https://www.meity.gov.in/documents/notification", domain="meity.gov.in",
           is_primary_source=True, always_relevant=True,
           gnews_fallback="site:meity.gov.in DPDP OR data protection"),
    Source("MeitY press", "docwatch", TIER_PRIMARY,
           "https://www.meity.gov.in/whatsnew", domain="meity.gov.in",
           is_primary_source=True,
           gnews_fallback="MeitY data protection OR DPDP OR IT rules"),
    Source("CERT-In advisories", "docwatch", TIER_PRIMARY,
           "https://www.cert-in.org.in/", domain="cert-in.org.in",
           selector="a[href*='PUB'], a[href*='advisory'], a[href*='Directions']",
           is_primary_source=True, always_relevant=True,
           gnews_fallback="CERT-In directions OR advisory India"),
    Source("RBI press releases", "rss", TIER_PRIMARY,
           "https://www.rbi.org.in/pressreleases_rss.xml", domain="rbi.org.in",
           is_primary_source=True,
           gnews_fallback="site:rbi.org.in penalty OR data OR localisation"),
    Source("RBI notifications", "rss", TIER_PRIMARY,
           "https://www.rbi.org.in/notifications_rss.xml", domain="rbi.org.in",
           is_primary_source=True,
           gnews_fallback="RBI data localisation OR cyber OR outsourcing directions"),
    Source("SEBI", "docwatch", TIER_PRIMARY, "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0",
           domain="sebi.gov.in", is_primary_source=True,
           gnews_fallback="SEBI cyber security OR data protection circular"),
    Source("IRDAI", "docwatch", TIER_PRIMARY, "https://irdai.gov.in/circulars",
           domain="irdai.gov.in", is_primary_source=True,
           gnews_fallback="IRDAI data OR cyber OR privacy circular"),
    Source("CCI orders", "docwatch", TIER_PRIMARY, "https://www.cci.gov.in/antitrust/orders",
           domain="cci.gov.in", is_primary_source=True,
           gnews_fallback="CCI order data OR privacy OR dominance India"),
    Source("TRAI", "docwatch", TIER_PRIMARY, "https://www.trai.gov.in/notifications/press-release",
           domain="trai.gov.in", is_primary_source=True,
           gnews_fallback="TRAI data OR privacy OR spam OR consent regulation"),
    Source("UIDAI", "gnews", TIER_PRIMARY, "UIDAI Aadhaar data OR privacy OR breach",
           domain="uidai.gov.in", is_primary_source=True),
    Source("PRS Legislative", "docwatch", TIER_PRIMARY, "https://prsindia.org/billtrack",
           domain="prsindia.org", is_primary_source=True,
           gnews_fallback="site:prsindia.org data protection bill"),
]

# ── Tier 1: press — where India privacy news actually breaks ──────────────
PRESS_SOURCES = [
    Source("MediaNama", "rss", TIER_PRESS, "https://www.medianama.com/feed/",
           domain="medianama.com",
           gnews_fallback="site:medianama.com data protection OR DPDP OR privacy"),
    Source("LiveLaw", "rss", TIER_PRESS, "https://www.livelaw.in/rss.xml",
           domain="livelaw.in",
           gnews_fallback="site:livelaw.in privacy OR data protection judgment"),
    Source("Bar and Bench", "rss", TIER_PRESS, "https://www.barandbench.com/feed",
           domain="barandbench.com",
           gnews_fallback="site:barandbench.com data protection OR privacy"),
    Source("Inc42", "rss", TIER_PRESS, "https://inc42.com/feed/", domain="inc42.com"),
    Source("Entrackr", "rss", TIER_PRESS, "https://entrackr.com/rss", domain="entrackr.com"),
    Source("LiveMint Tech", "rss", TIER_PRESS, "https://www.livemint.com/rss/technology",
           domain="livemint.com"),
    Source("ET Tech", "rss", TIER_PRESS,
           "https://economictimes.indiatimes.com/tech/rssfeeds/13357220.cms",
           domain="economictimes.indiatimes.com",
           gnews_fallback="site:economictimes.indiatimes.com data protection OR DPDPA"),
    Source("YourStory", "rss", TIER_PRESS, "https://yourstory.com/feed", domain="yourstory.com"),
    Source("Business Standard Tech", "gnews", TIER_PRESS,
           "site:business-standard.com data protection OR DPDPA OR privacy",
           domain="business-standard.com"),
    Source("Hindu BusinessLine", "gnews", TIER_PRESS,
           "site:thehindubusinessline.com data protection OR privacy India",
           domain="thehindubusinessline.com"),
    Source("Moneycontrol", "gnews", TIER_PRESS,
           "site:moneycontrol.com data protection OR DPDPA", domain="moneycontrol.com"),
]

# ── Tier 1: broad topical nets (free, keyless, very high recall) ──────────
TOPIC_SOURCES = [
    Source("Topic: DPDPA", "gnews", TIER_PRESS, "DPDPA OR \"Digital Personal Data Protection\" India"),
    Source("Topic: DPDP Rules", "gnews", TIER_PRESS, "\"DPDP Rules\" OR \"Data Protection Board\" India"),
    Source("Topic: data breach India", "gnews", TIER_PRESS, "data breach India company"),
    Source("Topic: CERT-In", "gnews", TIER_PRESS, "CERT-In breach OR directions OR advisory"),
    Source("Topic: RBI data", "gnews", TIER_PRESS, "RBI data localisation OR penalty bank"),
    Source("Topic: privacy penalty", "gnews", TIER_PRESS, "India privacy penalty OR fine regulator"),
    Source("Topic: data privacy judgment", "gnews", TIER_PRESS,
           "India court privacy OR \"personal data\" judgment"),
    Source("Topic: consent manager", "gnews", TIER_PRESS,
           "consent manager OR \"data fiduciary\" India"),
]

# ── Tier 2: analysis / law firms (expert editorial fuel) ──────────────────
ANALYSIS_SOURCES = [
    Source("SpicyIP", "rss", TIER_ANALYSIS, "https://spicyip.com/feed", domain="spicyip.com"),
    Source("IAPP", "gnews", TIER_ANALYSIS, "site:iapp.org India OR DPDPA", domain="iapp.org"),
    Source("Nishith Desai", "gnews", TIER_ANALYSIS,
           "site:nishithdesai.com data protection OR privacy", domain="nishithdesai.com"),
    Source("Trilegal", "gnews", TIER_ANALYSIS,
           "site:trilegal.com data protection OR DPDP", domain="trilegal.com"),
    Source("Khaitan & Co", "gnews", TIER_ANALYSIS,
           "site:khaitanco.com data protection OR privacy", domain="khaitanco.com"),
    Source("Cyril Amarchand", "gnews", TIER_ANALYSIS,
           "site:cyrilshroff.com OR site:corporate.cyrilamarchandblogs.com data protection",
           domain="cyrilamarchandblogs.com"),
    Source("AZB", "gnews", TIER_ANALYSIS, "site:azbpartners.com data protection OR privacy",
           domain="azbpartners.com"),
]

# ── Tier 3: courts / audit ────────────────────────────────────────────────
AUDIT_SOURCES = [
    Source("Indian Kanoon", "gnews", TIER_AUDIT,
           "site:indiankanoon.org \"personal data\" OR privacy judgment",
           domain="indiankanoon.org", is_primary_source=True),
    Source("eGazette", "gnews", TIER_AUDIT, "site:egazette.gov.in data protection",
           domain="egazette.gov.in", is_primary_source=True),
    Source("Parliament Q&A", "gnews", TIER_AUDIT,
           "Lok Sabha OR Rajya Sabha question data breach OR data protection"),
]

ALL_SOURCES: list[Source] = (
    PRIMARY_SOURCES + PRESS_SOURCES + TOPIC_SOURCES + ANALYSIS_SOURCES + AUDIT_SOURCES
)


def sources_for_tier(tier: int | None = None) -> list[Source]:
    return [s for s in ALL_SOURCES if s.enabled and (tier is None or s.tier == tier)]


def sources_upto_tier(tier: int) -> list[Source]:
    return [s for s in ALL_SOURCES if s.enabled and s.tier <= tier]


def stats() -> dict:
    return {
        "total": len(ALL_SOURCES),
        "by_kind": {k: sum(1 for s in ALL_SOURCES if s.kind == k)
                    for k in ("rss", "docwatch", "gnews")},
        "by_tier": {t: sum(1 for s in ALL_SOURCES if s.tier == t) for t in (0, 1, 2, 3)},
        "primary_sources": sum(1 for s in ALL_SOURCES if s.is_primary_source),
        "paid_api_sources": 0,  # discovery is entirely free
    }
