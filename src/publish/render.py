"""Static site renderer (Phase 0).

Emits fully pre-rendered HTML so generative crawlers (GPTBot, ClaudeBot,
PerplexityBot, CCBot) — which largely do NOT execute JavaScript — can read every
case. The client-side live refresh still runs, but only as *progressive
enhancement* on top of complete HTML.

Outputs into web/:
    index.html                 tracker, all sections pre-rendered
    enforcement/<slug>.html    one permanent, citable page per case
    data/enforcement.json      machine-readable snapshot (existing contract)
    data/enforcement.csv       flat export for analysts / crawlers
    sitemap.xml, robots.txt, llms.txt

Run:  python -m src.publish.render
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.publish.model import (
    SECTION_LABELS,
    TIER_PRIMARY,
    RenderEvent,
    from_rows,
    from_snapshot,
)

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
TEMPLATES = Path(__file__).resolve().parent / "templates"

BASE_URL = "https://kensara-intelligence-module-alpha.vercel.app"

SECTION_ORDER = [
    ("dpdpa_board", "DPDPA / DPB"),
    ("sectoral_regulators", "Sectoral Regulators"),
    ("cert_in_breach", "CERT-In & Breaches"),
    ("courts_case_law", "Courts"),
    ("international_benchmarks", "Global"),
]

SECTION_BADGE = {
    "dpdpa_board": "bg-purple-100 text-purple-800",
    "sectoral_regulators": "bg-emerald-100 text-emerald-800",
    "cert_in_breach": "bg-orange-100 text-orange-800",
    "courts_case_law": "bg-blue-100 text-blue-800",
    "international_benchmarks": "bg-slate-200 text-slate-700",
}

SECTION_SUBTITLES = {
    "dpdpa_board": "Statute, rules and Data Protection Board milestones — from MeitY, PIB, the eGazette, India Code and PRS.",
    "sectoral_regulators": "Penalties and orders from RBI, SEBI, IRDAI, CCI, TRAI, DoT, UIDAI and NPCI — the precedent landscape shaping Indian data-protection enforcement today.",
    "cert_in_breach": "CERT-In directions and advisories (IT Act Section 70B, 6-hour reporting mandate) plus reported Indian data breaches.",
    "courts_case_law": "Judgments and tribunal rulings from the Supreme Court, High Courts, TDSAT and IT Act Section 43A adjudications.",
    "international_benchmarks": "Major GDPR and global DPA enforcement actions affecting Indian IT/ITES companies or subsidiaries — benchmarks for DPDPA precedent.",
}


def outcome_badge(outcome: str) -> str:
    o = (outcome or "").lower()
    if "fine" in o or "penalty" in o:
        return "badge-fine"
    if "ban" in o or "restrict" in o:
        return "badge-ban"
    if "compliance" in o:
        return "badge-compliance"
    if "enacted" in o or "rule" in o or "force" in o:
        return "badge-enacted"
    if "investigation" in o or "ongoing" in o or "consultation" in o:
        return "badge-investigation"
    return "badge-other"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["outcome_badge"] = outcome_badge
    return env


# ── Data loading ──────────────────────────────────────────────────────────
def load_events() -> list[RenderEvent]:
    """Prefer the live DB; fall back to the committed snapshot."""
    try:
        from src.db import store

        rows = store.all_published()
        if rows:
            log.info("render.source", source="supabase", count=len(rows))
            return from_rows(rows)
    except Exception as exc:
        log.warning("render.db_unavailable", error=str(exc))

    snap_path = WEB / "data" / "enforcement.json"
    if snap_path.exists():
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        events = from_snapshot(snapshot)
        log.info("render.source", source="snapshot", count=len(events))
        return events
    return []


# ── Stats ─────────────────────────────────────────────────────────────────
def build_stats(events: list[RenderEvent]) -> dict:
    grouped: dict[str, list[RenderEvent]] = {sid: [] for sid, _ in SECTION_ORDER}
    for e in events:
        grouped.setdefault(e.section, []).append(e)
    years = [e.year for e in events if e.year.isdigit()]
    return {
        "total": len(events),
        "primary_confirmed": sum(1 for e in events if e.trust_tier == TIER_PRIMARY),
        "total_dpdpa_board": len(grouped.get("dpdpa_board", [])),
        "total_sectoral_regulators": len(grouped.get("sectoral_regulators", [])),
        "total_cert_in_breach": len(grouped.get("cert_in_breach", [])),
        "total_courts_case_law": len(grouped.get("courts_case_law", [])),
        "total_international": len(grouped.get("international_benchmarks", [])),
        "earliest_year": min(years) if years else "—",
    }, grouped


# ── JSON-LD ───────────────────────────────────────────────────────────────
def dataset_jsonld(stats: dict) -> str:
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "@id": f"{BASE_URL}/#dataset",
        "name": "DPDPA Enforcement Actions India — KensaraAI Tracker",
        "description": ("Comprehensive database of Indian data-privacy enforcement actions: "
                        "DPDPA 2023, IT Act Section 43A/72A, CERT-In breach-notification "
                        "enforcement, RBI data-localisation actions, CCI data fines and "
                        "international GDPR actions affecting Indian companies. Every entry "
                        "carries a provenance label."),
        "url": BASE_URL + "/",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "KensaraAI",
                    "legalName": "KensaraAI Private Limited", "url": "https://kensara.in"},
        "publisher": {"@type": "Organization", "name": "KensaraAI", "url": "https://kensara.in"},
        "dateModified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "spatialCoverage": {"@type": "Place", "name": "India"},
        "temporalCoverage": "2017/..",
        "keywords": ["DPDPA", "data protection enforcement India", "CERT-In",
                     "IT Act 43A", "MeitY", "data privacy penalty India"],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{BASE_URL}/data/enforcement.json"},
            {"@type": "DataDownload", "encodingFormat": "text/csv",
             "contentUrl": f"{BASE_URL}/data/enforcement.csv"},
        ],
        "variableMeasured": ["authority", "company", "sector", "violation_type",
                             "legal_provision", "penalty", "outcome", "trust_tier"],
        "size": f"{stats['total']} records",
    }, ensure_ascii=False, indent=2)


def case_jsonld(e: RenderEvent) -> str:
    citations = [{"@type": "CreativeWork", "url": s.url} for s in e.sources if s.url]
    doc = {
        "@context": "https://schema.org",
        "@type": "Article",
        "@id": f"{BASE_URL}/{e.url_path}#record",
        "headline": f"{e.company} — {e.authority}",
        "description": e.summary[:300],
        "datePublished": e.date or None,
        "dateModified": e.updated_at or e.date or None,
        "isPartOf": {"@id": f"{BASE_URL}/#dataset"},
        "publisher": {"@type": "Organization", "name": "KensaraAI", "url": "https://kensara.in"},
        "about": [
            {"@type": "Organization", "name": e.company},
            {"@type": "GovernmentOrganization", "name": e.authority},
        ],
        "mainEntityOfPage": f"{BASE_URL}/{e.url_path}",
    }
    if citations:
        doc["citation"] = citations
    if e.statute_ref:
        doc["about"].append({"@type": "Legislation", "name": e.statute_ref})
    return json.dumps({k: v for k, v in doc.items() if v is not None},
                      ensure_ascii=False, indent=2)


# ── Emitters ──────────────────────────────────────────────────────────────
def write_csv(events: list[RenderEvent], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "slug", "date", "authority", "company", "sector", "section",
                    "violation_type", "legal_provision", "penalty", "penalty_inr",
                    "outcome", "trust_tier", "url", "sources"])
        for e in events:
            w.writerow([e.id, e.slug, e.date, e.authority, e.company, e.sector, e.section,
                        e.violation_type, e.statute_ref, e.penalty_display, e.penalty_inr,
                        e.outcome, e.trust_tier, f"{BASE_URL}/{e.url_path}",
                        " | ".join(s.url for s in e.sources)])


def write_sitemap(events: list[RenderEvent], path: Path, entities: list | None = None) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{BASE_URL}/</loc><lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for e in events:
        urls.append(
            f"  <url><loc>{BASE_URL}/{e.url_path}</loc>"
            f"<lastmod>{e.updated_at or today}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.8</priority></url>")
    for ent in entities or []:
        urls.append(
            f"  <url><loc>{BASE_URL}/{ent.url_path}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>0.7</priority></url>")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")


def write_robots(path: Path) -> None:
    """Explicitly WELCOME AI crawlers — being cited is the whole strategy."""
    path.write_text(f"""# Being cited by search and generative engines is the point of this dataset.
