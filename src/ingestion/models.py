"""Shared lightweight data structures for ingested items."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RawItem:
    """A single ingested article/notice before scoring or extraction."""

    source: str
    title: str
    url: str
    summary: str = ""
    published: str = ""  # ISO date string when known

    def text(self) -> str:
        return f"{self.title} {self.summary}".strip()

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
