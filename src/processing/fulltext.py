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
