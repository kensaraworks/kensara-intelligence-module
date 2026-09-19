"""Central configuration, loaded from environment variables.

Everything is read lazily from the environment so the same code runs on a
laptop (via a local ``.env``) and inside GitHub Actions (via repo secrets).
Nothing here raises on import — missing keys degrade gracefully so the
RSS/scrape-only paths keep working even with no API keys at all.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional: only needed for local dev
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # ── Supabase ──────────────────────────────────────────────────────────
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")

    # ── Search providers ─────────────────────────────────────────────────
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # ── LLM providers ────────────────────────────────────────────────────
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower()

    # Model ids (free-tier friendly defaults)
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Alerting ─────────────────────────────────────────────────────────
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    alert_score_threshold: int = _i("ALERT_SCORE_THRESHOLD", 12)

    # ── Tuning ───────────────────────────────────────────────────────────
    dedup_threshold: float = _f("DEDUP_SIMILARITY_THRESHOLD", 0.85)
    auto_publish_high_confidence: bool = _b("AUTO_PUBLISH_HIGH_CONFIDENCE", False)

    # ── Guardrails (keep the module light & free-tier safe) ───────────────
    max_candidates_per_sweep: int = _i("MAX_CANDIDATES_PER_SWEEP", 15)   # cap LLM/API spend
    article_max_chars: int = _i("ARTICLE_MAX_CHARS", 5000)              # cap tokens/call
    story_retention_days: int = _i("STORY_RETENTION_DAYS", 90)          # cap DB growth
    grounding_enabled: bool = _b("GROUNDING_ENABLED", True)             # official-source check
    few_shot_examples: int = _i("FEW_SHOT_EXAMPLES", 6)                 # from past reviews

    # ── Derived flags ────────────────────────────────────────────────────
    @property
    def supabase_ready(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def has_search(self) -> bool:
        return bool(self.serper_api_key or self.tavily_api_key)

    @property
    def has_llm(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key or self.openai_api_key)

    def resolved_llm_provider(self) -> str | None:
        """Pick an LLM provider: explicit override, else free-first order."""
        if self.llm_provider in {"groq", "gemini", "openai"}:
            key = getattr(self, f"{self.llm_provider}_api_key")
            return self.llm_provider if key else None
        if self.groq_api_key:
            return "groq"
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return None


settings = Settings()


# ── Static reference data shared across the pipeline ──────────────────────

RSS_FEEDS: dict[str, str] = {
    "EDPB": "https://edpb.europa.eu/feed/news_en",
    "RBI": "https://rbi.org.in/Scripts/RSSCirculars.aspx",
    "ET Tech": "https://economictimes.indiatimes.com/tech/rssfeeds/13357220.cms",
    "LiveMint Tech": "https://www.livemint.com/rss/technology",
    "YourStory": "https://yourstory.com/feed",
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/rss",
}

# Scoped legal/enforcement search queries used by the weekly sweep.
ENFORCEMENT_QUERIES: list[str] = [
    'DPDPA enforcement penalty India "Data Protection Board"',
    'CERT-In breach notification penalty India',
    'IT Act "Section 43A" OR "Section 72A" data compensation India',
    'RBI data localisation penalty OR ban India',
    'India data breach fine company 2025 OR 2026',
    'SEBI OR IRDAI data protection penalty India',
    'India "personal data" court judgment privacy 2025 OR 2026',
    'GDPR fine Indian company OR India subsidiary',
]

# Maps a coarse authority/keyword signal to a front-end section id.
SECTION_MAP = {
    "dpdpa_board": "dpdpa_board",
    "sectoral_regulators": "sectoral_regulators",
    "cert_in_breach": "cert_in_breach",
    "courts_case_law": "courts_case_law",
    "international_benchmarks": "international_benchmarks",
}

# Official / primary-source domains. A candidate corroborated by one of these is
# treated as high-trust (grounding, item #3) and eligible for auto-publish.
TRUSTED_SOURCE_DOMAINS = [
    "meity.gov.in", "rbi.org.in", "cert-in.org.in", "sebi.gov.in", "irdai.gov.in",
    "cci.gov.in", "sci.gov.in", "indiacode.nic.in", "egazette.gov.in", "uidai.gov.in",
    "trai.gov.in", "pib.gov.in", "prsindia.org", "indiankanoon.org",
]
