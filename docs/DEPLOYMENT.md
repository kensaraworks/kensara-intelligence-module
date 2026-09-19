# Deployment Guide — Kensara Intelligence Module

End-to-end setup for the **$0** stack. ~30 minutes. Nothing here costs money on
the free tiers described.

The system has **three runtime locations**, and each needs a different subset of
keys. Understanding this split is the whole game:

```
┌──────────────────────────┐   secrets (service key, LLM, search)
│  GitHub Actions (cron)    │◄──────────── the "brain": scrapes, scores,
│  — the pipeline           │              extracts, writes to the DB
└─────────────┬────────────┘
              │ writes (service key, bypasses RLS)
              ▼
┌──────────────────────────┐
│  Supabase (Postgres)      │  the durable store
└─────────────┬────────────┘
              │ reads (anon key + RLS)
              ▼
┌──────────────────────────┐   public config only (URL + anon key)
│  Static site (Cloudflare) │◄──────────── tracker (public) + admin (auth'd)
│  — web/ folder            │
└──────────────────────────┘
```

---

## 0. Key reference — what goes where

| Variable | GitHub Actions secret | Front-end JS (public) | Local `.env` | Required? |
|---|:---:|:---:|:---:|---|
| `SUPABASE_URL` | ✅ | ✅ | ✅ | **Yes** |
| `SUPABASE_ANON_KEY` | — | ✅ | ✅ | **Yes** (front-end) |
| `SUPABASE_SERVICE_KEY` | ✅ | ❌ **never** | ✅ | **Yes** (pipeline) |
| `SERPER_API_KEY` | ✅ | — | ✅ | One search key required |
| `TAVILY_API_KEY` | ✅ | — | ✅ | Optional (fallback) |
| `GROQ_API_KEY` | ✅ | — | ✅ | One LLM key required |
| `GEMINI_API_KEY` | ✅ | — | ✅ | Optional (fallback) |
| `OPENAI_API_KEY` | ✅ | — | ✅ | Optional (fallback) |
| `SLACK_WEBHOOK_URL` | ✅ | — | ✅ | Optional (alerts) |
| `DISCORD_WEBHOOK_URL` | ✅ | — | ✅ | Optional (alerts) |
| Tuning / guardrails | ✅ (optional) | — | ✅ | Optional (defaults fine) |

**Golden rules**
- The **anon key is public** — it is *designed* to ship in the browser. Row-Level
  Security (RLS) is what protects your data. Safe to commit in `web/assets/*.js`.
- The **service key is a master key** — it bypasses RLS. It lives ONLY in GitHub
  Actions secrets and your local `.env` (which is git-ignored). Never in the
  front-end, never committed, never shared.
- **Minimum to run:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
  **one** of Groq/Gemini, **one** of Serper/Tavily. Everything else is optional and
  the pipeline degrades gracefully without it.

---

## 1. Put the code on GitHub

```bash
cd "Intelligence Module"
git add -A
git commit -m "Initial commit: intelligence module"
gh repo create kensara-intelligence --private --source=. --push
# or create the repo in the GitHub UI and: git remote add origin <url> && git push -u origin main
```

- **Public repo** → unlimited Actions minutes (recommended; the code contains no
  secrets — the anon key is meant to be public).
- **Private repo** → 2,000 free Actions minutes/month, which is plenty here, but
  GitHub *Pages* isn't free on private repos — use Cloudflare Pages (step 6).

---

## 2. Supabase (database + auth)

