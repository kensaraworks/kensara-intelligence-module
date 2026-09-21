"""Full-article text extraction (#1).

Extraction quality jumps when the LLM sees the real article instead of a 200-char
search snippet. We reuse the existing stealth fetcher, strip boilerplate, and
**truncate to config.article_max_chars** (guardrail #3) so token spend stays capped.
Failures degrade to the snippet — never fatal.
"""
from __future__ import annotations

import structlog
from bs4 import BeautifulSoup

from src.config import settings
from src.ingestion.stealth_scraper import fetch_protected_page

log = structlog.get_logger(__name__)

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


def clean_html_to_text(html: str, max_chars: int | None = None) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body or soup
    text = node.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    cap = max_chars or settings.article_max_chars
    return text[:cap]


async def fetch_article_text(url: str, fallback: str = "") -> str:
    """Return cleaned, truncated article text; falls back to the snippet."""
    if not url:
        return fallback
    html = await fetch_protected_page(url)
    if not html:
        return fallback
    try:
        text = clean_html_to_text(html)
        # Guard against nav-only / paywalled shells that yield near-nothing.
        return text if len(text) >= 200 else (fallback or text)
    except Exception as exc:
        log.warning("fulltext.parse_failed", url=url, error=str(exc))
        return fallback


# ── Aggregator redirects ──────────────────────────────────────────────────
# Google News RSS returns opaque redirect URLs (news.google.com/rss/articles/...).
# Fetching one yields a ~500-char JavaScript stub, NOT the article — which is
# strictly worse than the RSS snippet, and was silently starving the extractor.
_AGGREGATOR_HOSTS = ("news.google.com", "news.yahoo.com/rss")


def is_aggregator_url(url: str) -> bool:
    return any(h in (url or "") for h in _AGGREGATOR_HOSTS)


async def resolve_publisher_url(title: str, publisher_url: str = "") -> str:
    """Find the real article behind an aggregator redirect.

    Costs ONE search call, so it is only worth doing for an item we are about to
    spend an LLM call on anyway. Returns "" when search is unavailable.
    """
    from src.config import settings

    if not settings.has_search or not title:
        return ""
    from urllib.parse import urlparse

    domain = ""
    try:
        domain = urlparse(publisher_url).netloc.replace("www.", "")
    except Exception:
        pass

    from src.ingestion import search_sweep

    # Strip the " - Publisher" suffix Google News appends to headlines.
    clean = title.rsplit(" - ", 1)[0].strip()
    query = f'{"site:" + domain + " " if domain else ""}"{clean[:90]}"'
    try:
        results = await search_sweep.search(query, num=3)
    except Exception as exc:
        log.warning("fulltext.resolve_failed", error=str(exc))
        return ""
    for r in results:
        if r.url and not is_aggregator_url(r.url):
            log.info("fulltext.resolved", publisher=domain or "?", url=r.url[:80])
            return r.url
    return ""


async def fetch_article_text_smart(item, fallback: str = "") -> tuple[str, dict]:
    """Fetch article text, resolving aggregator redirects first.

    Returns (text, diagnostics) so the inspection lab can show what actually
    happened — a silent 500-char stub is exactly the failure that hid here.
    """
    diag = {"aggregator": False, "resolved_url": "", "chars": 0, "note": ""}
    url = getattr(item, "url", "") or ""

    if is_aggregator_url(url):
        diag["aggregator"] = True
        real = await resolve_publisher_url(getattr(item, "title", ""),
                                           getattr(item, "publisher_url", ""))
        if real:
            diag["resolved_url"] = real
            text = await fetch_article_text(real, fallback=fallback)
            diag.update(chars=len(text), note="resolved aggregator link to publisher")
            return text, diag
        # No search available: the snippet beats a JS redirect stub.
        diag.update(chars=len(fallback), note="aggregator link unresolved — using snippet")
        return fallback, diag

    text = await fetch_article_text(url, fallback=fallback)
    diag.update(chars=len(text), note="direct fetch")
    return text, diag
