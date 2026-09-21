"""Read published rows using the PUBLIC anon key.

The renderer needs published cases, which the anon key can already read through
the RLS-guarded `enforcement_public` view. Using it means local runs and CI jobs
without the service key still render the real, live dataset instead of drifting
to a stale snapshot.

These values are public by design — they already ship in web/assets/tracker.js.
Env vars override them.
"""
from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger(__name__)

PUBLIC_URL = os.getenv("SUPABASE_URL", "https://cqjjmednofcdjrigjaer.supabase.co").rstrip("/")
PUBLIC_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxamptZWRub2ZjZGpyaWdqYWVyIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3ODk4MTYyMzIsImV4cCI6MjEwNTM5MjIzMn0."
    "OhVpRSjByOA7L__Ew94LxYp-xREhQjMu-LUx4zeT9Dg",
)

# Columns added in later phases may not exist yet if the schema hasn't been
# re-run, so we degrade to a base set rather than failing the whole render.
_FULL = ("id,slug,section,date,authority,company,sector,violation_type,dpdpa_section,"
         "summary,penalty_amount,penalty_amount_inr,outcome,source_url,"
         "official_source_url,sources,trust_tier,updated_at")
_BASE = ("id,section,date,authority,company,sector,violation_type,dpdpa_section,"
         "summary,penalty_amount,penalty_amount_inr,outcome,source_url,updated_at")
_MINIMAL = "id,section,date,authority,company,sector,violation_type,summary,penalty_amount,outcome,source_url"


def fetch_published() -> list[dict]:
    if not PUBLIC_URL or not PUBLIC_ANON_KEY:
        return []
    headers = {"apikey": PUBLIC_ANON_KEY, "Authorization": f"Bearer {PUBLIC_ANON_KEY}"}
    url = f"{PUBLIC_URL}/rest/v1/enforcement_public"
    for columns in (_FULL, _BASE, _MINIMAL):
        try:
            with httpx.Client(timeout=25) as c:
                r = c.get(url, headers=headers,
                          params={"select": columns, "order": "date.desc"})
            if r.status_code == 400:      # a column doesn't exist yet
                continue
            r.raise_for_status()
            rows = r.json()
            if isinstance(rows, list):
                if columns is not _FULL:
                    log.info("public_read.degraded",
                             note="schema not fully applied; some columns unavailable")
                return rows
        except Exception as exc:
            log.warning("public_read.failed", error=str(exc))
            return []
    return []
