"""Anti-bot stealth scraping via curl_cffi Chrome TLS impersonation.

Cloudflare/Akamai fingerprint the TLS ClientHello, so plain httpx/requests get
challenged. ``curl_cffi`` replays a real Chrome JA3/JA4 handshake. If curl_cffi
is unavailable (e.g. a stripped environment), we fall back to httpx so the code
still runs — just with a higher block rate.
"""
from __future__ import annotations

import asyncio

import structlog
from bs4 import BeautifulSoup

from src.ingestion.models import RawItem

log = structlog.get_logger(__name__)

_HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

try:
    from curl_cffi.requests import AsyncSession  # type: ignore

    _HAS_CURL_CFFI = True
except Exception:  # pragma: no cover
    _HAS_CURL_CFFI = False


async def fetch_protected_page(url: str, timeout: int = 20) -> str | None:
    """Return page HTML, impersonating Chrome. None on failure."""
    if _HAS_CURL_CFFI:
        try:
            async with AsyncSession() as session:
                resp = await session.get(
                    url, impersonate="chrome124", timeout=timeout, headers=_HEADERS
                )
                resp.raise_for_status()
                return resp.text
        except Exception as exc:
            log.warning("stealth.curl_cffi_failed", url=url, error=str(exc))
    # Fallback: plain httpx
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url, headers={**_HEADERS, "User-Agent": "Mozilla/5.0 Chrome/124.0"})
            r.raise_for_status()
            return r.text
    except Exception as exc:
        log.warning("stealth.httpx_failed", url=url, error=str(exc))
        return None


async def scrape_listing(
    source: str,
    url: str,
    link_selector: str,
    *,
    base: str = "",
    limit: int = 25,
) -> list[RawItem]:
    """Fetch a listing/tag page and extract anchor items via a CSS selector."""
    html = await fetch_protected_page(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    items: list[RawItem] = []
    seen: set[str] = set()
    for a in soup.select(link_selector)[: limit * 2]:
        href = a.get("href") or ""
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 12:
            continue
        if href.startswith("/"):
            href = (base or _origin(url)) + href
        if not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        items.append(RawItem(source=source, title=title, url=href))
        if len(items) >= limit:
            break
    log.info("stealth.listing", source=source, count=len(items))
    return items


def _origin(url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


async def scrape_many(specs: list[dict]) -> list[RawItem]:
    """Run several listing scrapes concurrently.

    Each spec: {source, url, selector, base?, limit?}
    """
    tasks = [
        scrape_listing(
            s["source"], s["url"], s["selector"], base=s.get("base", ""), limit=s.get("limit", 25)
        )
        for s in specs
    ]
    out: list[RawItem] = []
    for res in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(res, list):
            out.extend(res)
    return out
