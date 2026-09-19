"""Story -> content angle (#9).

Turns intelligence into SEO action: for each top-scored recent story, propose a
blog angle Kensara should publish, informed by competitor gap flags. Bounded
(cap N stories), one LLM call each, JSON out. Stored in `content_angles` and
published to web/data/angles.json. No LLM key -> template angle from the headline.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.config import settings
from src.db import store
from src.db.supabase_client import db
from src.processing.llm import complete_text

log = structlog.get_logger(__name__)

ANGLES_JSON = Path(__file__).resolve().parents[2] / "web" / "data" / "angles.json"
MAX_STORIES = 8


def _competitor_gaps() -> list[str]:
    rows = db.select(store.COMPETITOR, columns="primary_keyword",
                     filters={"gap_flag": "eq.true"}, limit=50)
    kws = {r.get("primary_keyword", "").strip() for r in rows if r.get("primary_keyword")}
    return sorted(k for k in kws if k)


async def _angle_for(story: dict, gaps: list[str]) -> dict | None:
    headline = story.get("headline", "")
    if not headline:
        return None
    if not settings.has_llm:
        return {
            "story_url": story.get("url"), "headline": headline,
            "angle": f"Explainer: what '{headline}' means for DPDPA compliance in India",
            "target_keyword": "", "rationale": "Template angle (no LLM key).",
            "score": story.get("score", 0),
        }
    prompt = (
        "You are the head of SEO content at KensaraAI (India DPDPA compliance SaaS). "
        "Given this regulatory news headline, propose ONE high-intent blog angle we "
        "should publish to capture search demand and showcase our platform. "
        "Prefer angles overlapping these competitor-covered gap keywords if relevant: "
        f"{', '.join(gaps[:12]) or 'none'}.\n"
        f'Headline: "{headline}"\n\n'
        'Respond with strict JSON: {"angle": string (a compelling working title), '
        '"target_keyword": string, "rationale": one sentence on the search/business case}.'
    )
    raw = await complete_text(prompt, max_tokens=250)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
    except Exception:
        data = {}
    if not data.get("angle"):
        return None
    return {
        "story_url": story.get("url"), "headline": headline,
        "angle": data["angle"], "target_keyword": data.get("target_keyword", ""),
        "rationale": data.get("rationale", ""), "score": story.get("score", 0),
    }


async def generate_content_angles() -> dict:
    stories = store.top_stories(limit=MAX_STORIES, min_score=8)
    gaps = _competitor_gaps()
    rows = []
    for s in stories:
        angle = await _angle_for(s, gaps)
        if angle:
            rows.append(angle)
    store.upsert_angles(rows)
    _publish_json(rows)
    store.log_run("content_angles", "ok", detail=f"angles={len(rows)}", items_found=len(rows))
    log.info("angles.done", count=len(rows))
    return {"status": "ok", "angles": len(rows)}


def _publish_json(rows: list[dict]) -> None:
    try:
        ANGLES_JSON.parent.mkdir(parents=True, exist_ok=True)
        ANGLES_JSON.write_text(json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(), "angles": rows},
            indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("angles.publish_failed", error=str(exc))
