"""Render model — the contract between data and the static site.

Deliberately shaped like a Phase-1 *event*, not like today's `enforcement_actions`
row, so the knowledge model can slot in later without rewriting the renderer.
Adapters convert whatever we currently have into `RenderEvent`.

Slugs are PERMANENT. Once a case is published at /enforcement/<slug>, that URL
must keep working forever — a citation that 404s is worse than no citation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ── Trust tiers (public provenance labels) ────────────────────────────────
TIER_PRIMARY = "primary_confirmed"
TIER_PRESS = "press_reported"
TIER_AI = "ai_detected"

TIER_META = {
    TIER_PRIMARY: {
        "label": "Primary source confirmed",
        "short": "Primary source",
        "icon": "✓",
        "css": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "desc": "An official document from the issuing authority has been retrieved "
                "and its key details match this entry.",
    },
    TIER_PRESS: {
        "label": "Press reported",
        "short": "Press reported",
        "icon": "◐",
        "css": "bg-amber-50 text-amber-700 border-amber-200",
        "desc": "Reported by named news sources. No primary document has been "
                "attached to this entry yet.",
    },
    TIER_AI: {
        "label": "Under review",
        "short": "Under review",
        "icon": "…",
        "css": "bg-gray-50 text-gray-600 border-gray-200",
        "desc": "Automatically detected and awaiting human review. Not published.",
    },
}

SECTION_LABELS = {
    "dpdpa_board": "DPDPA & Data Protection Board",
    "sectoral_regulators": "Sectoral Regulators",
    "cert_in_breach": "CERT-In & Breach Enforcement",
    "courts_case_law": "Courts & Case Law",
    "international_benchmarks": "International Benchmarks",
}

_AUTH_SHORT = {
    "Data Protection Board of India": "dpb",
    "Reserve Bank of India": "rbi",
    "Competition Commission of India": "cci",
    "High Court / Supreme Court": "court",
    "Irish Data Protection Commission": "dpc",
    "CERT-In / IRDAI": "cert-in",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_STOP = {"the", "of", "and", "a", "an", "for", "ltd", "limited", "pvt", "private", "inc"}


_DATE_FORMATS = (
    "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%B %Y", "%b %Y", "%Y",
)


def normalize_date(value: str) -> str:
    """Coerce any reported date to ISO YYYY-MM-DD.

    LLM extraction returns human formats ("Aug 1, 2024"), which sort
    lexicographically wrong, break period-based slugs and corrupt timelines.
    Unparseable values are returned unchanged rather than dropped.
    """
    import datetime as _dt

    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw
    for fmt in _DATE_FORMATS:
        try:
            d = _dt.datetime.strptime(raw, fmt)
            if fmt == "%Y":
                return f"{d.year:04d}-01-01"
            if fmt in ("%B %Y", "%b %Y"):
                return f"{d.year:04d}-{d.month:02d}-01"
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def slugify(text: str, max_words: int = 6) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    words = [w for w in _SLUG_STRIP.sub(" ", text.lower()).split() if w and w not in _STOP]
    return "-".join(words[:max_words]) or "case"


def authority_short(authority: str) -> str:
    if authority in _AUTH_SHORT:
        return _AUTH_SHORT[authority]
    return slugify(authority, max_words=2)


@dataclass
class Source:
    url: str
    name: str = ""
    is_primary: bool = False

    @property
    def display(self) -> str:
        if self.name:
            return self.name
        from urllib.parse import urlparse
        try:
            return urlparse(self.url).netloc.replace("www.", "")
        except Exception:
            return self.url


@dataclass
class RenderEvent:
    """One enforcement event, as the public site renders it."""

    id: str
    slug: str
    date: str
    authority: str
    company: str
    sector: str
    section: str
    violation_type: str = ""
    statute_ref: str = ""          # dpdpa_section in v1 terms
    summary: str = ""
    penalty_display: str = ""
    penalty_inr: float = 0.0
    outcome: str = ""
    trust_tier: str = TIER_AI
    sources: list[Source] = field(default_factory=list)
    updated_at: str = ""

    # ── Derived helpers used by templates ────────────────────────────────
    @property
    def tier(self) -> dict:
        return TIER_META.get(self.trust_tier, TIER_META[TIER_AI])

    @property
    def section_label(self) -> str:
        return SECTION_LABELS.get(self.section, "Enforcement")

    @property
    def url_path(self) -> str:
        # Written to enforcement/<slug>/index.html but linked WITHOUT a trailing
        # slash, to match Vercel's `trailingSlash: false`. Canonical URLs must
        # return 200, never a 308 — a redirecting canonical weakens citation.
        return f"enforcement/{self.slug}"

    @property
    def title(self) -> str:
        """Human + machine friendly page title."""
        bits = [self.company]
        if self.authority and self.authority.lower() != "unknown":
            bits.append(self.authority)
        if self.date:
            bits.append(self.date[:4])
        return " — ".join(b for b in bits if b)

    @property
    def primary_source(self) -> Source | None:
        for s in self.sources:
            if s.is_primary:
                return s
        return self.sources[0] if self.sources else None

    @property
    def year(self) -> str:
        return (self.date or "")[:4]


# ── Adapters ──────────────────────────────────────────────────────────────
def _infer_tier(row: dict) -> str:
    """Honest provenance from whatever signals the row carries."""
    explicit = (row.get("trust_tier") or "").strip()
    if explicit in TIER_META:
        return explicit
    if row.get("official_source_url"):
        return TIER_PRIMARY
    if row.get("source_url") or row.get("sources"):
        return TIER_PRESS
    return TIER_AI


def _collect_sources(row: dict) -> list[Source]:
    out: list[Source] = []
    seen: set[str] = set()

    official = row.get("official_source_url")
    if official:
        out.append(Source(url=official, is_primary=True))
        seen.add(official)

    raw = row.get("sources") or []
    if isinstance(raw, list):
        for s in raw:
            if isinstance(s, dict):
                url = s.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    out.append(Source(url=url, name=s.get("source", "")))

    primary_url = row.get("source_url")
    if primary_url and primary_url not in seen:
        out.append(Source(url=primary_url))
    return out


def build_slug(row: dict, taken: set[str]) -> str:
    """Stable, readable slug. Reuses a stored slug when present."""
    existing = (row.get("slug") or "").strip()
    if existing:
        return existing
    company = slugify(row.get("company", ""), max_words=4)
    auth = authority_short(row.get("authority", ""))
    period = (row.get("date") or "")[:7].replace("-", "")
    base = "-".join(p for p in (company, auth, period) if p)
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def from_enforcement_row(row: dict, taken: set[str]) -> RenderEvent:
    row = {**row, "date": normalize_date(row.get("date", ""))}
    slug = build_slug(row, taken)
    taken.add(slug)
    return RenderEvent(
        id=row.get("id", ""),
        slug=slug,
        date=row.get("date", ""),
        authority=row.get("authority", ""),
        company=row.get("company", ""),
        sector=row.get("sector", "Other"),
        section=row.get("section", "sectoral_regulators"),
        violation_type=row.get("violation_type", ""),
        statute_ref=row.get("dpdpa_section", ""),
        summary=row.get("summary", ""),
        penalty_display=row.get("penalty_amount", ""),
        penalty_inr=float(row.get("penalty_amount_inr") or 0),
        outcome=row.get("outcome", ""),
        trust_tier=_infer_tier(row),
        sources=_collect_sources(row),
        updated_at=str(row.get("updated_at") or "")[:10],
    )


def from_rows(rows: list[dict]) -> list[RenderEvent]:
    taken: set[str] = set()
    events = [from_enforcement_row(r, taken) for r in rows]
    events.sort(key=lambda e: e.date or "", reverse=True)
    return events


def from_snapshot(snapshot: dict) -> list[RenderEvent]:
    """Adapter for the committed JSON snapshot (offline / no-DB path)."""
    rows: list[dict] = []
    for section, items in (snapshot.get("sections") or {}).items():
        for item in items:
            rows.append({**item, "section": section})
    return from_rows(rows)
