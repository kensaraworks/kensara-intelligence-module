"""Domain store: typed operations on top of the raw Supabase client.

Also builds the *public snapshot* — the exact JSON shape the static front-end
consumes (5 sections + statistics) — so the site works even without a live DB
connection at page-load time (the snapshot is committed as web/data/enforcement.json).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import structlog

from src.db.supabase_client import SupabaseClient, db

log = structlog.get_logger(__name__)

ENFORCEMENT = "enforcement_actions"
STORIES = "stories_processed"
COMPETITOR = "competitor_intel"
RUNS = "scraper_runs"
DECISIONS = "review_decisions"
BRIEFS = "intel_briefs"
ANGLES = "content_angles"

SECTIONS = [
    "dpdpa_board",
    "sectoral_regulators",
    "cert_in_breach",
    "courts_case_law",
    "international_benchmarks",
]

_SECTOR_BUCKETS = {
    "social_tech_count": {"Social Media / Tech"},
    "healthcare_count": {"Healthcare", "Insurance / Healthcare", "Insurance"},
    "fintech_count": {"Fintech", "Payments / Fintech", "Payments"},
    "gov_count": {"Government"},
}


def _client(client: SupabaseClient | None = None) -> SupabaseClient:
    return client or db


# ── Stories ───────────────────────────────────────────────────────────────
def story_id_for(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def record_story(row: dict[str, Any], client: SupabaseClient | None = None) -> None:
    row.setdefault("story_id", story_id_for(row["url"]))
    _client(client).upsert(STORIES, row, on_conflict="story_id", ignore_duplicates=False)


def recent_fingerprints(days: int = 14, client: SupabaseClient | None = None) -> list[dict]:
    """Return recent stories' fingerprint vectors for TF-IDF dedup."""
    return _client(client).select(
        STORIES,
        columns="story_id,headline,fingerprint_vector",
        order="processed_at.desc",
        limit=500,
    )


def top_stories(limit: int = 25, min_score: int = 0, client: SupabaseClient | None = None) -> list[dict]:
    filters = {"score": f"gte.{min_score}"} if min_score else None
    return _client(client).select(
        STORIES, columns="headline,score,url,intent_tag,source,processed_at",
        filters=filters, order="score.desc", limit=limit,
    )


def url_seen(url: str, client: SupabaseClient | None = None) -> bool:
    sid = story_id_for(url)
    rows = _client(client).select(
        STORIES, columns="story_id", filters={"story_id": f"eq.{sid}"}, limit=1
    )
    return bool(rows)


# ── Enforcement ────────────────────────────────────────────────────────────
def enforcement_source_seen(source_url: str, client: SupabaseClient | None = None) -> bool:
    rows = _client(client).select(
        ENFORCEMENT, columns="id", filters={"source_url": f"eq.{source_url}"}, limit=1
    )
    return bool(rows)


def insert_candidate(row: dict[str, Any], client: SupabaseClient | None = None) -> list[dict]:
    """Insert an auto-detected enforcement candidate (needs_review=True)."""
    row.setdefault("detected_at", datetime.now(timezone.utc).isoformat())
    row.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    return _client(client).upsert(
        ENFORCEMENT, row, on_conflict="source_url", ignore_duplicates=True
    )


def review_queue(limit: int = 100, client: SupabaseClient | None = None) -> list[dict]:
    return _client(client).select(
        ENFORCEMENT,
        filters={"needs_review": "eq.true"},
        order="detected_at.desc",
        limit=limit,
    )


def all_published(client: SupabaseClient | None = None) -> list[dict]:
    return _client(client).select(
        ENFORCEMENT, filters={"needs_review": "eq.false"}, order="date.desc", limit=2000
    )


def mark_verified(
    action_id: str, updates: dict[str, Any], client: SupabaseClient | None = None
) -> bool:
    patch = dict(updates)
    patch["needs_review"] = False
    patch["verified_at"] = datetime.now(timezone.utc).isoformat()
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = _client(client).update(ENFORCEMENT, patch, {"id": f"eq.{action_id}"})
    return bool(res)