1. Create a free project at **supabase.com** → New project. Pick a region near India
   (e.g. `ap-south-1` Mumbai). Set a strong DB password (you won't need it again).
2. **SQL Editor → New query →** paste all of [`supabase/schema.sql`](../supabase/schema.sql)
   → **Run**. This creates every table, index, RLS policy and the public view.
   *(Re-running it later is safe — it's idempotent.)*
3. **Settings → API →** copy three values:
   - **Project URL** → `SUPABASE_URL`
   - **`anon` `public` key** → `SUPABASE_ANON_KEY`
   - **`service_role` `secret` key** → `SUPABASE_SERVICE_KEY`
4. **Authentication → Users → Add user →** enter your reviewer email + a password,
   tick **Auto Confirm User**. This is the login for `/admin.html`. Add one per
   reviewer.

> Why Supabase won't "pause": the free tier pauses after 7 days of *inactivity*.
> The 4-hourly news cron touches the DB constantly, so it never idles.

---

## 3. Get the API keys (all free tiers)

| Service | Where | Free tier | Maps to |
|---|---|---|---|
| **Serper** (search) | serper.dev → API Key | 2,500 credits | `SERPER_API_KEY` |
| **Groq** (LLM) | console.groq.com → API Keys | generous free | `GROQ_API_KEY` |
| **Gemini** (LLM) | aistudio.google.com → Get API key | 1,500 req/day | `GEMINI_API_KEY` |
| **Tavily** (search, optional) | tavily.com → dashboard | 1,000/mo | `TAVILY_API_KEY` |
| **OpenAI** (LLM, optional) | platform.openai.com → API keys | paid | `OPENAI_API_KEY` |
| **Slack** (alerts, optional) | api.slack.com/apps → Incoming Webhooks | free | `SLACK_WEBHOOK_URL` |

Provider order is **free-first**: Serper→Tavily for search, Groq→Gemini→OpenAI for
LLM. Claude is intentionally not wired in. Grab at least Serper + Groq (or Gemini).

---

## 4. Add GitHub Actions secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add each (name = left column, value = the key):

```
SUPABASE_URL            = https://xxxx.supabase.co
SUPABASE_SERVICE_KEY    = eyJhbGci...   (the service_role key)
SERPER_API_KEY          = ...
GROQ_API_KEY            = ...
GEMINI_API_KEY          = ...            (optional)
TAVILY_API_KEY          = ...            (optional)
OPENAI_API_KEY          = ...            (optional)
SLACK_WEBHOOK_URL       = ...            (optional)
```

Optional tuning secrets (only if you want to override defaults):
`MAX_CANDIDATES_PER_SWEEP`, `ARTICLE_MAX_CHARS`, `STORY_RETENTION_DAYS`,
`GROUNDING_ENABLED`, `AUTO_PUBLISH_HIGH_CONFIDENCE`, `ALERT_SCORE_THRESHOLD`.

> Note: `SUPABASE_ANON_KEY` is **not** needed as an Actions secret — the pipeline
> uses the service key. The anon key only goes in the front-end (step 5).

---

## 5. Configure the front-end (2 files)

Edit the config at the top of each file and commit:

**`web/assets/admin.js`** (required — otherwise the admin runs in offline demo mode):
```js
const SUPABASE_URL = "https://xxxx.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGci...";   // the ANON key, not service
```

**`web/assets/tracker.js`** (optional — enables instant live refresh after a verify):
```js
const CONFIG = {
  SUPABASE_URL: "https://xxxx.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGci...",
};
```

Also update the canonical/OG URLs in `web/index.html` (currently
`https://kensara.in/dpdpa/enforcement-tracker`) to wherever you'll host it.

```bash
git add web/ && git commit -m "config: wire Supabase into front-end" && git push
```

---

## 6. Seed the baseline data (one-time)

The tracker ships with ~10 curated real cases. Load them into Supabase:

```bash
python -m pip install -r requirements.txt
cp .env.example .env          # fill SUPABASE_URL + SUPABASE_SERVICE_KEY at minimum
python -m src.seed            # pushes curated cases + rebuilds the snapshot
git add web/data/ && git commit -m "seed: baseline dataset" && git push
```

No keys yet? `python -m src.seed --local` builds `web/data/enforcement.json` from the
seed alone (no DB write) so the page has content immediately.

---

## 7. Deploy the static site — Cloudflare Pages (recommended, truly free)

1. **dash.cloudflare.com → Workers & Pages → Create → Pages → Connect to Git.**
2. Select your repo.
3. Build settings:
   - **Framework preset:** None
   - **Build command:** *(leave empty)*
   - **Build output directory:** `web`
4. **Save and Deploy.** You get `https://<project>.pages.dev`.
5. **Custom domain:** Pages → your project → Custom domains → add
   `tracker.kensara.in` (or a path — see step 9). Cloudflare sets the DNS.

Every `git push` (including the cron's snapshot commits) auto-redeploys, so the
tracker stays fresh. No commercial-use restriction, unlike Vercel Hobby.

*Alternative — GitHub Pages* (public repos only): add a Pages deploy workflow that
publishes the `web/` folder, or move `web/` to `docs/` and enable Pages on `/docs`.
Cloudflare is cleaner because it serves an arbitrary output dir directly.

---

## 8. Turn on the pipeline & test

1. Repo → **Actions** tab → enable workflows if prompted.
2. Run one manually: **Actions → "Regulatory & News Poll" → Run workflow**.
3. Watch the logs. Then check **Supabase → Table editor → `stories_processed`** for
   rows, and **`scraper_runs`** for an `ok` entry.
4. Run **"Weekly DPDPA Enforcement Tracker"** the same way to test extraction; new
   auto-detected leads land in `enforcement_actions` with `needs_review = true`.

Schedules (already configured, in UTC):
| Workflow | Cron | IST |
|---|---|---|
| News + regulatory poll | `0 */4 * * *` | every 4h |
| Enforcement sweep + re-verify | `30 0 * * 4` | Thu 06:00 |
| Competitor + brief + angles | `30 0 * * 1` | Mon 06:00 |

---

## 9. Use the admin & embed

- Open `https://<your-site>/admin.html`, sign in with the Supabase reviewer user.
- **Review Queue** → edit a candidate → **Verify & Publish**. It appears on the
  public tracker (instantly if you set the tracker.js live-refresh keys; otherwise
  on the next cron snapshot commit).
- **Embed in kensara.in** (WordPress): easiest is an `<iframe>` of the Pages URL on
  a WP page, or point a subdomain/`/dpdpa/enforcement-tracker` reverse-proxy at it.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Admin shows "DEMO MODE" | `SUPABASE_URL`/`ANON_KEY` not set in `web/assets/admin.js`. |
| Admin login fails | Create the user in Supabase → Authentication → Users (Auto Confirm). |
| Public page empty | `web/data/enforcement.json` not committed — run step 6, or the cron hasn't run yet. |
| Queue never fills | Missing `SERPER_API_KEY` (no search) — add it as an Actions secret. |
| Cases extracted but all `[Needs review]` | No LLM key → heuristic fallback. Add `GROQ_API_KEY` or `GEMINI_API_KEY`. |
| Actions push fails | The workflow needs `contents: write` (already set) and the repo default branch to be `main`. |
| Supabase "project paused" | It idled >7 days — un-pause once; the cron keeps it awake thereafter. |
| Costs appearing | You added a paid host (Vercel Pro) or exceeded a free tier — check Serper credits and stay on Cloudflare Pages. |

## Security checklist
- [ ] `SUPABASE_SERVICE_KEY` is **only** in GitHub secrets + local `.env` (never in `web/`).
- [ ] `.env` is git-ignored (it is, via `.gitignore`).
- [ ] RLS is enabled on all tables (the schema does this).
- [ ] `/admin.html` has `noindex` (it does) and requires Supabase auth.
- [ ] Reviewer accounts use strong passwords.
