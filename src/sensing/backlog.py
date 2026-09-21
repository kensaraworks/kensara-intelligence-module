"""Candidate backlog — the spend cap must defer, never discard.

The per-sweep cap exists to bound LLM spend, not to make editorial judgements.
An item that passed the relevance pre-filter but finished 16th is *queued*, not
rejected. Without an explicit backlog those items vanish for good, because RSS
feeds roll off within a day or two — which is precisely how a
"miss nothing" system quietly starts missing things.

So: survivors that lose the cap race are persisted and re-enter the ranking pool
on the next sweep, ahead of nothing and behind nothing — they simply compete
again. Over successive runs the backlog drains.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from src.ingestion.models import RawItem

log = structlog.get_logger(__name__)

BACKLOG_PATH = Path(__file__).resolve().parents[2] / ".cache" / "backlog.json"
MAX_AGE_DAYS = 21          # after this, a story is no longer "recent"
MAX_BACKLOG = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_backlog() -> list[RawItem]:
    """Deferred items still young enough to matter."""
    try:
        if not BACKLOG_PATH.exists():
            return []
        raw = json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("backlog.read_failed", error=str(exc))
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    out: list[RawItem] = []
    for r in raw:
        try:
            if datetime.fromisoformat(r.get("queued_at", "")) < cutoff:
                continue
        except Exception:
            pass
        out.append(RawItem(
            source=r.get("source", ""), title=r.get("title", ""),
            url=r.get("url", ""), summary=r.get("summary", ""),
            published=r.get("published", "")))
    log.info("backlog.loaded", count=len(out))
    return out


def save_backlog(items: list[RawItem], existing: list[RawItem] | None = None) -> int:
    """Persist deferred items, newest first, de-duplicated by URL."""
    merged: dict[str, dict] = {}
    for it in (existing or []) + list(items):
        if not it.url:
            continue
        merged.setdefault(it.url, {
            "source": it.source, "title": it.title, "url": it.url,
            "summary": (it.summary or "")[:600], "published": it.published,
            "queued_at": _now(),
        })
    rows = list(merged.values())[:MAX_BACKLOG]
    try:
        BACKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKLOG_PATH.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("backlog.write_failed", error=str(exc))
    log.info("backlog.saved", count=len(rows))
    return len(rows)


def clear_processed(processed_urls: set[str]) -> None:
    """Drop anything that has now been extracted."""
    current = load_backlog()
    remaining = [i for i in current if i.url not in processed_urls]
    if len(remaining) != len(current):
        save_backlog(remaining)
