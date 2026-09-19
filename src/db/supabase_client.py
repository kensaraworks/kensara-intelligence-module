"""Minimal Supabase (PostgREST) client over httpx.

We deliberately avoid the official ``supabase`` SDK: it pulls a large
dependency tree and we only need a handful of REST verbs. The pipeline uses
the *service* key (bypasses RLS). If Supabase isn't configured, every method
degrades to a no-op so the pipeline can still run locally and emit JSON.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.config import settings

log = structlog.get_logger(__name__)


class SupabaseClient:
    def __init__(self, url: str = "", key: str = "") -> None:
        self.url = (url or settings.supabase_url).rstrip("/")
        self.key = key or settings.supabase_service_key
        self.rest = f"{self.url}/rest/v1" if self.url else ""

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    # ── Reads ─────────────────────────────────────────────────────────────
    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        params: dict[str, Any] = {"select": columns}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        try:
            with httpx.Client(timeout=30) as c:
                r = c.get(f"{self.rest}/{table}", headers=self._headers(), params=params)
                r.raise_for_status()
                return r.json()
        except Exception as exc:  # pragma: no cover - network
            log.warning("supabase.select_failed", table=table, error=str(exc))
            return []

    # ── Upsert (insert or merge on conflict) ──────────────────────────────
    def upsert(
        self,
        table: str,
        rows: list[dict[str, Any]] | dict[str, Any],
        *,
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            return []
        resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
        prefer = f"return=representation,resolution={resolution}"
        params = {"on_conflict": on_conflict} if on_conflict else {}
        try:
            with httpx.Client(timeout=45) as c:
                r = c.post(
                    f"{self.rest}/{table}",
                    headers=self._headers(prefer),
                    params=params,
                    json=rows,
                )
                r.raise_for_status()
                return r.json() if r.text else []
        except Exception as exc:  # pragma: no cover - network
            log.warning("supabase.upsert_failed", table=table, error=str(exc))
            return []

    # ── Update ────────────────────────────────────────────────────────────
    def update(
        self, table: str, patch: dict[str, Any], filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            with httpx.Client(timeout=30) as c:
                r = c.patch(
                    f"{self.rest}/{table}",
                    headers=self._headers("return=representation"),
                    params=filters,
                    json=patch,
                )
                r.raise_for_status()
                return r.json() if r.text else []
        except Exception as exc:  # pragma: no cover - network
            log.warning("supabase.update_failed", table=table, error=str(exc))
            return []

    def delete(self, table: str, filters: dict[str, str]) -> bool:
        if not self.configured:
            return False
        try:
            with httpx.Client(timeout=30) as c:
                r = c.delete(f"{self.rest}/{table}", headers=self._headers(), params=filters)
                r.raise_for_status()
                return True
        except Exception as exc:  # pragma: no cover - network
            log.warning("supabase.delete_failed", table=table, error=str(exc))
            return False


# Shared singleton for the pipeline (service key).
db = SupabaseClient()
