"""Build the knowledge graph from published rows.

Computed, not migrated: the graph is reconstructed from scratch on every run, so
improving resolution logic improves the graph immediately — no migrations, no
drift. Persistence to Supabase is best-effort and nothing here depends on it.

Inputs : published `enforcement_actions` rows (DB) or the committed snapshot.
Outputs: entities, events (with timeline + contradictions) for the renderer.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

from src.graph.entities import Entity, EntityResolver
from src.publish.model import RenderEvent, from_rows

log = structlog.get_logger(__name__)

# Fields where two sources disagreeing is meaningful, not noise.
CONTRADICTION_FIELDS = ("penalty_display", "date", "outcome")

_AMOUNT_RE = re.compile(r"[\d,]+(?:\.\d+)?")


@dataclass
class Contradiction:
    field_name: str
    values: list[str]

    @property
    def label(self) -> str:
        pretty = {"penalty_display": "penalty amount", "date": "date",
                  "outcome": "outcome"}.get(self.field_name, self.field_name)
        return f"Sources differ on the {pretty}"


@dataclass
class GraphEvent:
    """A RenderEvent enriched with resolved entities and cross-source checks."""

    event: RenderEvent
    subject: Entity | None = None
    authorities: list[Entity] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)

    # Convenience passthroughs so templates can stay simple.
    def __getattr__(self, item):
        return getattr(self.event, item)


@dataclass
class KnowledgeGraph:
    events: list[GraphEvent]
    entities: list[Entity]

    def entity_events(self, ent: Entity) -> list[GraphEvent]:
        return [ge for ge in self.events
                if (ge.subject and ge.subject.key == ent.key)
                or any(a.key == ent.key for a in ge.authorities)]

    @property
    def companies(self) -> list[Entity]:
        return [e for e in self.entities if e.entity_type == "company"]

    @property
    def regulators(self) -> list[Entity]:
        return [e for e in self.entities if e.entity_type in ("regulator", "court")]

    @property
    def pageable(self) -> list[Entity]:
        """Entities that warrant their own public page (see classify_entity)."""
        from src.graph.entities import PAGEABLE_TYPES

        return [e for e in self.entities
                if e.entity_type in PAGEABLE_TYPES and e.event_ids]


def _normalise_amount(value: str) -> str:
    """Compare penalties by their numeric core so '₹213.14 Cr' == '₹213.14 crore'."""
    m = _AMOUNT_RE.search(value or "")
    return m.group(0).replace(",", "") if m else (value or "").strip().lower()


def detect_contradictions(event: RenderEvent) -> list[Contradiction]:
    """Flag disagreement between sources rather than silently picking one.

    Today a published row carries one agreed value per field, so this mostly
    fires once multi-source claims accumulate (Phase 2+). The detection lives
    here so the surface is ready and the data model is honest from day one.
    """
    out: list[Contradiction] = []
    claims: dict[str, set[str]] = defaultdict(set)

    for src in event.sources:
        raw = getattr(src, "claimed", None)
        if isinstance(raw, dict):
            for f in CONTRADICTION_FIELDS:
                if raw.get(f):
                    claims[f].add(str(raw[f]))

    for f, values in claims.items():
        norm = {_normalise_amount(v) if f == "penalty_display" else v.strip().lower()
                for v in values}
        if len(norm) > 1:
            out.append(Contradiction(field_name=f, values=sorted(values)))
    return out


def build_graph(rows: list[dict] | None = None) -> KnowledgeGraph:
    """Resolve entities and assemble events. Deterministic and idempotent."""
    if rows is None:
        rows = _load_rows()

    events = from_rows(rows)
    resolver = EntityResolver()
    graph_events: list[GraphEvent] = []

    for ev in events:
        subject = resolver.resolve(ev.company)
        authorities = resolver.resolve_authorities(ev.authority)

        if subject:
            subject.event_ids.append(ev.id)
        for a in authorities:
            if a.key != (subject.key if subject else None):
                a.event_ids.append(ev.id)

        graph_events.append(GraphEvent(
            event=ev, subject=subject, authorities=authorities,
            contradictions=detect_contradictions(ev)))

    graph = KnowledgeGraph(events=graph_events, entities=resolver.all())
    log.info("graph.built", events=len(graph_events), entities=len(graph.entities),
             companies=len(graph.companies), regulators=len(graph.regulators),
             contradictions=sum(len(g.contradictions) for g in graph_events))
    return graph


def _load_rows() -> list[dict]:
    """Prefer the live DB; fall back to the committed snapshot."""
    try:
        from src.db import store

        rows = store.all_published()
        if rows:
            return rows
    except Exception as exc:
        log.warning("graph.db_unavailable", error=str(exc))

    import json
    from pathlib import Path

    snap = Path(__file__).resolve().parents[2] / "web" / "data" / "enforcement.json"
    if snap.exists():
        data = json.loads(snap.read_text(encoding="utf-8"))
        out: list[dict] = []
        for section, items in (data.get("sections") or {}).items():
            for it in items:
                out.append({**it, "section": section})
        return out
    return []


# ── Best-effort persistence (nothing above depends on it) ─────────────────
def persist(graph: KnowledgeGraph) -> dict:
    try:
        from src.db.supabase_client import db

        if not db.configured:
            return {"status": "skipped", "reason": "no_db"}

        db.upsert("entities", [{
            "key": e.key, "slug": e.slug, "name": e.name,
            "entity_type": e.entity_type, "aliases": sorted(e.aliases),
        } for e in graph.entities], on_conflict="key")

        db.upsert("events", [{
            "id": ge.event.id, "event_key": ge.event.slug, "slug": ge.event.slug,
            "title": ge.event.title, "occurred_on": ge.event.date,
            "trust_tier": ge.event.trust_tier, "penalty_inr": ge.event.penalty_inr,
            "outcome": ge.event.outcome, "summary": ge.event.summary,
            "contradictions": [{"field": c.field_name, "values": c.values}
                               for c in ge.contradictions],
        } for ge in graph.events], on_conflict="id")

        links = []
        for ge in graph.events:
            if ge.subject:
                links.append({"event_id": ge.event.id, "entity_key": ge.subject.key,
                              "role": "subject"})
            for a in ge.authorities:
                links.append({"event_id": ge.event.id, "entity_key": a.key,
                              "role": "authority"})
        if links:
            db.upsert("event_entities", links, on_conflict="event_id,entity_key,role",
                      ignore_duplicates=True)

        log.info("graph.persisted", entities=len(graph.entities), events=len(graph.events))
        return {"status": "ok", "entities": len(graph.entities), "events": len(graph.events)}
    except Exception as exc:
        log.warning("graph.persist_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}