# ── Guardrail: retention prune (#keep DB bounded) ──────────────────────────
def prune_old_stories(days: int = 90, client: SupabaseClient | None = None) -> None:
    """Delete processed-story rows older than N days to cap DB growth."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    _client(client).delete(STORIES, {"processed_at": f"lt.{cutoff}"})


# ── Feedback loop (#4) ─────────────────────────────────────────────────────
def record_decision(row: dict[str, Any], client: SupabaseClient | None = None) -> None:
    _client(client).upsert(DECISIONS, row)


def recent_decisions(limit: int = 40, client: SupabaseClient | None = None) -> list[dict]:
    return _client(client).select(
        DECISIONS, order="decided_at.desc", limit=limit
    )


def false_positive_signatures(
    limit: int = 200, client: SupabaseClient | None = None
) -> set[str]:
    rows = _client(client).select(
        DECISIONS, columns="signature,decision",
        filters={"decision": "eq.discarded"}, order="decided_at.desc", limit=limit,
    )
    return {r["signature"] for r in rows if r.get("signature")}


# ── Weekly brief (#6) ──────────────────────────────────────────────────────
def upsert_brief(period: str, markdown: str, stats: dict, client: SupabaseClient | None = None):
    _client(client).upsert(
        BRIEFS, {"period": period, "markdown": markdown, "stats": stats},
        on_conflict="period", ignore_duplicates=False,
    )


def latest_brief(client: SupabaseClient | None = None) -> dict | None:
    rows = _client(client).select(BRIEFS, order="created_at.desc", limit=1)
    return rows[0] if rows else None


# ── Content angles (#9) ────────────────────────────────────────────────────
def upsert_angles(rows: list[dict], client: SupabaseClient | None = None) -> None:
    if rows:
        _client(client).upsert(ANGLES, rows, on_conflict="story_url", ignore_duplicates=True)


# ── Re-verification (#7) ───────────────────────────────────────────────────
def open_published_cases(
    older_than_days: int = 30, limit: int = 40, client: SupabaseClient | None = None
) -> list[dict]:
    """Published cases with an unresolved outcome, not re-checked recently."""
    rows = _client(client).select(
        ENFORCEMENT,
        filters={"needs_review": "eq.false"},
        order="last_reverified_at.asc.nullsfirst",
        limit=200,
    )
    open_states = ("Investigation Ongoing", "Consultation")
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    out = []
    for r in rows:
        if r.get("outcome") not in open_states:
            continue
        lr = r.get("last_reverified_at")
        if lr:
            try:
                if datetime.fromisoformat(lr.replace("Z", "+00:00")) > cutoff:
                    continue
            except Exception:
                pass
        out.append(r)
        if len(out) >= limit:
            break
    return out


def update_case(action_id: str, patch: dict, client: SupabaseClient | None = None) -> bool:
    patch = dict(patch)
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    return bool(_client(client).update(ENFORCEMENT, patch, {"id": f"eq.{action_id}"}))


# ── Scraper health log ─────────────────────────────────────────────────────
def log_run(
    job: str,
    status: str,
    *,
    source: str | None = None,
    detail: str | None = None,
    items_found: int = 0,
    client: SupabaseClient | None = None,
) -> None:
    _client(client).upsert(
        RUNS,
        {
            "job": job,
            "source": source,
            "status": status,
            "detail": (detail or "")[:500],
            "items_found": items_found,
        },
    )


# ── Public snapshot (front-end contract) ───────────────────────────────────
def build_public_snapshot(client: SupabaseClient | None = None) -> dict[str, Any]:
    """Assemble the exact JSON the static tracker renders."""
    rows = all_published(client)
    sections: dict[str, list[dict]] = {s: [] for s in SECTIONS}
    for r in rows:
        sec = r.get("section") if r.get("section") in sections else "sectoral_regulators"
        sections[sec].append(_public_row(r))

    stats = {
        "total_all_sections": len(rows),
        "total_dpdpa_board": len(sections["dpdpa_board"]),
        "total_sectoral_regulators": len(sections["sectoral_regulators"]),
        "total_cert_in_breach": len(sections["cert_in_breach"]),
        "total_courts_case_law": len(sections["courts_case_law"]),
        "total_international": len(sections["international_benchmarks"]),
    }

    sector_counts = {k: 0 for k in _SECTOR_BUCKETS}
    sector_counts["other_sectors_count"] = 0
    for r in rows:
        matched = False
        for bucket, names in _SECTOR_BUCKETS.items():
            if r.get("sector") in names:
                sector_counts[bucket] += 1
                matched = True
                break
        if not matched:
            sector_counts["other_sectors_count"] += 1

    return {
        "metadata": {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "last_updated_formatted": datetime.now(timezone.utc).strftime("%d %B %Y"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "statistics": stats,
        "sector_counts": sector_counts,
        "sections": sections,
    }


def _public_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "date": r.get("date", ""),
        "authority": r.get("authority", ""),
        "company": r.get("company", ""),
        "sector": r.get("sector", "Other"),
        "violation_type": r.get("violation_type", ""),
        "dpdpa_section": r.get("dpdpa_section", ""),
        "summary": r.get("summary", ""),
        "penalty_amount": r.get("penalty_amount", ""),
        "outcome": r.get("outcome", ""),
        "source_url": r.get("source_url", ""),
        "sources": r.get("sources", []) or [],
        "official_source_url": r.get("official_source_url", ""),
    }