# All well-behaved crawlers, including AI crawlers, are explicitly welcome.

User-agent: *
Allow: /
Disallow: /admin.html
Disallow: /admin

User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

User-agent: Applebot-Extended
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
""", encoding="utf-8")


def write_llms_txt(events: list[RenderEvent], stats: dict, path: Path) -> None:
    lines = [
        "# DPDPA Enforcement Tracker India — KensaraAI",
        "",
        f"> A public, continuously-maintained database of {stats['total']} Indian data-protection "
        "enforcement actions: DPDPA 2023, IT Act Section 43A/72A, CERT-In breach-notification "
        "enforcement, RBI data-localisation actions, CCI data fines, and international GDPR "
        "actions affecting Indian companies. Maintained by KensaraAI Private Limited.",
        "",
        "## Provenance",
        "Every entry carries a trust label:",
        "- **Primary source confirmed** — an official document from the issuing authority was retrieved and matched.",
        "- **Press reported** — reported by named news sources; no primary document attached yet.",
        "Entries under internal review are never published.",
        "",
        "## Machine-readable data",
        f"- JSON: {BASE_URL}/data/enforcement.json",
        f"- CSV: {BASE_URL}/data/enforcement.csv",
        f"- Sitemap: {BASE_URL}/sitemap.xml",
        "",
        "## Licence",
        "CC BY 4.0 — free to use with attribution to KensaraAI (https://kensara.in).",
        "",
        "## Records",
    ]
    for e in events:
        pen = f" — {e.penalty_display}" if e.penalty_display else ""
        lines.append(f"- [{e.company} — {e.authority} ({e.date})]({BASE_URL}/{e.url_path}): "
                     f"{e.violation_type or e.section_label}{pen}. {e.outcome}.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def related_for(e: RenderEvent, events: list[RenderEvent], limit: int = 4) -> list[RenderEvent]:
    """Interlinking: same authority first, then same sector."""
    same_auth = [o for o in events if o.slug != e.slug and o.authority == e.authority]
    same_sector = [o for o in events if o.slug != e.slug and o.sector == e.sector
                   and o not in same_auth]
    return (same_auth + same_sector)[:limit]


# ── Orchestrator ──────────────────────────────────────────────────────────
def _fmt_inr(total: float) -> str:
    if not total:
        return ""
    if total >= 1_00_00_000:
        return f"₹{total / 1_00_00_000:,.2f} Cr".replace(".00", "")
    if total >= 1_00_000:
        return f"₹{total / 1_00_000:,.2f} Lakh".replace(".00", "")
    return f"₹{total:,.0f}"


def render_entity_pages(graph, env, site) -> int:
    """Entity pages — pulled forward from Phase 4.

    Entities are the expensive part of the graph; once resolved, these pages are
    nearly free and multiply the long-tail surface while the window is open.
    """
    tmpl = env.get_template("entity.html")
    root = WEB / "entity"
    root.mkdir(parents=True, exist_ok=True)
    type_labels = {"company": "Organisation", "regulator": "Regulator", "court": "Court"}
    written = 0

    for ent in graph.pageable:
        evs = graph.entity_events(ent)
        if not evs:
            continue
        evs.sort(key=lambda g: g.event.date or "", reverse=True)
        years = [g.event.year for g in evs if g.event.year.isdigit()]
        authorities = {a.name for g in evs for a in g.authorities}
        total = sum(g.event.penalty_inr or 0 for g in evs)

        related = []
        for g in evs:
            if g.subject and g.subject.key != ent.key:
                related.append(g.subject)
            for a in g.authorities:
                if a.key != ent.key:
                    related.append(a)
        seen, uniq = set(), []
        for r in related:
            if r.key not in seen and r.entity_type in {"company", "regulator", "court"}:
                seen.add(r.key)
                uniq.append(r)

        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Organization" if ent.entity_type == "company" else "GovernmentOrganization",
            "@id": f"{BASE_URL}/{ent.url_path}#entity",
            "name": ent.name,
            "alternateName": sorted(ent.aliases) or None,
            "subjectOf": [{"@type": "Article", "url": f"{BASE_URL}/{g.event.url_path}"}
                          for g in evs],
        }, ensure_ascii=False, indent=2)

        html = tmpl.render(
            site=site, ent=ent, events=evs,
            type_label=type_labels.get(ent.entity_type, "Entity"),
            total_penalty=_fmt_inr(total), authorities=sorted(authorities),
            first_year=min(years) if years else "—", last_year=max(years) if years else "—",
            related_entities=uniq[:12], jsonld=jsonld)
        d = root / ent.slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
        written += 1
    return written


def render_site() -> dict:
    from src.graph.build import build_graph, persist

    graph = build_graph()
    events = [ge.event for ge in graph.events]
    if not events:
        log.warning("render.no_events")
        return {"status": "skipped", "reason": "no_events"}
    by_slug = {ge.event.slug: ge for ge in graph.events}

    stats, grouped = build_stats(events)
    env = _env()
    site = {"base_url": BASE_URL,
            "last_updated": datetime.now(timezone.utc).strftime("%d %B %Y")}

    # Tracker index
    index_html = env.get_template("index.html").render(
        site=site, stats=stats, grouped=grouped, section_order=SECTION_ORDER,
        section_badge=SECTION_BADGE, section_titles=SECTION_LABELS,
        section_subtitles=SECTION_SUBTITLES, jsonld=dataset_jsonld(stats))
    (WEB / "index.html").write_text(index_html, encoding="utf-8")

    # Case dossiers — one directory per case so the URL has no .html suffix
    case_root = WEB / "enforcement"
    case_root.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("case.html")
    live_slugs = {e.slug for e in events}
    for e in events:
        ge = by_slug.get(e.slug)
        html = tmpl.render(site=site, e=e, related=related_for(e, events),
                           jsonld=case_jsonld(e),
                           subject=ge.subject if ge else None,
                           authorities=ge.authorities if ge else [],
                           contradictions=ge.contradictions if ge else [])
        d = case_root / e.slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")

    # Prune pages whose case disappeared, but NEVER silently: a removed URL
    # breaks citations, so it is logged loudly.
    for child in case_root.iterdir():
        if child.is_dir() and child.name not in live_slugs:
            log.warning("render.stale_case_page", slug=child.name,
                        note="case no longer published; page left in place to avoid a 404")

    # Entity pages (Phase 1 graph → long-tail surface)
    entity_pages = render_entity_pages(graph, env, site)

    # Machine surfaces
    write_csv(events, WEB / "data" / "enforcement.csv")
    write_sitemap(events, WEB / "sitemap.xml", entities=graph.pageable)
    write_robots(WEB / "robots.txt")
    write_llms_txt(events, stats, WEB / "llms.txt")

    persist(graph)  # best-effort; never required

    result = {"status": "ok", "events": len(events), "entities": len(graph.entities),
              "entity_pages": entity_pages, "pages": len(events) + entity_pages + 1,
              "contradictions": sum(len(g.contradictions) for g in graph.events),
              "primary_confirmed": stats["primary_confirmed"]}
    log.info("render.done", **result)
    return result


if __name__ == "__main__":
    structlog.configure(processors=[structlog.processors.add_log_level,
                                    structlog.dev.ConsoleRenderer()])
    print(render_site())
