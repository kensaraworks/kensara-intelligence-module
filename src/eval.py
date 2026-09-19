"""Extractor eval harness (#8).

Measures precision / recall / F1 of the enforcement classifier against a labelled
set so every model or prompt change is *measured*, not guessed. Runs the real
extractor (with keys) or the deterministic heuristic (without). Pure stdlib —
no sklearn.

    python -m src.eval
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.config import settings
from src.processing.llm_extractor import extract_enforcement

EVAL_SET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval_set.json"


async def _predict(item: dict) -> bool:
    ex = await extract_enforcement(item["title"], item["snippet"], "https://eval.local/x")
    return ex is not None


def _metrics(tp: int, fp: int, tn: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    acc = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "accuracy": round(acc, 3),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn}


async def run_eval() -> dict:
    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    tp = fp = tn = fn = 0
    misses = []
    for item in data:
        pred = await _predict(item)
        gold = bool(item["label"])
        if pred and gold: tp += 1
        elif pred and not gold: fp += 1; misses.append(("FP", item["title"]))
        elif not pred and gold: fn += 1; misses.append(("FN", item["title"]))
        else: tn += 1
    m = _metrics(tp, fp, tn, fn)
    mode = settings.resolved_llm_provider() or "heuristic"
    print(f"\n=== Extractor eval ({mode}) — n={len(data)} ===")
    for k, v in m.items():
        print(f"  {k:10}: {v}")
    if misses:
        print("  misclassified:")
        for kind, title in misses:
            print(f"    [{kind}] {title}")
    return {"mode": mode, **m}


if __name__ == "__main__":
    asyncio.run(run_eval())
