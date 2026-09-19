"""Pure-Python 12-signal relevance scoring engine.

    Final Score = min(20, base) + recency_delta

Ported and hardened from the reference algorithm. No external deps. Also
provides a coarse section classifier used to route enforcement candidates into
the correct front-end tab.
"""
from __future__ import annotations

import re
from datetime import date, datetime

HIGH_KW = [
    "dpdpa", "data protection board", "meity", "personal data protection", "dsar",
    "consent management", "breach notification", "72 hour", "6 hour", "enforcement",
    "penalty", "fine", "data fiduciary", "significant data fiduciary",
]
MED_KW = [
    "gdpr", "ccpa", "ico", "edpb", "data breach", "data localization", "data localisation",
    "cross-border transfer", "right to erasure", "privacy by design",
]
INDIAN_CORPS = [
    "tcs", "infosys", "wipro", "reliance", "jio", "airtel", "hdfc", "icici", "sbi",
    "paytm", "phonepe", "zerodha", "zomato", "swiggy", "flipkart", "cred", "byju",
    "star health", "mastercard", "amex", "american express",
]

_MONEY_RE = re.compile(r"(?:₹|rs\.?|rupees?|\b\d+\s*(?:lakh|crore|million|billion)\b)")
_SECTION_RE = re.compile(r"\b(?:section|sec\.?|rule|clause|article|art\.?)\s+\d+\b")
_SECTION_RULE_RE = re.compile(r"\b(?:section|rule)\s+\d+\b")
_CORP_SUFFIX_RE = re.compile(r"\b[a-z0-9]+\s+(?:pvt\.?\s+ltd\.?|ltd\.?|llp)\b")


def compute_days_old(published_date: str) -> int:
    if not published_date:
        return 30  # unknown → treat as ~month old (neutral)
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            d = datetime.strptime(published_date.strip()[:11].strip(), fmt).date()
            return max(0, (date.today() - d).days)
        except ValueError:
            continue
    return 30


def calculate_relevance_score(
    title: str, summary: str, source: str, published_date: str = ""
) -> int:
    text = f"{title} {summary}".lower()
    source_l = source.lower()
    score = 0

    # 1. High-relevance keywords (+2 each)
    score += 2 * sum(1 for kw in HIGH_KW if kw in text)
    # 2. Medium-relevance keywords (+1 each)
    score += sum(1 for kw in MED_KW if kw in text)
    # 3. India-origin domain (+2)
    if any(s in source_l for s in
           ["meity", "dpbi", "cert-in", "rbi", "yourstory", "inc42", "entrackr"]):
        score += 2
    # 4. Monetary penalty mentioned (+3)
    if _MONEY_RE.search(text):
        score += 3
    # 5. Named Indian enterprise (+2)
    if any(c in text for c in INDIAN_CORPS) or _CORP_SUFFIX_RE.search(text):
        score += 2
    # 6. Specific section/rule cited (+2)
    if _SECTION_RE.search(text) or "schedule i" in text:
        score += 2
    # 7. Judicial / enforcement verbs (+2)
    if any(w in text for w in
           ["penalty", "penalize", "fine", "adjudicate", "prosecute", "order", "investigation"]):
        score += 2
    # 8. Urgency verbs (+2)
    if any(w in text for w in
           ["effective immediately", "deadline", "urgency", "timeline", "urgent"]):
        score += 2
    # 9. RBI + DPDPA intersection (+3)
    if ("rbi" in source_l or "reserve bank" in text) and "dpdpa" in text:
        score += 3
    # 10. Authority bonus
    if "dataguidance" in source_l or "dsci" in source_l:
        score += 2
    elif "iapp" in source_l or "privacyenforcement" in source_l:
        score += 1
    # 11. Judicial court sources — highest authority (+4, +1 if section cited)
    if any(k in source_l for k in
           ["indiankanoon", "supreme court", "high court", "adjudication", "nclt", "cci"]):
        score += 4
        if _SECTION_RULE_RE.search(text):
            score += 1
    # 12. Indian business press bonus (+2)
    if any(k in source_l for k in
           ["et business", "economictimes", "inc42", "yourstory", "entrackr", "livemint"]):
        score += 2

    base = min(20, score)

    # Recency delta curve
    days = compute_days_old(published_date)
    is_court = any(k in source_l for k in ["indiankanoon", "supreme court", "high court"])
    if is_court:
        delta = 3 if days <= 30 else (0 if days <= 180 else (-2 if days <= 730 else -4))
    else:
        delta = (
            3 if days <= 7
            else (1 if days <= 30 else (0 if days <= 90 else (-3 if days <= 180 else -6)))
        )
    return base + delta


# ── Section / sector classification ────────────────────────────────────────
def classify_section(text: str, authority: str = "") -> str:
    """Route an item into one of the 5 front-end tabs."""
    t = f"{authority} {text}".lower()
    if any(k in t for k in ["dpdpa", "data protection board", "dpbi", "meity", "dpdp rules"]):
        return "dpdpa_board"
    if any(k in t for k in ["cert-in", "cert in", "breach notification", "6 hour", "6-hour", "70b"]):
        return "cert_in_breach"
    if any(k in t for k in
           ["supreme court", "high court", "tribunal", "tdsat", "judgment", "43a", "72a", "court"]):
        return "courts_case_law"
    if any(k in t for k in
           ["rbi", "reserve bank", "sebi", "irdai", "cci", "trai", "npci", "uidai", "dot ",
            "ccpa"]):
        return "sectoral_regulators"
    if any(k in t for k in
           ["gdpr", "edpb", "ico", "cnil", "garante", "pdpc", "oaic", "eu ", "ireland",
            "european"]):
        return "international_benchmarks"
    return "sectoral_regulators"


def classify_sector(text: str) -> str:
    t = text.lower()
    if any(k in t for k in
           ["bank", "fintech", "payment", "upi", "paytm", "phonepe", "rbi", "lending", "npci"]):
        return "Fintech"
    if any(k in t for k in
           ["health", "hospital", "insurance", "irdai", "star health", "pharma", "medical"]):
        return "Healthcare"
    if any(k in t for k in
           ["social", "meta", "facebook", "whatsapp", "google", "twitter", "x corp", "tech",
            "app ", "platform"]):
        return "Social Media / Tech"
    if any(k in t for k in
           ["government", "aadhaar", "uidai", "ministry", "govt", "public sector", "state"]):
        return "Government"
    return "Other"
