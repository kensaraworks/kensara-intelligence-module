"""Slack / Discord webhook alerting for high-scoring stories."""
from __future__ import annotations

import httpx
import structlog

from src.config import settings

log = structlog.get_logger(__name__)


async def send_alert(title: str, url: str, score: int, source: str) -> None:
    text = f":rotating_light: *Regulatory Alert* (score {score})\n<{url}|{title}>\n_source: {source}_"
    if settings.slack_webhook_url:
        await _post(settings.slack_webhook_url, {"text": text})
    if settings.discord_webhook_url:
        await _post(settings.discord_webhook_url, {"content": text})


async def _post(webhook: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(webhook, json=payload)
    except Exception as exc:  # pragma: no cover - network
        log.warning("alert.failed", error=str(exc))
