"""Normalised signatures for case clustering (#2) and false-positive memory (#4).

Pure-python, no deps. A signature collapses trivially-different reports of the
same event to the same key so we cluster them and remember reviewer rejections.
"""
from __future__ import annotations

import re

_SUFFIX_RE = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|corp|corporation|company|co|plc|"
    r"technologies|technology|solutions|services|india|bank)\b",
    re.IGNORECASE,
)
_NONWORD_RE = re.compile(r"[^a-z0-9 ]+")


def normalize_company(name: str) -> str:
    n = (name or "").lower()
    n = _NONWORD_RE.sub(" ", n)
    n = _SUFFIX_RE.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _date_bucket(date: str) -> str:
    """Bucket to the month — same event reported over a few days still matches."""
    return (date or "")[:7]  # YYYY-MM


def make_signature(company: str, authority: str = "", date: str = "") -> str:
    parts = [normalize_company(company), (authority or "").lower().strip()]
    return "|".join(p for p in parts if p) or "unknown"


def cluster_key(company: str, authority: str, date: str, amount_inr: float = 0) -> str:
    """Tighter key for merging near-identical candidates within a sweep."""
    amt = ""
    try:
        amt = str(int(round(float(amount_inr) / 100000)))  # bucket to ~lakh
    except (TypeError, ValueError):
        amt = ""
    return "|".join([
        normalize_company(company),
        (authority or "").lower().strip()[:12],
        _date_bucket(date),
        amt,
    ])
