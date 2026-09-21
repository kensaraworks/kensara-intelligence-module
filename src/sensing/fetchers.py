"""Sensors: RSS / Google-News RSS / document-watch.

All three are free. A source that fails (dead feed, bot-block, layout change)
automatically retries through its Google News fallback, so coverage degrades
gracefully instead of silently going dark — the failure mode that actually
matters when the goal is "miss nothing".
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import feedparser
import httpx
import structlog
from bs4 import BeautifulSoup

from src.ingestion.models import RawItem
from src.sensing.registry import Source

log = structlog.get_logger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class SourceResult:
    source: Source
    items: list[RawItem]
    status: str          # ok | empty | fallback | blocked | error
    detail: str = ""

    @property
    def count(self) -> int:
        return len(self.items)


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _parse_feed(content: bytes, source: Source) -> list[RawItem]:
    parsed = feedparser.parse(content)
    items: list[RawItem] = []
    for entry in parsed.entries[:60]:
        link = (entry.get("link") or "").strip()
        title = _clean(entry.get("title") or "")
        if not link or not title:
            continue
        published = ""
        for attr in ("published_parsed", "updated_parsed"):
            if getattr(entry, attr, None):
                published = time.strftime("%Y-%m-%d", getattr(entry, attr))
                break
        summary = _clean(entry.get("summary") or entry.get("description") or "")[:1500]
        # Google News wraps the real publisher in the title: "Headline - Publisher"
        src_name = source.domain or source.name
        publisher_url = ""
        if source.kind == "gnews" and getattr(entry, "source", None):
            src_name = entry.source.get("title", src_name)
            publisher_url = entry.source.get("href", "")
        items.append(RawItem(source=src_name, title=title, url=link,
                             summary=summary, published=published,
                             publisher_url=publisher_url))
    return items


def _fetch_bytes(url: str, timeout: int = 20) -> bytes | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": _UA, "Accept-Language": "en-IN,en;q=0.9"})
        r.raise_for_status()
        return r.content
    except Exception as exc:
        log.debug("fetch.failed", url=url, error=str(exc))
        return None


def fetch_rss(source: Source) -> SourceResult:
    content = _fetch_bytes(source.resolved_url())
    if content is None:
        return SourceResult(source, [], "blocked", "fetch failed")
    items = _parse_feed(content, source)
    return SourceResult(source, items, "ok" if items else "empty")


def fetch_docwatch(source: Source, seen: set[str]) -> SourceResult:
    """Diff a listing page's links against what we've already recorded.

    No keywords: anything newly published on a regulator page is interesting by
    construction. This is the highest-signal free sensor we have.
    """
    content = _fetch_bytes(source.resolved_url(), timeout=25)
    if content is None:
        return SourceResult(source, [], "blocked", "fetch failed")
    try:
        soup = BeautifulSoup(content, "lxml")
    except Exception as exc:
        return SourceResult(source, [], "error", str(exc))

    from urllib.parse import urljoin

    items: list[RawItem] = []
    for a in soup.select(source.selector)[:400]:
        href = (a.get("href") or "").strip()
        title = _clean(a.get_text())
        if not href or len(title) < 12:
            continue
        url = urljoin(source.resolved_url(), href)
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        items.append(RawItem(source=source.domain or source.name, title=title, url=url))
        if len(items) >= 40:
            break
    return SourceResult(source, items, "ok" if items else "empty")


def fetch_source(source: Source, seen: set[str]) -> SourceResult:
    """Dispatch by sensor type, falling back to Google News if the sensor fails."""
    try:
        if source.kind == "docwatch":
            res = fetch_docwatch(source, seen)
        else:
            res = fetch_rss(source)
    except Exception as exc:
        res = SourceResult(source, [], "error", str(exc))

    if res.status in ("blocked", "error", "empty") and source.gnews_fallback:
        import dataclasses

        from src.sensing.registry import gnews_rss

        content = _fetch_bytes(gnews_rss(source.gnews_fallback))
        if content is not None:
            # CRITICAL: parse the fallback AS a Google News feed, and strip the
            # primary-source flag/domain. Otherwise a Business Standard article
            # surfaced via CCI's fallback would be attributed to cci.gov.in and
            # wrongly promoted to "primary source confirmed" — corrupting the
            # provenance that the whole trust model rests on.
            proxy = dataclasses.replace(
                source, kind="gnews", domain="", is_primary_source=False,
                always_relevant=False)
            items = _parse_feed(content, proxy)
            if items:
                log.info("sensor.fallback_used", source=source.name, count=len(items))
                return SourceResult(source, items, "fallback",
                                    f"primary {res.status}; used Google News")
    return res


async def fetch_all(sources: list[Source], seen: set[str],
                    max_workers: int = 10) -> list[SourceResult]:
    """Fetch every source concurrently in threads (feedparser/bs4 are sync)."""
    loop = asyncio.get_event_loop()
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        tasks = [loop.run_in_executor(pool, fetch_source, s, seen) for s in sources]
        for res in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(res, SourceResult):
                results.append(res)
            else:
                log.warning("sensor.task_failed", error=str(res))
    return results
