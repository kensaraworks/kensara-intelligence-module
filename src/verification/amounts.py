"""Indian monetary amount parsing and comparison.

Verification hinges on "does this official document actually state this penalty?"
— which is impossible without handling the many ways Indian regulators write a
number. All of these are the same amount:

    ₹5,00,000   Rs. 5 lakh   INR 500000   Rupees Five Lakh   0.05 crore

Indian grouping (lakh = 1e5, crore = 1e7) and Indian digit grouping (5,00,000
rather than 500,000) both have to be understood. Pure stdlib.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MULTIPLIERS = {
    "thousand": 1_000, "k": 1_000,
    "lakh": 1_00_000, "lakhs": 1_00_000, "lac": 1_00_000, "lacs": 1_00_000,
    "million": 10_00_000, "mn": 10_00_000, "m": 10_00_000,
    "crore": 1_00_00_000, "crores": 1_00_00_000, "cr": 1_00_00_000,
    "billion": 100_00_00_000, "bn": 100_00_00_000,
    "trillion": 1_00_000_00_00_000,
}

_CURRENCY = r"(?:₹|rs\.?|inr|rupees?|usd|\$|eur|€|£)"
_NUM = r"\d[\d,]*(?:\.\d+)?"
_MULT = "|".join(sorted(MULTIPLIERS, key=len, reverse=True))

# "₹5 crore", "Rs. 5,00,000", "5 lakh", "€1.2 billion"
AMOUNT_RE = re.compile(
    rf"(?P<cur>{_CURRENCY})?\s*(?P<num>{_NUM})\s*(?P<mult>{_MULT})?\b", re.I)

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "fifty": 50, "hundred": 100,
}
WORD_AMOUNT_RE = re.compile(
    rf"\b(?P<word>{'|'.join(_WORD_NUMS)})\s+(?P<mult>{_MULT})\b", re.I)


@dataclass(frozen=True)
class Amount:
    value: float          # in the smallest unit of its currency
    currency: str = "INR"
    raw: str = ""

    def close_to(self, other: "Amount", tolerance: float = 0.02) -> bool:
        """Equal within tolerance — rounding differs between order and press."""
        if not self.value or not other.value:
            return False
        if self.currency != other.currency:
            return False
        hi = max(self.value, other.value)
        return abs(self.value - other.value) / hi <= tolerance


def _currency_of(token: str | None) -> str:
    t = (token or "").lower().strip().rstrip(".")
    if t in ("$", "usd"):
        return "USD"
    if t in ("€", "eur"):
        return "EUR"
    if t in ("£", "gbp"):
        return "GBP"
    return "INR"


def parse_amounts(text: str) -> list[Amount]:
    """Every monetary amount in the text, normalised."""
    out: list[Amount] = []
    if not text:
        return out

    for m in AMOUNT_RE.finditer(text):
        num_s, mult, cur = m.group("num"), m.group("mult"), m.group("cur")
        if not cur and not mult:
            continue                       # a bare number is not an amount
        try:
            value = float(num_s.replace(",", ""))
        except ValueError:
            continue
        if mult:
            value *= MULTIPLIERS[mult.lower()]
        if value <= 0:
            continue
        out.append(Amount(value=value, currency=_currency_of(cur), raw=m.group(0).strip()))

    for m in WORD_AMOUNT_RE.finditer(text):
        value = _WORD_NUMS[m.group("word").lower()] * MULTIPLIERS[m.group("mult").lower()]
        out.append(Amount(value=value, currency="INR", raw=m.group(0).strip()))

    return out


def parse_amount(text: str) -> Amount | None:
    """The single most significant amount in a short string (e.g. a penalty field)."""
    amounts = parse_amounts(text)
    return max(amounts, key=lambda a: a.value) if amounts else None


def contains_amount(document_text: str, target: Amount, tolerance: float = 0.02) -> Amount | None:
    """Return the matching amount found in the document, if any."""
    for found in parse_amounts(document_text):
        if found.close_to(target, tolerance):
            return found
    return None
