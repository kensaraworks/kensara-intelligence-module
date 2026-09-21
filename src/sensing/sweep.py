"""Sensing sweep orchestrator.

    sources → fetch (free) → seen-filter → dedup → pre-filter → scored candidates

Emits candidates for the extraction pipeline and records per-source health so
the admin can see, at a glance, which sensors have gone dark.

Cost: discovery is entirely free. The only spend downstream is the LLM call on
the capped survivors — and the pre-filter keeps that set small.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config import settings
from src.ingestion.models import RawItem
from src.processing.dedup import Deduplicator
from src.processing.scoring import calculate_relevance_score, tracked_entity_names
from src.sensing import fetchers, prefilter
from src.sensing.registry import Source, sources_upto_tier

log = structlog.get_logger(__name__)

# Local fallback so document-watch novelty works without a DB (dev/CI).
SEEN_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "seen_urls.json"


# ── Seen-URL state ────────────────────────────────────────────────────────
def load_seen() -> set[str]:
    """URLs we have actually PROCESSED (reached extraction).

    Deliberately NOT "every URL we have ever laid eyes on". Marking merely-sensed
    URLs as seen permanently excludes anything that lost the spend-cap race, which
    silently destroys recall — the one thing this system must not do.
    """
    urls: set[str] = set()
    try:
        from src.db.supabase_client import db

        if db.configured:
            # stories_processed = items that actually went through the pipeline.
            rows = db.select("stories_processed", columns="url", limit=5000)
            urls = {r["url"] for r in rows if r.get("url")}
            if urls:
                return urls
    except Exception as exc:
        log.debug("seen.db_unavailable", error=str(exc))

    try:
        if SEEN_CACHE.exists():
            urls = set(json.loads(SEEN_CACHE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return urls


def save_seen(urls: set[str]) -> None:
    try:
        SEEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SEEN_CACHE.write_text(json.dumps(sorted(urls)[-20000:]), encoding="utf-8")
    except Exception as exc:
        log.debug("seen.cache_write_failed", error=str(exc))


def record_documents(items: list[RawItem], primary_domains: set[str]) -> None:
    """Persist ingested documents (evidence trail + novelty state)."""
    try:
        import hashlib

        from src.db.supabase_client import db

        if not db.configured or not items:
            return
        rows = [{
            "id": hashlib.md5(i.url.encode()).hexdigest(),
            "url": i.url,
            "source_domain": i.source,
            "title": i.title[:500],
            "is_primary": any(d in (i.source or "") or d in (i.url or "")
                              for d in primary_domains),
            "published_at": i.published or None,
        } for i in items if i.url]
        db.upsert("documents", rows, on_conflict="url", ignore_duplicates=True)
    except Exception as exc:
        log.debug("documents.persist_failed", error=str(exc))


# ── Sweep ─────────────────────────────────────────────────────────────────
@dataclass
class SweepResult:
    items: list[RawItem] = field(default_factory=list)
    health: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


async def run_sweep(tier: int = 3, include_watchlist: bool = True,
                    cap: int | None = None) -> SweepResult:
    sources: list[Source] = sources_upto_tier(tier)

    if include_watchlist:
        try:
            from src.sensing.expansion import build_watchlist

            sources = sources + build_watchlist()
        except Exception as exc:
            log.warning("sweep.watchlist_failed", error=str(exc))

    primary_domains = {s.domain for s in sources if s.is_primary_source and s.domain}
    always_domains = {s.domain for s in sources if s.always_relevant and s.domain}
    seen = load_seen()
    seen_before = len(seen)

    results = await fetchers.fetch_all(sources, seen)

    raw: list[RawItem] = []
    health: list[dict] = []
    for r in results:
        health.append({"source": r.source.name, "kind": r.source.kind,
                       "tier": r.source.tier, "status": r.status,
                       "items": r.count, "detail": r.detail})
        raw.extend(r.items)

    # Drop anything already ingested in a previous run.
    known = {i.url for i in raw} & seen
    fresh = [i for i in raw if i.url and i.url not in known]

    # Near-duplicate suppression across outlets.
    dedup = Deduplicator(threshold=settings.dedup_threshold)
    unique: list[RawItem] = []
    suppressed = 0
    for item in fresh:
        is_dup, _sim, _fp = dedup.is_duplicate(item.text())
        if is_dup:
            suppressed += 1
        else:
            unique.append(item)

    # Cheap deterministic gate BEFORE any model call.
    kept, rejections = prefilter.filter_items(unique, primary_domains, always_domains)

    # Items deferred by a previous cap re-enter the pool and compete again.
    from src.sensing.backlog import load_backlog, save_backlog

    carried = [i for i in load_backlog() if i.url not in seen]
    kept = kept + [i for i in carried if i.url not in {k.url for k in kept}]

    # Final relevance ordering, then the spend cap.
    tracked = tracked_entity_names()   # graph-aware: follow-ups on known cases rank up
    scored = sorted(
        kept,
        key=lambda i: calculate_relevance_score(i.title, i.summary, i.source,
                                                i.published, tracked),
        reverse=True)
    limit = cap if cap is not None else settings.max_candidates_per_sweep
    candidates = scored[:limit] if limit else scored

    # The cap DEFERS, it does not discard. Survivors that missed the cut are
    # queued for the next sweep instead of being lost when the feed rolls off.
    deferred = scored[limit:] if limit else []
    save_backlog(deferred)

    # Only items that reached extraction count as processed.
    for i in candidates:
        if i.url:
            seen.add(i.url)
    save_seen(seen)
    record_documents(unique, primary_domains)

    ok = sum(1 for h in health if h["status"] in ("ok", "fallback"))
    stats = {
        "sources_polled": len(sources),
        "sources_healthy": ok,
        "sources_dark": len(health) - ok,
        "raw_items": len(raw),
        "already_seen": len(raw) - len(fresh),
        "near_duplicates": suppressed,
        "prefilter_rejected": sum(rejections.values()),
        "rejection_reasons": rejections,
        "kept": len(kept),
        "carried_from_backlog": len(carried),
        "deferred_to_backlog": len(deferred),
        "candidates": len(candidates),
        "new_urls": len(seen) - seen_before,
        "paid_api_calls": 0,
    }
    log.info("sweep.done", **{k: v for k, v in stats.items() if k != "rejection_reasons"})
    return SweepResult(items=candidates, health=health, stats=stats)


def log_health(health: list[dict], job: str = "sensing") -> None:
    try:
        from src.db import store

        for h in health:
            if h["status"] not in ("ok", "fallback"):
                store.log_run(job, "blocked" if h["status"] == "blocked" else "error",
                              source=h["source"], detail=h["detail"] or h["status"])
        store.log_run(job, "ok",
                      detail=f"{sum(1 for h in health if h['status'] in ('ok','fallback'))}"
                             f"/{len(health)} sources healthy",
                      items_found=sum(h["items"] for h in health))
    except Exception as exc:
        log.debug("health.log_failed", error=str(exc))
