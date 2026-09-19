"""Scoped web-search sweeps for the enforcement tracker.

Provider order: Serper (Google SERP, cheap/generous free tier) → Tavily.
Both return a normalised list of ``RawItem``. If neither key is present the
sweep returns [] so upstream code can fall back to RSS/scraping only.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

from src.config import settings
from src.ingestion.models import RawItem

log = structlog.get_logger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_TAVILY_URL = "https://api.tavily.com/search"


async def _serper(query: str, num: int = 10) -> list[RawItem]:
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(
                _SERPER_URL,
                headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num, "gl": "in", "hl": "en"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.warning("serper.failed", query=query, error=str(exc))
        return []
    items = []
    for res in data.get("organic", [])[:num]:
        items.append(
            RawItem(
                source=_domain(res.get("link", "")),
                title=res.get("title", ""),
                url=res.get("link", ""),
                summary=res.get("snippet", ""),
                published=res.get("date", ""),
            )
        )
    return items


async def _tavily(query: str, num: int = 10) -> list[RawItem]:
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                _TAVILY_URL,
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": num,
                    "include_answer": False,
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.warning("tavily.failed", query=query, error=str(exc))
        return []
    items = []
    for res in data.get("results", [])[:num]:
        items.append(
            RawItem(
                source=_domain(res.get("url", "")),
                title=res.get("title", ""),
                url=res.get("url", ""),
                summary=(res.get("content") or "")[:1200],
            )
        )
    return items


async def search(query: str, num: int = 10) -> list[RawItem]:
    if settings.serper_api_key:
        res = await _serper(query, num)
        if res:
            return res
    if settings.tavily_api_key:
        return await _tavily(query, num)
    return []


async def sweep(queries: list[str], num: int = 10) -> list[RawItem]:
    """Run all queries concurrently and flatten, de-duping by URL."""
    results = await asyncio.gather(*(search(q, num) for q in queries), return_exceptions=True)
    seen: set[str] = set()
    flat: list[RawItem] = []
    for chunk in results:
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if item.url and item.url not in seen:
                seen.add(item.url)
                flat.append(item)
    log.info("search.sweep_complete", queries=len(queries), items=len(flat))
    return flat


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
