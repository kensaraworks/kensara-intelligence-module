"""Re-verification of open cases (#7).

'Investigation Ongoing' / 'Consultation' cases go stale. This job re-checks a
bounded batch: one search per case for a status update, one short LLM judgement.
It always stamps last_reverified_at (so we don't recheck immediately) and updates
the outcome only when a change is detected. Falls back to a keyword heuristic
with no LLM key. Cheap and capped.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from src.config import settings
from src.db import store
from src.ingestion import search_sweep
from src.processing.grounding import is_trusted
from src.processing.llm import complete_text

log = structlog.get_logger(__name__)

_RESOLVED = {
    "Fine Imposed", "Compliance Achieved", "Business Ban / Restriction",
    "Adjudication Order Issued",
}
_RESOLVE_KW = ["fine of", "penalty of", "imposed a penalty", "ordered to pay",
               "dismissed", "closed the", "settled", "banned", "barred"]


async def _detect_update(case: dict) -> dict | None:
    """Return {outcome, official_source_url} if the case appears resolved."""
    if not settings.has_search:
        return None
    q = f'{case.get("company","")} {case.get("authority","")} penalty OR order OR outcome'
    results = await search_sweep.search(q, num=5)
    if not results:
        return None
    official = next((r.url for r in results if is_trusted(r.url)), "")
    corpus = " ".join(f"{r.title} {r.summary}" for r in results)[:2500]

    if settings.has_llm:
        prompt = (
            "A regulatory case is currently marked as open. Based ONLY on the search "
            "results below, has it been resolved? Reply with strict JSON: "
            '{"resolved": bool, "outcome": one of ["Fine Imposed","Compliance Achieved",'
            '"Business Ban / Restriction","Adjudication Order Issued","Investigation Ongoing"], '
            '"note": short string}.\n\n'
            f"Case: {case.get('company')} / {case.get('authority')} / {case.get('summary','')[:200]}\n\n"
            f"Search results:\n{corpus}"
        )
        raw = await complete_text(prompt, max_tokens=250)
        try:
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
            if data.get("resolved") and data.get("outcome") in _RESOLVED:
                return {"outcome": data["outcome"], "official_source_url": official,
                        "notes": data.get("note", "")[:300]}
        except Exception:
            pass
        return None

    # Heuristic fallback
    low = corpus.lower()
    if any(k in low for k in _RESOLVE_KW):
        return {"outcome": "Fine Imposed", "official_source_url": official,
                "notes": "Auto-flagged possible resolution — verify."}
    return None


async def run_reverification() -> dict:
    cases = store.open_published_cases(older_than_days=30, limit=15)  # bounded
    checked = updated = 0
    for case in cases:
        checked += 1
        patch = {"last_reverified_at": datetime.now(timezone.utc).isoformat()}
        change = await _detect_update(case)
        if change:
            patch.update(change)
            updated += 1
        store.update_case(case["id"], patch)

    if updated:
        from src.publish.snapshot import publish_all
        publish_all()
    store.log_run("reverify", "ok", detail=f"checked={checked} updated={updated}",
                  items_found=updated)
    result = {"status": "ok", "checked": checked, "updated": updated}
    log.info("reverify.done", **result)
    return result
