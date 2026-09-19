"""Concurrent RSS/Atom ingestion.

Uses ``feedparser`` (tolerant of malformed feeds) behind a thread pool so all
feeds are fetched in parallel with a per-feed timeout budget. Network and
parse errors are isolated: one dead feed never fails the whole sweep.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import httpx
import structlog

from src.config import RSS_FEEDS
from src.ingestion.models import RawItem

log = structlog.get_logger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _fetch_one(name: str, url: str, timeout: int = 15) -> list[RawItem]:
    items: list[RawItem] = []
    try:
        # Fetch bytes ourselves (feedparser's own fetch ignores UA/timeout well).
        resp = httpx.get(url, timeout=timeout, headers={"User-Agent": _UA}, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries[:40]:
            link = entry.get("link", "")
            if not link:
                continue
            published = ""
            if getattr(entry, "published_parsed", None):
                published = time.strftime("%Y-%m-%d", entry.published_parsed)
            elif getattr(entry, "updated_parsed", None):
                published = time.strftime("%Y-%m-%d", entry.updated_parsed)
            items.append(
                RawItem(
                    source=name,
                    title=(entry.get("title") or "").strip(),
                    url=link.strip(),
                    summary=(entry.get("summary") or entry.get("description") or "").strip()[:1200],
                    published=published,
                )
            )
        log.info("rss.ok", feed=name, count=len(items))
    except Exception as exc:
        log.warning("rss.failed", feed=name, error=str(exc))
    return items


async def poll_all_feeds(feeds: dict[str, str] | None = None) -> list[RawItem]:
    feeds = feeds or RSS_FEEDS
    loop = asyncio.get_event_loop()
    results: list[RawItem] = []
    with ThreadPoolExecutor(max_workers=min(8, len(feeds))) as pool:
        tasks = [
            loop.run_in_executor(pool, _fetch_one, name, url) for name, url in feeds.items()
        ]
        for chunk in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(chunk, list):
                results.extend(chunk)
    log.info("rss.sweep_complete", total=len(results))
    return results
