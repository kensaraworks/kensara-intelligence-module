"""Case-level clustering (#2).

Search sweeps return the same enforcement event from several outlets. Instead of
creating N review cards, we group by a normalised (company|authority|month|amount)
key and emit ONE candidate carrying every corroborating source. Multi-source
corroboration also feeds the confidence signal used by grounding (#3).

Pure-python, in-memory — this REDUCES load (one LLM extraction per cluster).
"""
from __future__ import annotations

from src.processing.signature import cluster_key

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def merge_candidate_rows(rows: list[dict]) -> list[dict]:
    """Merge post-extraction candidate rows that describe the same event.

    Bounded and accurate: we already know company/authority/date/amount, so the
    (company|authority|month|amount) key is reliable. Merged rows keep every
    corroborating source, the richest summary, and the strongest confidence.
    """
    buckets: dict[str, dict] = {}
    for row in rows:
        key = cluster_key(
            row.get("company", ""), row.get("authority", ""),
            row.get("date", ""), row.get("penalty_amount_inr", 0),
        )
        src = {"source": _domain(row.get("source_url", "")), "url": row.get("source_url", "")}
        if key not in buckets:
            row.setdefault("sources", [])
            if src["url"]:
                row["sources"] = [src]
            buckets[key] = row
            continue
        # Merge into the existing representative.
        base = buckets[key]
        if src["url"] and src["url"] not in {s.get("url") for s in base["sources"]}:
            base["sources"].append(src)
        if len(row.get("summary", "")) > len(base.get("summary", "")):
            base["summary"] = row["summary"]
        if _CONF_RANK.get(row.get("confidence"), 0) > _CONF_RANK.get(base.get("confidence"), 0):
            base["confidence"] = row["confidence"]
        if row.get("official_source_url") and not base.get("official_source_url"):
            base["official_source_url"] = row["official_source_url"]
        for f in ("penalty_amount", "dpdpa_section", "violation_type"):
            if not base.get(f) and row.get(f):
                base[f] = row[f]
    return list(buckets.values())


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
