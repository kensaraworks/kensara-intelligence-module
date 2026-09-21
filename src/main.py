"""CLI orchestrator for the intelligence pipeline.

Usage (locally or in GitHub Actions):
    python -m src.main enforcement     # weekly enforcement sweep + LLM extract
    python -m src.main news            # deep news + regulatory poll
    python -m src.main news-quick      # RSS-only quick poll (4-hourly)
    python -m src.main competitor      # weekly competitor crawl
    python -m src.main brief           # weekly executive brief + trend aggregates
    python -m src.main reverify        # re-check stale open cases for updates
    python -m src.main angles          # story -> SEO content angles
    python -m src.main snapshot        # rebuild JSON snapshot + re-render static site
    python -m src.main render          # re-render the static site only
    python -m src.main graph           # rebuild the knowledge graph (idempotent)
    python -m src.main all             # run everything (handy for first seed)
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from src.agents.brief import generate_brief
from src.agents.competitor_intel import run_competitor_intelligence
from src.agents.content_angles import generate_content_angles
from src.agents.enforcement_tracker import update_enforcement_tracker
from src.agents.news_scan import run_news_scan
from src.agents.reverify import run_reverification
from src.config import settings
from src.publish.snapshot import publish_all, write_snapshot

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("main")


async def run_regulatory_poll() -> dict:
    """Alias used by the 4-hour quick-poll workflow (RSS-only, fast)."""
    return await run_news_scan(deep=False)


async def _dispatch(cmd: str) -> None:
    log.info("startup", command=cmd, supabase=settings.supabase_ready,
             search=settings.has_search, llm=settings.has_llm)

    if cmd == "enforcement":
        print(await update_enforcement_tracker())
    elif cmd == "news":
        print(await run_news_scan(deep=True))
    elif cmd in {"news-quick", "poll"}:
        print(await run_news_scan(deep=False))
    elif cmd == "competitor":
        print(await run_competitor_intelligence())
    elif cmd == "brief":
        print(await generate_brief())
    elif cmd == "reverify":
        print(await run_reverification())
    elif cmd == "angles":
        print(await generate_content_angles())
    elif cmd == "snapshot":
        print(publish_all())
    elif cmd == "graph":
        from src.graph.build import build_graph, persist
        g = build_graph()
        print({"events": len(g.events), "entities": len(g.entities),
               "pageable": len(g.pageable), "persist": persist(g)})
    elif cmd == "render":
        from src.publish.render import render_site
        print(render_site())
    elif cmd == "all":
        print(await run_news_scan(deep=True))
        print(await update_enforcement_tracker())
        print(await run_competitor_intelligence())
        print(await generate_content_angles())
        print(await generate_brief())
    else:
        print(__doc__)
        sys.exit(1)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    asyncio.run(_dispatch(cmd))


if __name__ == "__main__":
    main()
