"""Daily / 4-hourly news + regulatory poll.

Ingest RSS + high-value stealth-scraped listings, dedup, score, store, and fire
webhook alerts for anything at/above the alert threshold. Cheap and key-light:
runs on RSS alone if no search/LLM keys are present.
"""
from __future__ import annotations

import structlog

from src.alerts import send_alert
from src.config import settings
from src.db import store
from src.ingestion import rss_poller, stealth_scraper
from src.processing.dedup import Deduplicator
from src.processing.scoring import calculate_relevance_score

log = structlog.get_logger(__name__)

# High-value listing pages worth stealth-scraping alongside RSS.
STEALTH_SPECS = [
    {"source": "Inc42", "url": "https://inc42.com/tag/data-protection/",
     "selector": "a[href*='/buzz/'], h2 a, h3 a", "limit": 20},
    {"source": "YourStory", "url": "https://yourstory.com/tag/dpdpa",
     "selector": "a[href*='/2025/'], a[href*='/2026/']", "limit": 20},
]


async def run_news_scan(deep: bool = True) -> dict:
    log.info("news_scan.start", deep=deep)
    items = await rss_poller.poll_all_feeds()

    if deep:
        try:
            items += await stealth_scraper.scrape_many(STEALTH_SPECS)
        except Exception as exc:  # never let scraping sink the run
            log.warning("news_scan.stealth_failed", error=str(exc))

    dedup = Deduplicator(threshold=settings.dedup_threshold)
    dedup.seed([
        f["fingerprint_vector"] for f in store.recent_fingerprints()
        if f.get("fingerprint_vector")
    ])

    scanned = suppressed = alerted = 0
    for item in items:
        if not item.url or store.url_seen(item.url):
            continue
        is_dup, _sim, fp = dedup.is_duplicate(item.text())
        score = calculate_relevance_score(item.title, item.summary, item.source, item.published)
        store.record_story({
            "source": item.source,
            "headline": item.title,
            "url": item.url,
            "score": score,
            "fingerprint_vector": fp,
            "action_taken": "suppressed" if is_dup else ("alerted" if score >= settings.alert_score_threshold else "scanned"),
        })
        if is_dup:
            suppressed += 1
            continue
        scanned += 1
        if score >= settings.alert_score_threshold:
            await send_alert(item.title, item.url, score, item.source)
            alerted += 1

    store.log_run("news_scan", "ok",
                  detail=f"scanned={scanned} suppressed={suppressed} alerted={alerted}",
                  items_found=scanned)
    result = {"status": "ok", "scanned": scanned, "suppressed": suppressed, "alerted": alerted}
    log.info("news_scan.done", **result)
    return result
