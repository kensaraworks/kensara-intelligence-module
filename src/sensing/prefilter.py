"""Deterministic pre-filter — runs before any LLM call.

Guardrail #2 from the architecture: *never send a document to an LLM that a
cheap filter can reject*. High-recall sensing means far more documents, so this
gate is what keeps the free tiers comfortable while coverage grows.

Pure string work: no network, no model, no cost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A document must show at least one topical anchor to be worth any further spend.
TOPIC_ANCHORS = (
    "dpdp", "data protection", "personal data", "privacy", "data breach",
    "cert-in", "cert in", "data fiduciary", "data principal", "consent manager",
    "data localisation", "data localization", "gdpr", "cyber security",
    "cybersecurity", "information technology act", "it act", "aadhaar",
    "surveillance", "data leak", "breach notification", "dsar",
)

# Signals that this is an ACTION, not commentary — used for ranking, not rejection.
ACTION_SIGNALS = re.compile(
    r"\b(?:penal(?:ty|ise|ize|ised|ized)|fine[ds]?|fined|order(?:ed|s)?|"
    r"direct(?:ed|ion|ions)?|notice|ban(?:ned)?|barred|restrict\w*|"
    r"adjudicat\w*|investigat\w*|prosecut\w*|judgment|ruling|verdict|"
    r"notifi(?:ed|cation)|circular|advisory|breach|leak(?:ed)?)\b", re.I)

# Obvious non-events: marketing, listicles, events, jobs.
NOISE = re.compile(
    r"\b(?:webinar|conference|summit|workshop|hiring|job|internship|"
    r"sponsored|advertorial|coupon|discount|horoscope|cricket|box office|"
    r"how to|top \d+|best \d+|listicle)\b", re.I)

# Business-as-usual corporate news. It carries money figures and India hints, so
# without an explicit reject it scores well and crowds out real enforcement.
CORPORATE_NOISE = re.compile(
    r"\b(?:seed round|series [a-f]\b|funding|raises|raised|valuation|ipo|"
    r"acquires|acquisition|merger|appoints|appointment|resigns|steps down|"
    r"quarterly results|q[1-4] results|revenue|profit|share price|"
    r"launches|unveils|partners with|partnership)\b", re.I)

# Regulator feeds carry high volumes of routine business unrelated to data
# protection (RBI alone publishes these daily). Rejected even from a primary
# source unless the title itself is on-topic.
OFF_TOPIC_REGULATORY = re.compile(
    r"\b(?:priority sector lending|cash reserve ratio|statutory liquidity|"
    r"foreign exchange management|fema|know your customer|kyc|"
    r"monetary policy|repo rate|interest rate|liquidity adjustment|"
    r"government securities|treasury bill|banking ombudsman|"
    r"co-operative bank|basel|capital adequacy|inflation|gdp|msme credit|"
    r"prompt corrective action|deposit insurance)\b", re.I)

INDIA_HINTS = ("india", "indian", "rbi", "meity", "cert-in", "sebi", "irdai",
               "cci", "trai", "uidai", "delhi", "mumbai", "bengaluru", "supreme court")


@dataclass
class FilterVerdict:
    keep: bool
    reason: str
    priority: int = 0      # cheap ranking so the cap keeps the best candidates


def evaluate(title: str, summary: str = "", source: str = "",
             is_primary_source: bool = False,
             always_relevant: bool = False) -> FilterVerdict:
    text = f"{title} {summary}".lower()
    if not title.strip():
        return FilterVerdict(False, "empty_title")

    if NOISE.search(text):
        return FilterVerdict(False, "noise_pattern")

    anchored = any(a in text for a in TOPIC_ANCHORS)
    title_anchored = any(a in title.lower() for a in TOPIC_ANCHORS)

    # Routine regulatory business is rejected even from a primary source.
    if OFF_TOPIC_REGULATORY.search(text) and not title_anchored:
        return FilterVerdict(False, "off_topic_regulatory")

    # Corporate news scores deceptively well (money + India), so reject it
    # unless the topic anchor is in the TITLE (a real breach/penalty story).
    if CORPORATE_NOISE.search(text) and not title_anchored:
        return FilterVerdict(False, "corporate_noise")

    # `always_relevant` sources (CERT-In advisories, MeitY notifications) are
    # narrow enough that everything they publish is in scope. Broad regulator
    # feeds like RBI's are NOT — they must still show a topic anchor, otherwise
    # hundreds of banking circulars flood the queue.
    if not anchored and not always_relevant:
        return FilterVerdict(False, "no_topic_anchor")

    priority = 0
    if is_primary_source:
        priority += 5
    if anchored:
        priority += 2
    if ACTION_SIGNALS.search(text):
        priority += 3
    if any(h in text or h in source.lower() for h in INDIA_HINTS):
        priority += 2
    if re.search(r"(?:₹|rs\.?|inr)\s?[\d,]+|crore|lakh|million|billion", text):
        priority += 2

    return FilterVerdict(True, "kept", priority)


def filter_items(items: list, primary_domains: set[str] | None = None,
                 always_relevant_domains: set[str] | None = None,
                 trace: list | None = None) -> tuple[list, dict]:
    """Return (kept_items_sorted_by_priority, rejection_stats).

    Pass ``trace`` to collect a per-item verdict for the inspection lab — every
    item, kept or rejected, with the reason. Opaque filtering is unauditable.
    """
    primary_domains = primary_domains or set()
    always_relevant_domains = always_relevant_domains or set()
    kept, stats = [], {}
    for it in items:
        haystack = f"{it.source or ''} {it.url or ''}"
        is_primary = any(d in haystack for d in primary_domains)
        always = any(d in haystack for d in always_relevant_domains)
        v = evaluate(it.title, it.summary, it.source, is_primary, always)
        if trace is not None:
            trace.append({
                "title": it.title, "url": it.url, "source": it.source,
                "kept": v.keep, "reason": v.reason, "priority": v.priority,
                "is_primary_source": is_primary, "always_relevant": always,
            })
        if v.keep:
            kept.append((v.priority, it))
        else:
            stats[v.reason] = stats.get(v.reason, 0) + 1
    kept.sort(key=lambda t: t[0], reverse=True)
    return [it for _, it in kept], stats
