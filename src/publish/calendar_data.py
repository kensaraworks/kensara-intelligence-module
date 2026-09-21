"""Regulatory calendar — forward-looking milestones.

Nobody publishes a forward-looking India data-protection calendar, and "what do
I have to do by when" is exactly the question that converts a reader into a
customer. It is also the page where a wrong date would do the most damage.

So the rule here is strict: **every milestone must carry a source.** Nothing is
generated from a model's memory. The calendar is assembled from two places:

  1. ``MILESTONES`` below — curated entries, each with a source URL. Your team
     adds verified deadlines here as the DPDP Rules phase in.
  2. Tracked events — dates already verified in the enforcement dataset are
     surfaced automatically, so the calendar stays current for free.

If we are unsure of a date, it does not go on the page. An empty calendar is
recoverable; a wrong compliance deadline is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Milestone:
    date: str                  # ISO YYYY-MM-DD
    title: str
    description: str
    kind: str = "milestone"    # milestone | deadline | consultation | enforcement
    authority: str = ""
    source_url: str = ""
    confirmed: bool = True     # False => clearly labelled as expected/indicative

    @property
    def is_future(self) -> bool:
        try:
            return datetime.strptime(self.date, "%Y-%m-%d").date() >= date.today()
        except ValueError:
            return False

    @property
    def year(self) -> str:
        return self.date[:4]

    @property
    def days_away(self) -> int | None:
        try:
            d = datetime.strptime(self.date, "%Y-%m-%d").date()
            return (d - date.today()).days
        except ValueError:
            return None


# ── Curated milestones (each MUST carry a source) ─────────────────────────
MILESTONES: list[Milestone] = [
    Milestone(
        date="2023-08-11",
        title="Digital Personal Data Protection Act, 2023 receives Presidential assent",
        description="India's first comprehensive data-protection statute enters the statute "
                    "book, with penalties of up to ₹250 crore per breach. Provisions commence "
                    "on dates notified by the Central Government.",
        kind="milestone", authority="MeitY",
        source_url="https://www.meity.gov.in/data-protection-framework"),
    Milestone(
        date="2025-01-03",
        title="Draft Digital Personal Data Protection Rules released for consultation",
        description="MeitY published draft Rules covering notice, consent managers, "
                    "breach notification, children's data verification and Board procedure, "
                    "and invited public comments.",
        kind="consultation", authority="MeitY",
        source_url="https://www.meity.gov.in/data-protection-framework"),
]

# ── Team instructions (shown in the repo, not on the page) ────────────────
# To add a verified deadline:
#   Milestone(date="YYYY-MM-DD", title="...", description="...",
#             kind="deadline", authority="MeitY",
#             source_url="<official notification URL>")
# Set confirmed=False only for an officially-signalled but not-yet-notified
# date; the page will label it as indicative.


def derived_from_events(events) -> list[Milestone]:
    """Surface dated, verified enforcement events on the timeline for free."""
    out: list[Milestone] = []
    for e in events or []:
        if not e.date or len(e.date) < 10:
            continue
        out.append(Milestone(
            date=e.date,
            title=f"{e.company} — {e.authority}",
            description=(e.summary or "")[:220],
            kind="enforcement",
            authority=e.authority,
            source_url=(e.primary_source.url if e.primary_source else ""),
        ))
    return out


def build_calendar(events=None) -> dict:
    """Upcoming first (that is the useful view), then the historical timeline."""
    curated_dates = {m.date for m in MILESTONES}
    # A curated milestone and a tracked event often describe the SAME thing
    # (e.g. the draft Rules). Prefer the curated entry, which carries a source.
    derived = [m for m in derived_from_events(events) if m.date not in curated_dates]

    items = list(MILESTONES) + derived
    items.sort(key=lambda m: m.date)

    upcoming = [m for m in items if m.is_future and m.kind != "enforcement"]
    past = [m for m in items if not m.is_future]
    past.reverse()

    by_year: dict[str, list[Milestone]] = {}
    for m in past:
        by_year.setdefault(m.year, []).append(m)

    return {
        "upcoming": upcoming,
        "past": past,
        "by_year": by_year,
        "has_upcoming": bool(upcoming),
        "curated_count": len(MILESTONES),
    }
