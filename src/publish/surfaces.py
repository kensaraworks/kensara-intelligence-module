"""Phase 4 public surfaces: statute explorer, penalties, calendar, static API.

Each is generated from the same knowledge base, so every new verified case
strengthens several pages at once — that is the compounding mechanism behind
the long-tail strategy.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.publish.calendar_data import build_calendar
from src.publish.statute import (
    OFFICIAL_TEXT_URL,
    SCHEDULE_PENALTIES,
    SECTIONS,
    sections_cited_in,
)

log = structlog.get_logger(__name__)


def _fmt_inr(total: float) -> str:
    if not total:
        return ""
    if total >= 1_00_00_000:
        return f"₹{total / 1_00_00_000:,.2f} Cr".replace(".00", "")
    if total >= 1_00_000:
        return f"₹{total / 1_00_000:,.2f} Lakh".replace(".00", "")
    return f"₹{total:,.0f}"


# ── Statute explorer ──────────────────────────────────────────────────────
def cases_by_section(events) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    for e in events:
        for sec in sections_cited_in(e.statute_ref or ""):
            out[sec.number].append(e)
    return out


def render_statute_pages(events, env, site, base_url: str, web: Path) -> int:
    mapping = cases_by_section(events)
    tmpl = env.get_template("section.html")
    written = 0

    for s in SECTIONS:
        cases = sorted(mapping.get(s.number, []), key=lambda e: e.date or "", reverse=True)
        related = [r for r in SECTIONS if r.chapter == s.chapter and r.number != s.number][:4]
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Legislation",
            "@id": f"{base_url}/{s.url_path}#section",
            "name": f"DPDPA 2023 {s.label} — {s.title}",
            "legislationIdentifier": f"DPDP Act 2023, {s.label}",
            "jurisdiction": {"@type": "AdministrativeArea", "name": "India"},
            "description": s.summary,
            "isPartOf": {"@type": "Legislation",
                         "name": "Digital Personal Data Protection Act, 2023"},
        }, ensure_ascii=False, indent=2)
        html = tmpl.render(site=site, s=s, cases=cases, related=related,
                           official_url=OFFICIAL_TEXT_URL, jsonld=jsonld)
        d = web / "dpdpa" / s.slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
        written += 1

    by_chapter: dict[str, list] = defaultdict(list)
    for s in SECTIONS:
        by_chapter[s.chapter].append(s)
    index_html = env.get_template("dpdpa_index.html").render(
        site=site, by_chapter=dict(by_chapter),
        case_counts={k: len(v) for k, v in mapping.items()},
        penalties=SCHEDULE_PENALTIES, official_url=OFFICIAL_TEXT_URL)
    d = web / "dpdpa"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(index_html, encoding="utf-8")
    return written + 1


# ── Penalty database ──────────────────────────────────────────────────────
def _grouped(events, key):
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
    for e in events:
        k = (key(e) or "Unknown").strip() or "Unknown"
        agg[k]["count"] += 1
        agg[k]["total"] += e.penalty_inr or 0
    rows = sorted(agg.items(), key=lambda kv: (kv[1]["total"], kv[1]["count"]), reverse=True)
    top = rows[0][1]["total"] or rows[0][1]["count"] if rows else 1
    out = []
    for name, v in rows[:8]:
        basis = v["total"] if top else 0
        pct = int((basis / top) * 100) if top and basis else max(8, int(v["count"] / max(
            1, rows[0][1]["count"]) * 100))
        out.append((name, v["count"], _fmt_inr(v["total"]), max(4, min(100, pct))))
    return out


def render_penalties_page(events, env, site, base_url: str, web: Path, stats: dict) -> None:
    total = sum(e.penalty_inr or 0 for e in events)
    largest = sorted([e for e in events if (e.penalty_inr or 0) > 0],
                     key=lambda e: e.penalty_inr, reverse=True)[:10]

    years: dict[str, int] = defaultdict(int)
    for e in events:
        if e.year.isdigit():
            years[e.year] += 1
    ordered = sorted(years.items())
    peak = max(years.values()) if years else 1
    by_year = [(y, c, max(6, int(c / peak * 100))) for y, c in ordered]

    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "@id": f"{base_url}/penalties#dataset",
        "name": "India data-protection penalties — aggregate analysis",
        "description": "Totals of Indian data-protection enforcement penalties by regulator, "
                       "sector and year, computed from the KensaraAI enforcement tracker.",
        "isPartOf": {"@id": f"{base_url}/#dataset"},
        "url": f"{base_url}/penalties",
    }, ensure_ascii=False, indent=2)

    html = env.get_template("penalties.html").render(
        site=site, stats=stats, total_display=_fmt_inr(total), largest=largest,
        by_authority=_grouped(events, lambda e: e.authority),
        by_sector=_grouped(events, lambda e: e.sector),
        by_year=by_year, jsonld=jsonld)
    d = web / "penalties"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")


# ── Calendar ──────────────────────────────────────────────────────────────
def render_calendar_page(events, env, site, web: Path) -> None:
    cal = build_calendar(events)
    html = env.get_template("calendar.html").render(site=site, cal=cal)
    d = web / "calendar"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")


# ── Static JSON API (no server, CDN-cached, free) ─────────────────────────
def write_api(events, graph, base_url: str, web: Path, stats: dict) -> list[str]:
    """Machine-consumable endpoints — this is how tools and agents cite us."""
    api = web / "api" / "v1"
    api.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    written: list[str] = []

    def dump(name: str, payload: dict) -> None:
        (api / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        written.append(f"api/v1/{name}")

    dump("cases.json", {
        "generated_at": now, "count": len(events),
        "license": "CC BY 4.0", "attribution": "KensaraAI — https://kensara.in",
        "cases": [{
            "id": e.id, "slug": e.slug, "url": f"{base_url}/{e.url_path}",
            "date": e.date, "company": e.company, "authority": e.authority,
            "sector": e.sector, "section": e.section,
            "violation_type": e.violation_type, "legal_provision": e.statute_ref,
            "penalty": e.penalty_display, "penalty_inr": e.penalty_inr,
            "outcome": e.outcome, "trust_tier": e.trust_tier,
            "sources": [s.url for s in e.sources],
        } for e in events]})

    dump("entities.json", {
        "generated_at": now, "count": len(graph.pageable),
        "entities": [{
            "slug": en.slug, "name": en.name, "type": en.entity_type,
            "url": f"{base_url}/{en.url_path}",
            "aliases": sorted(en.aliases), "case_count": len(en.event_ids),
        } for en in graph.pageable]})

    total = sum(e.penalty_inr or 0 for e in events)
    dump("stats.json", {
        "generated_at": now,
        "total_cases": stats["total"],
        "primary_confirmed": stats["primary_confirmed"],
        "total_penalty_inr": total,
        "by_section": {k: v for k, v in (
            ("dpdpa_board", stats["total_dpdpa_board"]),
            ("sectoral_regulators", stats["total_sectoral_regulators"]),
            ("cert_in_breach", stats["total_cert_in_breach"]),
            ("courts_case_law", stats["total_courts_case_law"]),
            ("international_benchmarks", stats["total_international"]))},
        "by_authority": {n: c for n, c, _a, _p in _grouped(events, lambda e: e.authority)},
        "by_sector": {n: c for n, c, _a, _p in _grouped(events, lambda e: e.sector)},
    })

    dump("index.json", {
        "name": "KensaraAI India Data Protection Enforcement API",
        "version": "v1", "license": "CC BY 4.0",
        "attribution": "KensaraAI — https://kensara.in",
        "generated_at": now,
        "endpoints": {
            "cases": f"{base_url}/api/v1/cases.json",
            "entities": f"{base_url}/api/v1/entities.json",
            "stats": f"{base_url}/api/v1/stats.json",
            "csv": f"{base_url}/data/enforcement.csv",
        }})
    return written
