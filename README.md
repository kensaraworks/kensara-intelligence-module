# Kensara Intelligence Module

Autonomous DPDPA / regulatory **enforcement tracker** + SEO intelligence pipeline.
Ingests regulatory news, scores relevance, extracts structured enforcement cases
with an LLM, routes them through a human review gate, and publishes a verified
public tracker — all on a **strict $0 stack**.

```
GitHub Actions (cron compute)  →  Supabase (Postgres DB)  →  Static site + JSON
        │                                   ▲                        ▲
   RSS · scrape · Serper/Tavily        service key            anon key + RLS
   Groq/Gemini extraction          (pipeline writes)      (public read + admin)
```

## Why this is genuinely free

| Piece | Host | Free tier | Notes |
|---|---|---|---|
| Cron + scraping + LLM calls | **GitHub Actions** | 2,000 min/mo private, ∞ on public repos | Never sleeps |
| Database | **Supabase** | 500 MB Postgres | Cron every 4h keeps it from pausing |
| Public tracker + admin | **Cloudflare Pages / GitHub Pages** | Unlimited static | No commercial-use clause |
| Search | **Serper** (→ Tavily fallback) | 2,500 / 1,000 credits | |
| Extraction LLM | **Groq** (→ Gemini → OpenAI) | Generous free tiers | Claude intentionally unused |

> **On Vercel:** the Hobby tier is *non-commercial only*, so for KensaraAI
> Private Limited the front-end is built host-agnostic and deploys to
> **Cloudflare Pages / GitHub Pages** (truly free, no ToS issue). The admin is
> pure client-side (Supabase Auth + Row-Level Security) — no paid serverless.

---

## Layout

```
src/
  config.py                 # env-driven settings, provider fallback order
  db/                       # Supabase REST client + domain store + snapshot shape
  ingestion/                # rss_poller · stealth_scraper · search_sweep (Serper/Tavily)
  processing/               # dedup (TF-IDF) · scoring (12-signal) · llm_extractor
  agents/                   # enforcement_tracker · news_scan · competitor_intel
  publish/snapshot.py       # writes web/data/enforcement.json
  seed.py                   # curated baseline of real verified cases
  main.py                   # CLI: enforcement | news | news-quick | competitor | snapshot | all
web/
  index.html + assets/tracker.js   # public tracker (reads the JSON snapshot)
  admin.html + assets/admin.js     # client-side review cockpit (Supabase Auth)
  data/enforcement.json            # published snapshot (committed by CI)
supabase/schema.sql          # tables + Row-Level Security + public view
.github/workflows/           # three cron pipelines
```

## The 12-signal scoring & pipeline (unchanged intent, hardened)

- **Dedup** — pure-Python TF-IDF cosine (no numpy); URL hash + `≥0.85` similarity
  suppresses syndicated cross-posts.
- **Scoring** — the 12-signal formula, `min(20, base) + recency_delta`.
- **Extraction** — strict-JSON LLM extractor with a Pydantic schema; provider
  order Groq → Gemini → OpenAI; a word-boundary **heuristic fallback** keeps a
  review lead alive even with zero LLM keys.
- **Review gate** — auto-detected cases land with `needs_review = true` and are
  invisible to the public until a signed-in reviewer verifies them.

---

## Setup (≈ 20 minutes)

### 1. Supabase
1. Create a free project at supabase.com.
2. SQL Editor → paste & run [`supabase/schema.sql`](supabase/schema.sql).
3. Authentication → Users → **Add user** (your reviewer email + password).
4. Project Settings → API → copy the **Project URL**, **anon key**, **service_role key**.

### 2. Seed the baseline (local, one-time)
```bash
pip install -r requirements.txt
cp .env.example .env          # fill SUPABASE_URL + SUPABASE_SERVICE_KEY (+ search/LLM keys)
python -m src.seed            # pushes curated cases to Supabase + rebuilds the snapshot
```
No keys handy? `python -m src.seed --local` builds the JSON snapshot alone.

### 3. Front-end config
Put your **public** values in two files:
- `web/assets/tracker.js` → `CONFIG.SUPABASE_URL`, `CONFIG.SUPABASE_ANON_KEY` (optional live refresh)
- `web/assets/admin.js`   → `SUPABASE_URL`, `SUPABASE_ANON_KEY` (required for the admin)

### 4. GitHub secrets
Repo → Settings → Secrets and variables → Actions:
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SERPER_API_KEY`, `TAVILY_API_KEY`,
`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `SLACK_WEBHOOK_URL` (optional).

### 5. Deploy the static site
**Cloudflare Pages (recommended):** connect the repo → build command *(none)* →
output directory **`web`**. Done.
**GitHub Pages:** Settings → Pages → deploy from branch, folder `/web` (or a
tiny action that publishes `web/`).

The tracker lives at `/index.html`; the review cockpit at `/admin.html`
(`noindex`, gated by Supabase Auth).

---

## Running

| Command | What it does | Cron |
|---|---|---|
| `python -m src.main enforcement` | Search sweep → dedup → LLM extract → review queue → snapshot | Thu 06:00 IST |
| `python -m src.main news` | RSS + stealth scrape → score → alert | every 4h |
| `python -m src.main news-quick` | RSS-only fast poll | — |
| `python -m src.main competitor` | Competitor blog crawl + gap flags | Mon 06:00 IST |
| `python -m src.main snapshot` | Rebuild the public JSON only | — |

Everything degrades gracefully: no search key → RSS-only; no LLM key →
heuristic candidates; no Supabase → local snapshot. Nothing crashes on a
missing provider.

## Review flow
1. Cron finds a candidate → stored `needs_review = true` (hidden).
2. Reviewer opens `/admin.html`, signs in, edits the pre-filled card.
3. **Verify & Publish** flips `needs_review = false` (RLS-authorised) → it shows
   on the public tracker instantly (live refresh) and in the next committed JSON.
4. **Discard** deletes the false positive.

## Optional: embed in WordPress (kensara.in)
Simplest is an `<iframe>` of the Cloudflare Pages URL on a WP page, or reverse-proxy
`/dpdpa/enforcement-tracker` to it. A push-to-WordPress REST mirror can be added
if you'd rather host the HTML inside WordPress itself — ask and it's a small module.

## Cost guardrails
- Public repo → unlimited Actions minutes. Private → the 4h cron uses well under
  2,000 min/mo.
- Serper/Tavily calls are bounded by the 8 enforcement queries, weekly.
- LLM calls only fire on de-duplicated, unseen enforcement candidates.
