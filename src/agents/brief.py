"""Weekly executive brief + trend aggregates (#6).

Aggregates are computed in pure Python (cheap, deterministic). One LLM call turns
them into a readable brief. Stored in `intel_briefs` and published to
web/data/brief.json for optional display. Falls back to a templated brief if no
LLM key is present — never crashes.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.db import store
from src.processing.llm import complete_text

log = structlog.get_logger(__name__)

BRIEF_JSON = Path(__file__).resolve().parents[2] / "web" / "data" / "brief.json"


def _aggregates(cases: list[dict], stories: list[dict]) -> dict:
    by_section = Counter(c.get("section", "?") for c in cases)
    by_sector = Counter(c.get("sector", "Other") for c in cases)
    by_authority = Counter(c.get("authority", "Unknown") for c in cases)
    sections_cited = Counter(
        c.get("dpdpa_section", "").strip() for c in cases if c.get("dpdpa_section", "").strip())
    total_penalty = sum(float(c.get("penalty_amount_inr") or 0) for c in cases)
    top_stories = sorted(stories, key=lambda s: s.get("score", 0), reverse=True)[:5]
    return {
        "verified_cases": len(cases),
        "by_section": dict(by_section),
        "by_sector": dict(by_sector),
        "top_authorities": by_authority.most_common(4),
        "most_cited_provisions": sections_cited.most_common(4),
        "total_penalty_inr": total_penalty,
        "top_stories": [{"headline": s.get("headline"), "score": s.get("score"),
                         "url": s.get("url")} for s in top_stories],
    }


def _period() -> str:
    now = datetime.now(timezone.utc).isocalendar()
    return f"{now.year}-W{now.week:02d}"


def _template_brief(stats: dict) -> str:
    lines = [f"# Enforcement Intelligence Brief — {_period()}", ""]
    lines.append(f"**Verified cases in dataset:** {stats['verified_cases']}")
    if stats["top_authorities"]:
        lines.append("**Most active authorities:** " +
                     ", ".join(f"{a} ({n})" for a, n in stats["top_authorities"]))
    if stats["most_cited_provisions"]:
        lines.append("**Most-cited provisions:** " +
                     ", ".join(f"{p} ({n})" for p, n in stats["most_cited_provisions"]))
    lines.append("")
    lines.append("## Top signals this week")
    for s in stats["top_stories"]:
        lines.append(f"- [{s['score']}] {s['headline']}")
    return "\n".join(lines)


async def generate_brief() -> dict:
    cases = store.all_published()
    stories = store.top_stories(limit=25)
    stats = _aggregates(cases, stories or [])

    prompt = (
        "You are a regulatory-intelligence analyst for KensaraAI (India DPDPA "
        "compliance). Write a concise weekly executive brief (max 250 words, "
        "markdown) for a compliance leader. Be specific and non-alarmist. Use the "
        "aggregates below. Include: (1) headline takeaway, (2) what changed, "
        "(3) one action for Indian companies.\n\n"
        f"Aggregates JSON:\n{json.dumps(stats, ensure_ascii=False)}"
    )
    markdown = await complete_text(prompt, max_tokens=700)
    if not markdown:
        markdown = _template_brief(stats)

    period = _period()
    store.upsert_brief(period, markdown, stats)
    _publish_json(period, markdown, stats)
    log.info("brief.done", period=period, cases=stats["verified_cases"])
    return {"status": "ok", "period": period, "cases": stats["verified_cases"]}


def _publish_json(period: str, markdown: str, stats: dict) -> None:
    try:
        BRIEF_JSON.parent.mkdir(parents=True, exist_ok=True)
        BRIEF_JSON.write_text(json.dumps(
            {"period": period, "markdown": markdown, "stats": stats,
             "generated_at": datetime.now(timezone.utc).isoformat()},
            indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("brief.publish_failed", error=str(exc))
