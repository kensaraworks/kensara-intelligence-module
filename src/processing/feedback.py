"""Human-review feedback loop (#4).

Every verify/discard the reviewer makes is training signal. We use it two ways:
  • False-positive memory — skip candidates whose signature was discarded before.
  • Few-shot conditioning — show the extractor a handful of the reviewer's past
    accept/reject examples so it learns *your* bar for "genuine enforcement".

Everything is cheap: a small table read, a few examples appended to the prompt.
"""
from __future__ import annotations

import structlog

from src.config import settings
from src.db import store
from src.processing.signature import make_signature

log = structlog.get_logger(__name__)


class ReviewMemory:
    """Loaded once per sweep from recent reviewer decisions."""

    def __init__(self, fp_signatures: set[str], examples: list[dict]) -> None:
        self.fp_signatures = fp_signatures
        self.examples = examples

    @classmethod
    def load(cls) -> "ReviewMemory":
        try:
            fp = store.false_positive_signatures()
            decisions = store.recent_decisions(limit=60)
        except Exception as exc:  # never block the pipeline
            log.warning("feedback.load_failed", error=str(exc))
            return cls(set(), [])
        return cls(fp, decisions)

    def is_known_false_positive(self, company: str, authority: str) -> bool:
        return make_signature(company, authority) in self.fp_signatures

    def few_shot_block(self) -> str:
        """Render up to N past decisions as guidance for the extractor prompt."""
        if not self.examples:
            return ""
        n = settings.few_shot_examples
        lines = []
        for d in self.examples[:n]:
            verdict = "GENUINE ENFORCEMENT" if d.get("decision") == "verified" else "NOT ENFORCEMENT (rejected by reviewer)"
            title = (d.get("title") or "")[:160]
            if title:
                lines.append(f"- \"{title}\" -> {verdict}")
        if not lines:
            return ""
        return (
            "\nReviewer-labelled precedents (match this editorial bar):\n"
            + "\n".join(lines) + "\n"
        )
