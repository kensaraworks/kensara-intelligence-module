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
    "privacy policy", "data sharing", "consent", "data privacy",
]

# Live legal proceedings. These carry no penalty figure and often no statute
# number, so the keyword signals miss them entirely — yet a Supreme Court
# hearing on a privacy matter is among the most valuable things we can surface.
PROCEEDING_KW = [
    "supreme court", "high court", "nclat", "nclt", "tribunal", "tdsat",
    "hearing", "appeal", "petition", "pil", "writ", "bench", "verdict",
    "judgment", "ruling", "stay", "interim order", "notice to",
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
    title: str, summary: str, source: str, published_date: str = "",
    tracked_entities: set[str] | None = None,
) -> int:
    """12+2 signal relevance score.

    ``tracked_entities`` are normalised names already in the knowledge graph;
    a story about one of them is probably a development in a case we follow.
    """
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

    # 13. Live legal proceeding (+3). Court coverage rarely trips the money or
    #     statute signals, but a privacy matter before the SC/NCLAT is exactly
    #     what the tracker exists to follow.
    if any(k in text for k in PROCEEDING_KW):
        score += 3

    # 14. Concerns an entity we already track (+4). A follow-up on a case in our
    #     graph — an appeal, a compliance order, a settlement — is the highest
    #     value signal available, and keyword scoring alone cannot see it.
    if tracked_entities:
        if any(e in text for e in tracked_entities):
            score += 4

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


# ── Explainability: which signals actually fired ──────────────────────────
def score_breakdown(title: str, summary: str, source: str,
                    published_date: str = "") -> dict:
    """Same 12 signals as calculate_relevance_score, but itemised.

    Used by the inspection lab so a human can see *why* an item scored what it
    did, rather than trusting an opaque number.
    """
    text = f"{title} {summary}".lower()
    source_l = (source or "").lower()
    signals: list[dict] = []

    def add(name: str, points: int, detail: str = "") -> None:
        if points:
            signals.append({"signal": name, "points": points, "detail": detail})

    hi = [kw for kw in HIGH_KW if kw in text]
    add("High-relevance keywords", 2 * len(hi), ", ".join(hi[:6]))
    med = [kw for kw in MED_KW if kw in text]
    add("Medium-relevance keywords", len(med), ", ".join(med[:6]))
    if any(s in source_l for s in ["meity", "dpbi", "cert-in", "rbi", "yourstory",
                                   "inc42", "entrackr"]):
        add("India-origin source", 2, source)
    m = _MONEY_RE.search(text)
    if m:
        add("Monetary penalty mentioned", 3, m.group(0))
    corp = [c for c in INDIAN_CORPS if c in text]
    if corp or _CORP_SUFFIX_RE.search(text):
        add("Named Indian enterprise", 2, ", ".join(corp[:4]) or "corporate suffix")
    sec = _SECTION_RE.search(text)
    if sec or "schedule i" in text:
        add("Specific section/rule cited", 2, sec.group(0) if sec else "schedule i")
    verbs = [w for w in ["penalty", "penalize", "fine", "adjudicate", "prosecute",
                         "order", "investigation"] if w in text]
    if verbs:
        add("Judicial/enforcement verbs", 2, ", ".join(verbs[:4]))
    urg = [w for w in ["effective immediately", "deadline", "urgency", "timeline",
                       "urgent"] if w in text]
    if urg:
        add("Urgency language", 2, ", ".join(urg[:3]))
    if ("rbi" in source_l or "reserve bank" in text) and "dpdpa" in text:
        add("RBI x DPDPA intersection", 3)
    if "dataguidance" in source_l or "dsci" in source_l:
        add("Authority source bonus", 2, source)
    elif "iapp" in source_l or "privacyenforcement" in source_l:
        add("Authority source bonus", 1, source)
    if any(k in source_l for k in ["indiankanoon", "supreme court", "high court",
                                   "adjudication", "nclt", "cci"]):
        pts = 4 + (1 if _SECTION_RULE_RE.search(text) else 0)
        add("Judicial court source", pts, source)
    if any(k in source_l for k in ["et business", "economictimes", "inc42",
                                   "yourstory", "entrackr", "livemint"]):
        add("Indian business press", 2, source)

    base = sum(s["points"] for s in signals)
    capped = min(20, base)
    days = compute_days_old(published_date)
    is_court = any(k in source_l for k in ["indiankanoon", "supreme court", "high court"])
    if is_court:
        delta = 3 if days <= 30 else (0 if days <= 180 else (-2 if days <= 730 else -4))
    else:
        delta = (3 if days <= 7 else
                 (1 if days <= 30 else (0 if days <= 90 else (-3 if days <= 180 else -6))))
    return {
        "signals": signals, "base": base, "capped_base": capped,
        "recency_delta": delta, "days_old": days, "final": capped + delta,
    }


def tracked_entity_names(limit: int = 60) -> set[str]:
    """Lower-cased names of entities already in the knowledge graph.

    Cheap, cached per process. Failure is non-fatal — scoring simply falls back
    to the keyword signals.
    """
    global _TRACKED_CACHE
    try:
        if _TRACKED_CACHE is not None:
            return _TRACKED_CACHE
    except NameError:
        pass
    # Match on DISTINCTIVE TERMS, not canonical names. The graph stores
    # "Meta Platforms" but a headline says "Meta-WhatsApp", so a full-name
    # substring test never fires. Aliases and the distinctive token both count.
    generic = {"india", "indian", "limited", "ltd", "private", "pvt", "bank",
               "commission", "authority", "ministry", "board", "court", "of",
               "and", "the", "insurance", "financial", "services", "data"}
    names: set[str] = set()
    try:
        from src.graph.build import build_graph

        for e in build_graph().pageable[:limit]:
            variants = [e.name or ""] + list(e.aliases or [])
            for v in variants:
                v = v.lower().strip()
                if len(v) >= 4:
                    names.add(v)
                toks = [t for t in v.replace("/", " ").replace("-", " ").split()
                        if len(t) >= 4 and t not in generic]
                # A single distinctive token identifies a brand ("mastercard",
                # "meta", "linkedin"); two-token names keep the pair too.
                if toks:
                    names.add(toks[0])
                    if len(toks) >= 2:
                        names.add(" ".join(toks[:2]))
    except Exception:
        names = set()
    names = {n for n in names if len(n) >= 4}
    _TRACKED_CACHE = names
    return names


_TRACKED_CACHE = None
