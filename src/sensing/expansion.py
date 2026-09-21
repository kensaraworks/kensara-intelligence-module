"""Entity-graph expansion — the self-widening part of the net.

Keyword search can only find what you already thought to ask about. Once an
entity is in the graph, we watch it *by name* forever, so follow-ups, appeals
and second actions surface even when they share no keywords with the original
query. Coverage compounds as the graph grows.

Free: every generated watch is a Google News RSS query, not a paid search.
"""
from __future__ import annotations

import structlog

from src.sensing.registry import TIER_PRESS, Source

log = structlog.get_logger(__name__)

# Entities generic enough that a name-watch would return mostly noise.
_SKIP = {"unknown", "industry-wide", "generic"}

# Pair the entity name with topical anchors so the watch stays on-subject.
_ANCHOR = "(data OR privacy OR breach OR penalty OR DPDP OR CERT-In)"


def watch_query(entity_name: str) -> str:
    return f'"{entity_name}" {_ANCHOR}'


def build_watchlist(max_entities: int = 40) -> list[Source]:
    """Turn resolved graph entities into free Google News watches."""
    try:
        from src.graph.build import build_graph

        graph = build_graph()
    except Exception as exc:
        log.warning("expansion.graph_unavailable", error=str(exc))
        return []

    watches: list[Source] = []
    seen: set[str] = set()

    # Companies first: they generate follow-up news. Regulators are already
    # covered by their own primary-source sensors, so watching them adds little.
    candidates = graph.companies + [e for e in graph.regulators if len(e.event_ids) > 1]

    for ent in candidates:
        name = (ent.name or "").strip()
        key = name.lower()
        if not name or key in seen or key in _SKIP or len(name) < 4:
            continue
        if ent.entity_type in {"case", "generic", "statute"}:
            continue
        seen.add(key)
        watches.append(Source(
            name=f"Watch: {name}", kind="gnews", tier=TIER_PRESS,
            url=watch_query(name), domain=ent.slug))
        if len(watches) >= max_entities:
            break

    log.info("expansion.watchlist_built", watches=len(watches))
    return watches


def watchlist_stats() -> dict:
    watches = build_watchlist()
    return {"watches": len(watches), "cost": "free (Google News RSS)",
            "names": [w.name.replace("Watch: ", "") for w in watches[:12]]}
