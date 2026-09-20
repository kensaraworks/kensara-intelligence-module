"""Publish the public snapshot as a static JSON file.

The static front-end reads ``web/data/enforcement.json`` directly (fast, cached,
$0, works even if Supabase is briefly unreachable). The pipeline regenerates it
after every verified change and commits it (the GitHub Action does the commit).
The site can *also* live-query Supabase's ``enforcement_public`` view for the
freshest data — the JSON is the resilient baseline.
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from src.db import store

log = structlog.get_logger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "web" / "data" / "enforcement.json"


def _data_signature(snapshot: dict) -> str:
    """Stable serialisation of everything EXCEPT the volatile metadata block."""
    return json.dumps(
        {"statistics": snapshot["statistics"],
         "sector_counts": snapshot["sector_counts"],
         "sections": snapshot["sections"]},
        sort_keys=True, ensure_ascii=False,
    )


def write_snapshot(path: Path | str = DEFAULT_PATH) -> Path:
    snapshot = store.build_public_snapshot()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            # Safety: never overwrite a non-empty baseline with an empty snapshot.
            # An empty read is almost always a transient DB error, not a real
            # "zero published cases" — refuse to wipe the committed tracker.
            new_total = snapshot["statistics"]["total_all_sections"]
            old_total = existing.get("statistics", {}).get("total_all_sections", 0)
            if new_total == 0 and old_total > 0:
                log.warning("snapshot.refused_empty_overwrite", existing_total=old_total)
                return path
            # Idempotency: if only the timestamp would change, leave it untouched
            # so scheduled runs don't produce a stream of no-op commits.
            if _data_signature(existing) == _data_signature(snapshot):
                log.info("snapshot.unchanged", path=str(path))
                return path
        except Exception:
            pass

    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("snapshot.written", path=str(path),
             total=snapshot["statistics"]["total_all_sections"])
    return path


if __name__ == "__main__":
    write_snapshot()
