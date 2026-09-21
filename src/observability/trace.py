"""Pipeline trace — makes every stage inspectable.

A pipeline that silently drops 1,100 of 2,242 items is unauditable. This runs
the real sensing pipeline while recording, for every item, which stage it died
at and why — then writes a JSON artifact that the static inspection lab renders.

No server: `python -m src.main trace` → web/data/pipeline-trace.json → /lab.

Also captures the CRAWLER VIEW: what a JavaScript-less bot (GPTBot, ClaudeBot,
PerplexityBot, CCBot) actually receives, which is the thing the whole citation
strategy depends on and the easiest thing to break without noticing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
TRACE_PATH = WEB / "data" / "pipeline-trace.json"

MAX_ITEMS_RECORDED = 1200   # keep the artifact a reasonable size


def _crawler_view() -> dict:
    """What a bot that does not run JavaScript sees in the rendered HTML."""
    out: dict = {"pages": [], "robots": {}, "llms_txt": False}

    def inspect(rel: str, label: str) -> dict | None:
        p = WEB / rel
        if not p.exists():
            return None
        html = p.read_text(encoding="utf-8", errors="ignore")
        # Strip script/style, then tags — this approximates a non-JS crawler.
        body = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", body)
        text = " ".join(text.split())
        return {
            "path": "/" + rel.replace("index.html", "").rstrip("/"),
            "label": label,
            "html_bytes": len(html),
            "visible_text_chars": len(text),
            "case_rows": html.count('class="table-row-hover"'),
            "headings": re.findall(r"<h[12][^>]*>(.*?)</h[12]>", body, flags=re.S)[:6],
            "jsonld_blocks": html.count('application/ld+json'),
            "has_canonical": 'rel="canonical"' in html,
            "text_preview": text[:600],
            "js_dependent": "fetch(" in html and html.count('class="table-row-hover"') == 0,
        }

    for rel, label in [
        ("index.html", "Tracker index"),
        ("dpdpa/index.html", "DPDPA statute index"),
        ("penalties/index.html", "Penalty database"),
        ("calendar/index.html", "Regulatory calendar"),
    ]:
        got = inspect(rel, label)
        if got:
            out["pages"].append(got)

    first_case = next((p for p in (WEB / "enforcement").glob("*/index.html")), None)
    if first_case:
        got = inspect(str(first_case.relative_to(WEB)).replace("\\", "/"), "Case dossier (sample)")
        if got:
            out["pages"].append(got)

    robots = WEB / "robots.txt"
    if robots.exists():
        txt = robots.read_text(encoding="utf-8")
        agents = re.findall(r"User-agent:\s*(\S+)", txt)
        out["robots"] = {
            "ai_crawlers_allowed": [a for a in agents if a != "*"],
            "disallowed": re.findall(r"Disallow:\s*(\S+)", txt),
            "has_sitemap": "Sitemap:" in txt,
        }
    out["llms_txt"] = (WEB / "llms.txt").exists()
    return out


async def _deep_trace(candidates, limit: int) -> list[dict]:
    """Extraction + verification, recorded per candidate.

    Opt-in because these are the only stages that cost anything: an LLM call per
    candidate and a document fetch per verification. Nothing is written to the
    database — this is a diagnostic, not a pipeline run.
    """
    from src.processing import llm_extractor
    from src.processing.feedback import ReviewMemory
    from src.processing.fulltext import fetch_article_text_smart
    from src.verification.verify import Verifier

    memory = ReviewMemory.load()
    few_shot = memory.few_shot_block()
    verifier = Verifier(archive=False)     # never archive from a diagnostic run
    out: list[dict] = []

    for item in candidates[:limit]:
        rec: dict = {"title": item.title, "url": item.url, "source": item.source,
                     "stages": []}

        full_text, ft = await fetch_article_text_smart(item, fallback=item.summary)
        rec["stages"].append({
            "stage": "Full-text fetch",
            # An aggregator link we could not resolve means the model only ever
            # saw the RSS snippet — the silent quality killer this surfaced.
            "ok": bool(full_text) and not (ft["aggregator"] and not ft["resolved_url"]),
            "detail": f"{ft['chars']} chars — {ft['note']}",
            "official_url": ft["resolved_url"],
            "preview": (full_text or item.summary or "")[:400],
        })

        diag: dict = {}
        ex = await llm_extractor.extract_enforcement(
            item.title, item.summary, item.url, full_text=full_text,
            few_shot=few_shot, diag=diag)
        rec["extraction"] = diag
        rec["stages"].append({
            "stage": "LLM extraction",
            "ok": ex is not None,
            "detail": {
                "extracted": f"genuine enforcement (via {diag.get('provider') or 'heuristic'})",
                "rejected_not_enforcement":
                    "model judged this NOT an enforcement action",
                "heuristic_extracted": "no LLM key — heuristic kept it as a lead",
                "heuristic_rejected": "no LLM key — heuristic found no action signal",
                "no_provider": "no provider answered",
            }.get(diag.get("outcome"), diag.get("outcome", "")),
            "fields": diag.get("fields"),
        })

        if ex is None:
            rec["outcome"] = "discarded_at_extraction"
            out.append(rec)
            continue

        if memory.is_known_false_positive(ex.company, ex.authority):
            rec["stages"].append({"stage": "False-positive memory", "ok": False,
                                  "detail": "matches a signature a reviewer "
                                            "previously discarded"})
            rec["outcome"] = "skipped_known_false_positive"
            out.append(rec)
            continue

        vr = await verifier.verify(
            company=ex.company, authority=ex.authority, penalty=ex.penalty_amount,
            date=item.published or "", source_urls=[item.url],
            violation=ex.violation_type)
        m = vr.match
        rec["verification"] = vr.summary()
        rec["stages"].append({
            "stage": "Verification",
            "ok": vr.trust_tier == "primary_confirmed",
            "detail": (
                f"official document opened and matched ({m.strength})"
                if m and m.verified else
                ("official source found but it does NOT substantiate the claim"
                 if vr.official_url else "no official source located")),
            "checks": {
                "entity_matched": bool(m and m.entity_matched),
                "amount_matched": bool(m and m.amount_matched),
                "date_matched": bool(m and m.date_matched),
            } if m else None,
            "reasons": (m.reasons if m else vr.notes),
            "official_url": vr.official_url,
            "excerpt": (vr.evidence.excerpt if vr.evidence else ""),
        })
        rec["outcome"] = f"candidate_row:{vr.trust_tier}"
        out.append(rec)

    return out


async def run_trace(tier: int = 2, include_watchlist: bool = True,
                    deep: bool = False, deep_limit: int = 8) -> dict:
    """Run the sensing pipeline with full per-item instrumentation."""
    from src.config import settings
    from src.processing.dedup import Deduplicator
    from src.processing.scoring import (calculate_relevance_score, score_breakdown,
                                    tracked_entity_names)
    from src.sensing import fetchers, prefilter
    from src.sensing.registry import sources_upto_tier, stats as registry_stats
    from src.sensing.sweep import load_seen, save_seen

    sources = sources_upto_tier(tier)
    if include_watchlist:
        try:
            from src.sensing.expansion import build_watchlist
            sources = sources + build_watchlist()
        except Exception as exc:
            log.warning("trace.watchlist_failed", error=str(exc))

    primary_domains = {s.domain for s in sources if s.is_primary_source and s.domain}
    always_domains = {s.domain for s in sources if s.always_relevant and s.domain}
    seen = load_seen()

    # ── Stage 1: sensing ────────────────────────────────────────────────
    results = await fetchers.fetch_all(sources, seen)
    raw, health = [], []
    for r in results:
        health.append({
            "source": r.source.name, "kind": r.source.kind, "tier": r.source.tier,
            "status": r.status, "items": r.count, "detail": r.detail,
            "is_primary_source": r.source.is_primary_source,
            "always_relevant": r.source.always_relevant,
            "url": r.source.resolved_url()[:160],
        })
        raw.extend(r.items)

    records: dict[str, dict] = {}
    for it in raw:
        if it.url and it.url not in records:
            records[it.url] = {
                "title": it.title, "url": it.url, "source": it.source,
                "published": it.published, "summary": (it.summary or "")[:280],
                "stage": "sensed", "exited_at": None, "reason": None, "score": None,
            }

    # ── Stage 2: already seen ───────────────────────────────────────────
    known = {u for u in records if u in seen}
    for u in known:
        records[u].update(stage="dropped", exited_at="seen_filter",
                          reason="already ingested in a previous run")
    fresh = [it for it in raw if it.url and it.url not in known]
    fresh_unique = {it.url for it in fresh}

    # ── Stage 3: near-duplicate suppression ─────────────────────────────
    dedup = Deduplicator(threshold=settings.dedup_threshold)
    unique = []
    for it in fresh:
        is_dup, sim, _fp = dedup.is_duplicate(it.text())
        if is_dup:
            records[it.url].update(stage="dropped", exited_at="dedup",
                                   reason=f"near-duplicate (cosine {sim:.2f})")
        else:
            unique.append(it)

    # ── Stage 4: deterministic pre-filter ───────────────────────────────
    pf_trace: list[dict] = []
    kept, rejections = prefilter.filter_items(unique, primary_domains,
                                              always_domains, trace=pf_trace)
    for v in pf_trace:
        rec = records.get(v["url"])
        if not rec:
            continue
        rec["is_primary_source"] = v["is_primary_source"]
        rec["priority"] = v["priority"]
        if not v["kept"]:
            rec.update(stage="dropped", exited_at="prefilter", reason=v["reason"])
        else:
            rec["stage"] = "passed_prefilter"

    # ── Stage 5: scoring + cap ──────────────────────────────────────────
    tracked = tracked_entity_names()
    scored = []
    for it in kept:
        s = calculate_relevance_score(it.title, it.summary, it.source, it.published, tracked)
        records[it.url]["score"] = s
        scored.append((s, it))
    scored.sort(key=lambda t: t[0], reverse=True)
    limit = settings.max_candidates_per_sweep
    candidates = [it for _s, it in scored[:limit]]
    deferred = [it for _s, it in scored[limit:]]
    cand_urls = {it.url for it in candidates}
    for it in kept:
        if it.url in cand_urls:
            records[it.url].update(stage="candidate")
            records[it.url]["breakdown"] = score_breakdown(
                it.title, it.summary, it.source, it.published)
        else:
            # Deferred, NOT dropped: the cap bounds spend, it does not judge.
            records[it.url].update(
                stage="deferred", exited_at="spend_cap",
                reason=f"outside top {limit} this run — queued for the next sweep")

    from src.sensing.backlog import save_backlog
    save_backlog(deferred)
    for it in candidates:          # only extraction counts as processed
        if it.url:
            seen.add(it.url)
    save_seen(seen)

    funnel = [
        {"stage": "Sensed", "count": len(records),
         "note": f"{len(sources)} sources, 0 paid API calls"},
        {"stage": "Unseen", "count": len(fresh_unique),
         "note": f"{len(known)} already processed"},
        {"stage": "Deduplicated", "count": len(unique),
         "note": f"{len(fresh_unique) - len(unique)} near-duplicates suppressed"},
        {"stage": "Passed pre-filter", "count": len(kept),
         "note": f"{sum(rejections.values())} rejected before any LLM call"},
        {"stage": "Candidates", "count": len(candidates),
         "note": f"cap = top {limit}; {len(deferred)} deferred to backlog, not lost"},
    ]

    deep_records: list[dict] = []
    if deep:
        log.info("trace.deep_start", candidates=min(len(candidates), deep_limit))
        deep_records = await _deep_trace(candidates, deep_limit)

    trace = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deep": deep,
        "deep_records": deep_records,
        "config": {
            "tier": tier, "watchlist": include_watchlist,
            "max_candidates_per_sweep": limit,
            "dedup_threshold": settings.dedup_threshold,
            "article_max_chars": settings.article_max_chars,
            "llm_available": settings.has_llm,
            "grounding_available": settings.has_search,
        },
        "registry": registry_stats(),
        "funnel": funnel,
        "rejections": rejections,
        "sources": sorted(health, key=lambda h: (h["status"] != "ok", -h["items"])),
        "items": sorted(records.values(),
                        key=lambda r: ({"candidate": 0, "deferred": 1}.get(r["stage"], 2),
                                       -(r.get("score") or -99)))[:MAX_ITEMS_RECORDED],
        "crawler_view": _crawler_view(),
    }
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("trace.written", path=str(TRACE_PATH), items=len(trace["items"]),
             candidates=len(candidates), deep=len(deep_records))
    return {"status": "ok", "path": str(TRACE_PATH), "items": len(records),
            "candidates": len(candidates), "sources": len(sources),
            "deep_records": len(deep_records)}
