"""Pure-Python TF-IDF cosine deduplication (no numpy/scikit needed).

Two-stage: (1) exact URL hash, (2) content similarity vs the recent corpus.
Syndicated cross-posts of the same story score high cosine similarity and are
suppressed. Keeps a rolling in-memory corpus during a single sweep and can be
seeded from recently-stored fingerprints.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "has",
    "have", "had", "it", "its", "this", "that", "these", "those", "will", "would",
    "can", "could", "may", "might", "said", "says", "new", "also", "more", "after",
    "over", "into", "about", "than", "then", "not", "no", "we", "you", "they",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS]


def fingerprint(text: str) -> dict[str, int]:
    """Word-frequency map — serialisable to JSONB for cross-run dedup."""
    return dict(Counter(tokenize(text)))


class Deduplicator:
    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = threshold
        self._corpus: list[dict[str, int]] = []
        self._df: Counter = Counter()  # document frequency per term
        self._n = 0

    def seed(self, fingerprints: list[dict[str, int]]) -> None:
        for fp in fingerprints:
            if fp:
                self._add_to_corpus(fp)

    def _add_to_corpus(self, fp: dict[str, int]) -> None:
        self._corpus.append(fp)
        self._n += 1
        for term in fp:
            self._df[term] += 1

    def _idf(self, term: str) -> float:
        return math.log((1 + self._n) / (1 + self._df.get(term, 0))) + 1.0

    def _tfidf_vec(self, fp: dict[str, int]) -> dict[str, float]:
        return {t: c * self._idf(t) for t, c in fp.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def is_duplicate(self, text: str) -> tuple[bool, float, dict[str, int]]:
        """Check text against corpus. Returns (is_dup, max_sim, fingerprint).

        On a non-duplicate the item is added to the corpus so later items in the
        same sweep are compared against it too.
        """
        fp = fingerprint(text)
        if not fp:
            return False, 0.0, fp
        vec = self._tfidf_vec(fp)
        max_sim = 0.0
        for existing in self._corpus:
            sim = self._cosine(vec, self._tfidf_vec(existing))
            if sim > max_sim:
                max_sim = sim
            if max_sim >= self.threshold:
                return True, max_sim, fp
        self._add_to_corpus(fp)
        return False, max_sim, fp
