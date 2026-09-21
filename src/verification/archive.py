"""Evidence archive — Wayback Machine instead of paid object storage.

The architecture originally called for GCS. Three reasons not to:
  1. It costs money and needs another credential.
  2. Our own copy of a document is weak evidence — we could have written it.
  3. web.archive.org is free, keyless, permanent, and INDEPENDENT, which is
     evidentially stronger if an entry is ever challenged.

We therefore archive a public URL with the Internet Archive and keep, in
Postgres, the fingerprint of what we actually read:
    SHA-256 of the fetched text · the matched excerpt · retrieval timestamp

That combination answers "what did the document say when you read it, and can
anyone else check?" — which is the whole point of an evidence trail.

Best-effort throughout: archiving never blocks or fails a pipeline run, and it
is capped per run so we stay a polite citizen of a free service.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

log = structlog.get_logger(__name__)

SAVE_ENDPOINT = "https://web.archive.org/save/"
AVAILABILITY_ENDPOINT = "https://archive.org/wayback/available"
MAX_ARCHIVES_PER_RUN = 10


@dataclass
class Evidence:
    url: str
    content_sha256: str
    excerpt: str
    retrieved_at: str
    archived_url: str = ""

    def as_row(self) -> dict:
        return {
            "url": self.url,
            "content_sha256": self.content_sha256,
            "excerpt": self.excerpt[:1000],
            "retrieved_at": self.retrieved_at,
            "archived_url": self.archived_url,
        }


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()


def existing_snapshot(url: str, timeout: int = 12) -> str:
    """Check for an existing Wayback capture — free and avoids re-archiving."""
    try:
        r = httpx.get(AVAILABILITY_ENDPOINT, params={"url": url}, timeout=timeout)
        r.raise_for_status()
        snap = (r.json().get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available") and snap.get("url"):
            return snap["url"]
    except Exception as exc:
        log.debug("archive.availability_failed", url=url, error=str(exc))
    return ""


def archive_url(url: str, timeout: int = 25) -> str:
    """Submit a public URL for permanent archival. Returns the snapshot URL."""
    if not url or not url.startswith("http"):
        return ""
    existing = existing_snapshot(url)
    if existing:
        return existing
    try:
        r = httpx.get(f"{SAVE_ENDPOINT}{url}", timeout=timeout,
                      follow_redirects=True,
                      headers={"User-Agent": "KensaraAI-EnforcementTracker/1.0"})
        if r.status_code in (200, 302):
            # The archived location comes back either as the final URL or header.
            loc = r.headers.get("Content-Location") or ""
            if loc:
                return f"https://web.archive.org{loc}"
            if "web.archive.org" in str(r.url):
                return str(r.url)
        log.debug("archive.save_unexpected", url=url, status=r.status_code)
    except Exception as exc:
        log.debug("archive.save_failed", url=url, error=str(exc))
    return ""


def build_evidence(url: str, document_text: str, excerpt: str,
                   archive: bool = True) -> Evidence:
    ev = Evidence(
        url=url,
        content_sha256=content_hash(document_text),
        excerpt=excerpt or "",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )
    if archive:
        ev.archived_url = archive_url(url)
    return ev
