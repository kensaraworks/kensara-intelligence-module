"""Weekly competitor intelligence crawl.

Scrapes competitor blog/resource listings, records fresh posts, and flags
content gaps (topics competitors cover). Pure scraping — no paid APIs required.
"""
from __future__ import annotations

import structlog

from src.db import store
from src.db.supabase_client import db
from src.ingestion import stealth_scraper
from src.ingestion.models import RawItem

log = structlog.get_logger(__name__)

COMPETITORS = [
    {"domain": "securiti.ai", "url": "https://securiti.ai/blog/",
     "selector": "a[href*='/blog/']", "limit": 25},
    {"domain": "cookieyes.com", "url": "https://www.cookieyes.com/blog/",
     "selector": "a[href*='/blog/']", "limit": 25},
    {"domain": "tsaaro.com", "url": "https://tsaaro.com/blogs/",
     "selector": "a[href*='/blog']", "limit": 25},
]

# Topics we care about ranking for — used to flag competitor coverage as a gap.
GAP_KEYWORDS = [
    "dpdpa", "consent", "dsar", "data principal", "data fiduciary",
    "breach notification", "cert-in", "data localisation", "privacy policy",
]


async def run_competitor_intelligence() -> dict:
    log.info("competitor.start")
    total = gaps = 0
    for comp in COMPETITORS:
        try:
            items = await stealth_scraper.scrape_listing(
                comp["domain"], comp["url"], comp["selector"], limit=comp["limit"]
            )
        except Exception as exc:
            store.log_run("competitor", "blocked", source=comp["domain"], detail=str(exc))
            continue

        rows = []
        for it in items:
            title_l = it.title.lower()
            is_gap = any(k in title_l for k in GAP_KEYWORDS)
            rows.append({
                "domain": comp["domain"],
                "url": it.url,
                "title": it.title,
                "pub_date": RawItem.now_iso(),
                "primary_keyword": next((k for k in GAP_KEYWORDS if k in title_l), ""),
                "word_count": 0,
                "summary": "",
                "gap_flag": is_gap,
            })
            if is_gap:
                gaps += 1
        if rows:
            db.upsert(store.COMPETITOR, rows, on_conflict="url", ignore_duplicates=True)
            total += len(rows)
        store.log_run("competitor", "ok", source=comp["domain"], items_found=len(rows))

    result = {"status": "ok", "crawled": total, "gaps_flagged": gaps}
    log.info("competitor.done", **result)
    return result
