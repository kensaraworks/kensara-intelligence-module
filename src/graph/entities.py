"""Entity resolution — deterministic first, LLM only for genuine ambiguity.

"Meta", "Meta Platforms", "WhatsApp / Meta" and "Facebook India" must resolve to
one entity, or the knowledge graph fragments and entity pages become useless.

Strategy, cheapest first:
  1. Curated alias map  — a small hand-list covers the entities that actually
     recur in Indian data-protection enforcement. Highest precision per rupee.
  2. Normalised key     — strip corporate suffixes, punctuation, case.
  3. Token overlap      — Jaccard similarity over token sets for near-matches.
  4. (Phase 2) LLM adjudication for the residual ambiguous pairs.

No LLM call is made here: resolution stays free, deterministic and reproducible,
which matters because the graph is rebuilt from scratch on every run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.publish.model import slugify

# ── Curated aliases: canonical name → variants seen in the wild ───────────
ALIAS_SEEDS: dict[str, list[str]] = {
    "Meta Platforms": ["meta", "facebook", "whatsapp meta", "whatsapp", "meta india",
                       "facebook india", "whatsapp llc"],
    "Reserve Bank of India": ["rbi", "reserve bank"],
    "Competition Commission of India": ["cci"],
    "Ministry of Electronics and Information Technology": ["meity", "ministry of electronics",
                                                           "ministry of electronics and it"],
    "CERT-In": ["cert in", "certin", "indian computer emergency response team"],
    "Securities and Exchange Board of India": ["sebi"],
    "Insurance Regulatory and Development Authority of India": ["irdai", "irda"],
    "Telecom Regulatory Authority of India": ["trai"],
    "Unique Identification Authority of India": ["uidai", "aadhaar authority"],
    "Data Protection Board of India": ["dpb", "dpbi", "data protection board"],
    "Supreme Court of India": ["supreme court", "sci", "hon'ble supreme court"],
    "Irish Data Protection Commission": ["irish dpc", "dpc ireland", "data protection commission"],
    "Star Health and Allied Insurance": ["star health", "star health allied insurance"],
    "American Express": ["amex", "american express diners club", "diners club"],
    "Mastercard": ["mastercard incorporated", "master card"],
    "LinkedIn": ["linkedin ireland", "linkedin corporation"],
}

# Authority strings that actually name several bodies.
_AUTHORITY_SPLIT = re.compile(r"\s*(?:/|&|\band\b|,)\s*")

REGULATORS = {
    "reserve bank of india", "competition commission of india", "cert-in",
    "securities and exchange board of india",
    "insurance regulatory and development authority of india",
    "telecom regulatory authority of india", "data protection board of india",
    "ministry of electronics and information technology",
    "unique identification authority of india", "irish data protection commission",
}
COURTS = {"supreme court of india", "high court", "supreme court", "tdsat"}

_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|corp|corporation|company|co|plc|"
    r"technologies|technology|solutions|services|holdings|group)\b", re.I)
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_STOP = {"the", "of", "and", "a", "an", "for"}


def normalize(name: str) -> str:
    n = _NONWORD.sub(" ", (name or "").lower())
    n = _SUFFIX.sub(" ", n)
    return " ".join(w for w in n.split() if w not in _STOP).strip()


def _tokens(name: str) -> set[str]:
    return {t for t in normalize(name).split() if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_CASE_NAME = re.compile(r"\b(?:v|vs|versus)\b\.?\s", re.I)
_GENERIC = (
    "all body corporates", "industry-wide", "industry wide", "all data fiduciaries",
    "statute", "draft", "rules", "intermediaries", "needs review", "unknown",
)


def classify_entity(name: str) -> str:
    """Not everything named in a case is an *entity* with its own page.

    Court-case captions ("X v Union of India") and industry-wide addressees
    ("All body corporates") are subjects of an event, not organisations — giving
    them entity pages would produce misleading, thin URLs.
    """
    raw = (name or "").lower()
    n = normalize(name)
    if _CASE_NAME.search(raw):
        return "case"
    if any(g in raw for g in _GENERIC):
        return "generic"
    if n in {normalize(r) for r in REGULATORS} or any(k in n for k in
            ("commission", "authority", "ministry", "board", "cert", "bank of india")):
        return "regulator"
    if any(k in n for k in ("court", "tribunal", "tdsat", "bench")):
        return "court"
    if any(k in n for k in ("act", "rules", "section", "article", "constitution")):
        return "statute"
    return "company"


# Only these entity types get their own public page.
PAGEABLE_TYPES = {"company", "regulator", "court"}


@dataclass
class Entity:
    key: str
    name: str
    entity_type: str
    slug: str
    aliases: set[str] = field(default_factory=set)
    event_ids: list[str] = field(default_factory=list)

    @property
    def url_path(self) -> str:
        return f"entity/{self.slug}"


class EntityResolver:
    """Resolves raw name strings to canonical entities. Deterministic."""

    def __init__(self, similarity_threshold: float = 0.72) -> None:
        self.threshold = similarity_threshold
        self.entities: dict[str, Entity] = {}
        self._alias_to_key: dict[str, str] = {}
        self._slugs: set[str] = set()
        self._seed_aliases()

    def _seed_aliases(self) -> None:
        for canonical, variants in ALIAS_SEEDS.items():
            key = normalize(canonical)
            self._alias_to_key[key] = key
            for v in variants:
                self._alias_to_key[normalize(v)] = key

    def _unique_slug(self, name: str) -> str:
        base = slugify(name, max_words=5)
        slug, n = base, 2
        while slug in self._slugs:
            slug = f"{base}-{n}"
            n += 1
        self._slugs.add(slug)
        return slug

    def _canonical_name(self, key: str, fallback: str) -> str:
        for canonical in ALIAS_SEEDS:
            if normalize(canonical) == key:
                return canonical
        return fallback.strip()

    def resolve(self, raw_name: str, entity_type: str | None = None) -> Entity | None:
        if not raw_name or not raw_name.strip():
            return None
        norm = normalize(raw_name)
        if not norm:
            return None

        key = self._alias_to_key.get(norm)

        # Fuzzy match against entities already known in this build.
        if key is None:
            toks = _tokens(raw_name)
            best, best_score = None, 0.0
            for k, ent in self.entities.items():
                score = _jaccard(toks, _tokens(ent.name))
                if score > best_score:
                    best, best_score = k, score
            if best and best_score >= self.threshold:
                key = best

        if key is None:
            key = norm

        if key not in self.entities:
            name = self._canonical_name(key, raw_name)
            etype = entity_type or classify_entity(name)
            self.entities[key] = Entity(
                key=key, name=name, entity_type=etype, slug=self._unique_slug(name))
        ent = self.entities[key]
        if norm != key:
            ent.aliases.add(raw_name.strip())
        self._alias_to_key[norm] = key
        return ent

    def resolve_authorities(self, raw: str) -> list[Entity]:
        """'CERT-In / IRDAI' names two bodies — split rather than invent a hybrid."""
        if not raw:
            return []
        parts = [p for p in _AUTHORITY_SPLIT.split(raw) if p and len(p.strip()) > 1]
        if len(parts) <= 1:
            e = self.resolve(raw)
            return [e] if e else []
        out: list[Entity] = []
        for p in parts:
            e = self.resolve(p)
            if e and e not in out:
                out.append(e)
        return out

    def all(self) -> list[Entity]:
        return sorted(self.entities.values(), key=lambda e: e.name.lower())
