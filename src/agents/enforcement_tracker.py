"""Weekly enforcement tracker — now with the intelligence upgrades.

Pipeline:
  0. Load ReviewMemory (feedback loop, #4).
  1. Search sweep (Serper/Tavily).
  2. Dedup (TF-IDF) + 12-signal score; record stories.
  3. GUARDRAIL: keep only the top `max_candidates_per_sweep` unseen survivors.
  4. Per survivor: fetch FULL article text (#1) → LLM extract with few-shot (#4).
  5. Drop known false positives (#4); ground against official sources (#3).
  6. Cluster/merge same-event candidates into one row + sources (#2).
  7. Insert into the review queue (auto-publish only grounded high-confidence).
  8. GUARDRAIL: prune stories older than retention; rebuild snapshot.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from src.config import ENFORCEMENT_QUERIES, settings
from src.db import store
from src.ingestion import search_sweep
from src.ingestion.models import RawItem
from src.processing import llm_extractor
from src.processing.clustering import merge_candidate_rows
from src.processing.dedup import Deduplicator
from src.processing.feedback import ReviewMemory
from src.processing.fulltext import fetch_article_text
from src.processing.grounding import find_official_source, is_trusted
from src.processing.scoring import calculate_relevance_score, classify_section, classify_sector

log = structlog.get_logger(__name__)

_AUTHORITY_SECTION = {
    "Data Protection Board of India": "dpdpa_board",
    "MeitY": "dpdpa_board",
    "CERT-In": "cert_in_breach",
    "Reserve Bank of India": "sectoral_regulators",
    "Competition Commission of India": "sectoral_regulators",
    "IRDAI": "sectoral_regulators",
    "SEBI": "sectoral_regulators",
    "High Court / Supreme Court": "courts_case_law",
}


def _new_id() -> str:
    return f"AUTO-{datetime.now(timezone.utc):%Y}-{uuid.uuid4().hex[:6].upper()}"


def _candidate_row(item: RawItem, ex, score: int, official_url: str | None) -> dict:
    combined = f"{item.title} {ex.executive_summary} {ex.violation_type}"
    section = _AUTHORITY_SECTION.get(ex.authority) or classify_section(combined, ex.authority)
    sector = ex.sector if ex.sector and ex.sector != "Other" else classify_sector(combined)
    confidence = "high" if official_url else (ex.confidence_score or "medium")
    grounded_high = bool(official_url) and confidence == "high"
    needs_review = not (settings.auto_publish_high_confidence and grounded_high)
    return {
        "id": _new_id(),
        "section": section,
        "date": item.published or RawItem.now_iso(),
        "authority": ex.authority or "Unknown",
        "company": ex.company or "[Needs review]",
        "sector": sector,
        "violation_type": ex.violation_type,
        "dpdpa_section": ex.dpdpa_section,
        "summary": ex.executive_summary or item.summary,
        "penalty_amount": ex.penalty_amount,
        "penalty_amount_inr": ex.penalty_inr_numeric or 0,
        "outcome": ex.outcome,
        "source_url": item.url,
        "official_source_url": official_url or "",
        "auto_detected": True,
        "needs_review": needs_review,
        "confidence": confidence,
        "llm_extracted_data": ex.model_dump(),
    }


async def update_enforcement_tracker() -> dict:
    log.info("enforcement.start", search=settings.has_search, llm=settings.has_llm)

    if not settings.has_search:
        store.log_run("enforcement", "error", detail="no search provider configured")
        from src.publish.snapshot import publish_all
        publish_all()
        return {"status": "skipped", "reason": "no_search_provider"}

    memory = ReviewMemory.load()  # #4
    items = await search_sweep.sweep(ENFORCEMENT_QUERIES, num=10)

    dedup = Deduplicator(threshold=settings.dedup_threshold)
    dedup.seed([f["fingerprint_vector"] for f in store.recent_fingerprints()
                if f.get("fingerprint_vector")])

    # ── Dedup + score, collect unseen survivors ──────────────────────────
    survivors: list[tuple[RawItem, int]] = []
    suppressed = 0
    for item in items:
        if not item.url or store.enforcement_source_seen(item.url):
            continue
        is_dup, _sim, fp = dedup.is_duplicate(item.text())
        score = calculate_relevance_score(item.title, item.summary, item.source, item.published)
        store.record_story({
            "source": item.source, "headline": item.title, "url": item.url, "score": score,
            "fingerprint_vector": fp,
            "action_taken": "suppressed" if is_dup else "scanned",
        })
        if is_dup:
            suppressed += 1
        else:
            survivors.append((item, score))

    # ── GUARDRAIL: cap LLM/API spend to the top-N by score ───────────────
    survivors.sort(key=lambda t: t[1], reverse=True)
    capped = survivors[: settings.max_candidates_per_sweep]

    few_shot = memory.few_shot_block()
    rows: list[dict] = []
    discarded = fp_skipped = grounded = 0

    for item, score in capped:
        full_text = await fetch_article_text(item.url, fallback=item.summary)  # #1
        ex = await llm_extractor.extract_enforcement(
            item.title, item.summary, item.url, full_text=full_text, few_shot=few_shot)
        if ex is None:
            discarded += 1
            continue
        if memory.is_known_false_positive(ex.company, ex.authority):  # #4
            fp_skipped += 1
            continue
        official = None
        if is_trusted(item.url):
            official = item.url
        else:
            official = await find_official_source(  # #3
                ex.company, ex.authority, keywords=ex.violation_type)
        if official:
            grounded += 1
        rows.append(_candidate_row(item, ex, score, official))

    merged = merge_candidate_rows(rows)  # #2

    inserted = published = 0
    for row in merged:
        res = store.insert_candidate(row)
        if res:
            inserted += 1
            if not row["needs_review"]:
                published += 1

    store.prune_old_stories(settings.story_retention_days)  # GUARDRAIL
    from src.publish.snapshot import publish_all
    publish_all()

    store.log_run("enforcement", "ok",
                  detail=(f"scanned={len(items)} capped={len(capped)} merged={len(merged)} "
                          f"inserted={inserted} grounded={grounded} fp_skipped={fp_skipped}"),
                  items_found=inserted)
    summary = {
        "status": "ok", "scanned": len(items), "candidates": len(capped),
        "merged": len(merged), "inserted": inserted, "auto_published": published,
        "suppressed": suppressed, "grounded": grounded,
        "false_positives_skipped": fp_skipped, "discarded": discarded,
    }
    log.info("enforcement.done", **summary)
    return summary
