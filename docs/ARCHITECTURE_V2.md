# Intelligence Module — Architecture v2

> **Status:** design of record. Supersedes the v1 pipeline (`intelligence_module_architecture.md`)
> while reusing its working plumbing.

---

## 1. What we are actually building

Not a scraper. Not a news feed.

> **The canonical public record of Indian data-protection regulation** — the dataset
> that people and machines treat as the source of truth — with an editorial engine
> attached to it.

### Objective function

| Goal | Implication for the system |
|---|---|
| Be **first** to know | Time-to-detection is a primary KPI, not an afterthought |
| Miss **nothing** | Recall is measured against ground truth, not assumed |
| Be **cited** by Google / LLMs | Pre-rendered HTML, stable URLs, structured data, explicit provenance |
| Fuel **expert editorial** | A radar surface built for humans who write opinions |
| Convert mindshare → pipeline | Long-tail pages that own the 25k → 500k/mo search curve |

**Window:** now → **May 2027**. Every week the public surface is un-citable is a week of the land-grab burned.

---

## 2. Six design shifts from v1

### 2.1 Model *events* and *entities*, not *articles*
v1 treated an article as the unit: article → score → extract → row. That is why dedup is
brittle and cases go stale.

v2 spine: **Entities** (regulators, companies, statutes, sections, courts, people) and
**Events** (order issued, rule notified, breach disclosed, judgment delivered, consultation
opened). Many documents describe one event. An event has a **lifecycle**:

```
rumored → reported → confirmed → order published → appealed → upheld / overturned
```

Consequences that fall out for free:
- Deduplication becomes **event identity + entity resolution**, not string similarity.
- A case becomes a **dossier with a timeline**, not a table row.
- Re-verification is native: open events *want* resolution.
- Machines cite stable entities far more readily than rows in a table.

### 2.2 Two products, opposite optimisation targets
v1's single pipeline with one threshold forced a bad trade: either miss stories or publish noise.

| | **Radar** (internal) | **Record** (public) |
|---|---|---|
| Optimise for | **Recall** — never miss | **Precision** — never be wrong |
| Tolerates | Noise | Latency |
| Consumer | Kensara experts | Google, LLMs, the market |
| Failure mode | A missed story | A wrong entry: brand + legal damage |

One knowledge base. Two surfaces. Two thresholds.

### 2.3 Keyword *pull* → a sensing **net**
Three discovery modes instead of one:

1. **Document-watch** — diff source pages for *new documents*. No keywords. **Free** (HTTP + diff).
2. **Query matrix** — entity × action × statute, generated combinatorially.
3. **Entity-graph expansion** — every entity learned generates its own monitoring.
   Star Health enters the graph → Star Health is watched forever. This finds what keyword
   search structurally cannot, because it follows *entities*, not *words*.

### 2.4 Binary `needs_review` → public **trust tiers**
Trust is the moat, so it ships as a visible feature:

| Tier | Meaning | Public? |
|---|---|---|
| 🟢 `primary_confirmed` | Official document retrieved; entity + amount matched | Yes |
| 🟡 `press_reported` | N independent named sources, no primary doc yet | Yes, labelled |
| ⚪ `ai_detected` | Extracted, awaiting human review | **Never** |

This is what makes an LLM comfortable citing us — and it is our **defamation shield**.
Publishing "Company X was penalised" incorrectly is real legal exposure in India.

### 2.5 Relevance scoring → **editorial-value prediction**
Wrong question: *"does this contain the word DPDPA?"*
Right question: **"will our expert want to write about this today, and will it rank?"**

Signals: **novelty** (are we first?), event severity (order > consultation > opinion), entity
prominence, primary-source availability, search-demand velocity, competitor-coverage gap,
ICP relevance. Weights **learn** from what experts actually publish.

### 2.6 Backward-looking → also **forward-looking**
Everyone tracks what happened. Nobody publishes a **regulatory calendar**: rule phase-ins,
consultation close dates, compliance deadlines, DPB milestones. Evergreen, highly citable,
and "what must I do by when" is a buying trigger.

---

## 3. Knowledge model

```
sources ──< documents >──── claims ────> events ────< event_entities >──── entities
                │                          │
                └──> GCS evidence archive  └──< detections (time-to-detection)
```

### Core tables

```sql
entities        (id, type, canonical_name, aliases[], slug, metadata, created_at)
                -- type: regulator | company | statute | section | court | person

events          (id, slug, event_type, title, occurred_on, status, trust_tier,
                 subject_entity_id, authority_entity_id, statute_refs[],
                 penalty_inr, penalty_display, outcome, summary,
                 first_seen_at, published_at, updated_at)

documents       (id, url, url_hash, source_id, title, published_at, fetched_at,
                 content_hash, storage_uri, doc_type, is_primary_source)
                -- doc_type: news | order | gazette | judgment | press_release | analysis

claims          (id, event_id, document_id, field, value, confidence)
                -- one row per (field, document): enables contradiction detection

event_documents (event_id, document_id, role)      -- primary | corroborating
event_entities  (event_id, entity_id, role)        -- subject | authority | court | counsel

sources         (id, name, domain, tier, trust_weight, watch_type, feed_url,
                 cadence_tier, last_checked_at, health)

watchlist       (entity_id, reason, added_at, active)   -- entity-graph expansion
detections      (event_id, document_id, detected_at, published_at, latency_seconds)
coverage_audits (run_id, expected_event, found, source, checked_at)
citations       (query, engine, cited, position, checked_at)
review_decisions(...)                                    -- carried over from v1
```

### Event identity
Two documents describe the same event when they agree on
`(subject_entity, authority_entity, event_type, date within window)`.
Ambiguous pairs go to an LLM adjudicator. **Disagreeing claims are flagged, never silently
merged** — contradiction is signal, not noise.

---

## 4. Layered architecture

```
0  KNOWLEDGE MODEL   entities · events · documents · claims · sources
1  SENSING           document-watch · query matrix · entity-graph expansion
                     tiered cadence: 15 min (hot) → weekly (audit)
2  RESOLUTION        doc → claims → event identity → entity resolution
                     contradiction detection
3  VERIFICATION      primary-source retrieval · corroboration · GCS evidence → trust tier
4  JUDGMENT          novelty · editorial value · angle generation
5  SURFACES          RADAR (expert queue)  |  RECORD (public, static, per-case URLs)
6  DISTRIBUTION      GEO/SEO · JSON/CSV/API · llms.txt · alerts · digest
7  LEARNING          expert decisions → scoring weights, source trust, blind spots
8  MEASUREMENT       recall · time-to-detection · citation share · editorial throughput
```

### Two loops most systems skip
- **Coverage self-audit** — periodically ask *"what are we missing?"* by cross-checking against
  law-firm year-in-reviews, Parliament breach answers, and competitor trackers. A system that
  detects its own blind spots.
- **Citation monitoring** — track whether AI Overviews / Perplexity / ChatGPT actually cite us
  for target queries. Closes the loop on the real business goal.

### Sensing cadence tiers

| Tier | Cadence | Sources |
|---|---|---|
| **0 — hot** | 15–30 min | PIB, MeitY, CERT-In, RBI press, MediaNama, LiveLaw, Bar & Bench, Google News RSS |
| **1 — warm** | 1–4 h | ET, Mint, Business Standard, Inc42, Entrackr, BusinessLine |
| **2 — cool** | daily | Law firms (Nishith Desai, Trilegal, Khaitan, CAM, AZB), IAPP, DataGuidance, SpicyIP |
| **3 — audit** | weekly | Deep search sweeps, gap audits, competitor trackers, eGazette, PRS, Parliament Q&A |

> v1 missed **MediaNama, LiveLaw, Bar & Bench and law-firm analysis** — which is where India
> privacy news and judgments actually break first.

---

## 5. Cost model — hard constraint

**Everything is $0 except the public surface.** Each component carries a free-tier ceiling and
the guardrail that keeps it under.

| Layer | Platform | Free ceiling | Guardrail |
|---|---|---|---|
| Pipeline compute | **GitHub Actions** (public repo) | Unlimited minutes | Job timeouts; tiered cadence |
| Knowledge base | **Supabase Postgres** | 500 MB | Text → GCS; structured only in PG; retention prune |
| Evidence archive | **GCS** | ~cents | Compress; lifecycle rules |
| Public surface | **Vercel** | *hosting budget* | Pre-rendered static; CDN-cached |
| LLM | **Groq + Gemini (AI Studio)** | Per-provider daily caps | Cheap pre-filter first; only survivors hit an LLM; dual-provider headroom |
| Search | **Serper** | ~2,500 credits/mo | **Search is a last resort, not a sensor** |
| Auth | **Supabase Auth** | Generous | — |

### Three rules that keep it free

1. **Discovery must be free.** Document-watch (HTTP + diff) and RSS / Google News RSS are the
   primary sensors. Paid search is reserved for *grounding a specific candidate* and weekly gap
   audits. Done right, v2 uses **fewer** paid searches than v1, which routed everything through Serper.
2. **Never LLM a document that a cheap filter can reject.** Deterministic pre-filter (entity
   presence, source tier, keyword floor) runs first; only survivors are extracted.
3. **Raw text never touches Postgres.** Documents go to GCS; Postgres holds structured records
   and pointers.

> ⚠️ **GCP trap:** use **Gemini via AI Studio** (free). **Vertex AI bills from the first call.**

---

## 6. Public surface — the moat

One knowledge base → many citation magnets and long-tail SEO surfaces.

| Surface | URL pattern | Why it matters |
|---|---|---|
| Enforcement tracker | `/enforcement-tracker` | Flagship index |
| **Case dossier** | `/enforcement/{slug}` | Per-case permanent URL — citation + long-tail |
| Entity page | `/entity/{slug}` | Owns "<company> data breach penalty" |
| Statute explorer | `/dpdpa/section/{n}` | Owns "DPDPA Section 8(6)"-class queries |
| Regulatory calendar | `/calendar` | Forward-looking; nobody has this |
| Penalty database | `/penalties` | Aggregates, charts, sector totals |
| Machine surfaces | `/data/*.json`, `/llms.txt`, `sitemap.xml` | Direct machine consumption |

### Non-negotiable engineering rules
- **Pre-rendered static HTML.** GPTBot / ClaudeBot / PerplexityBot / CCBot largely do **not**
  execute JavaScript. A client-rendered table is invisible to them. *(This is v1's single
  biggest defect — the current tracker ships an empty shell.)*
- **Stable IDs and slugs forever.** A citation that 404s is worse than no citation.
- **schema.org** `Dataset`, `Article`, `Organization`, `Legislation` per surface.
- **Explicit provenance and dates** on every fact.
- **Interlinking** — cases ↔ entities ↔ sections. This is how hundreds of pages compound.

---

## 7. Metrics

Tracked weekly. These are also the marketing claims.

| Metric | Definition | Target |
|---|---|---|
| **Recall** | % of ground-truth events captured | > 95 % |
| **Time-to-detection** | Publication → in our radar | < 60 min (tier 0) |
| **Citation share** | % of target queries where engines cite us | Growing |
| **Editorial throughput** | Expert posts produced from radar / week | Per editorial plan |
| **Precision (public)** | Published entries with zero corrections | ~100 % |

---

## 8. Phases

Phases overlap; each ships something usable.

### Phase 0 — Stop the bleeding *(highest urgency)*
The public surface is currently invisible to generative crawlers and contains unverified seed data.
- Pre-render the tracker to **static HTML** at snapshot time
- **Per-case URLs** for existing cases
- **Seed-data integrity cleanup** — real source URLs or demote to `press_reported` / remove
- Ship **trust-tier labels** publicly
- `llms.txt`, sitemap, schema.org pass

**Exit:** an AI crawler fetching the page sees every case, with provenance.

### Phase 1 — Knowledge model
- `entities` / `events` / `documents` / `claims` / joins schema
- Migrate existing `enforcement_actions` → events + entities
- Event-identity resolution + entity resolution
- Contradiction detection

**Exit:** a case is a dossier with a timeline and multiple sources.

### Phase 2 — Sensing net
- Source registry with tiers + health
- **Document-watch** (diff-based) for all regulators
- RSS expansion: MediaNama, LiveLaw, Bar & Bench, law firms, Google News RSS
- Query matrix + **entity-graph expansion** + watchlist
- Cheap pre-filter before any LLM call
- Cadence tiers (15 min → weekly)

**Exit:** time-to-detection < 60 min on tier-0 sources; paid-search spend *down*.

### Phase 3 — Verification & trust
- Primary-source retrieval and **matching** (entity + amount actually present)
- **GCS evidence archive** (snapshot every ingested document)
- Cross-source corroboration → trust tier assignment
- Public provenance labels wired end-to-end

**Exit:** every public fact traceable to an archived document.

### Phase 4 — Public surface build-out
- Case dossiers, entity pages, statute explorer, calendar, penalty database
- Full interlinking, schema.org, JSON/CSV exports, API
- Sitemap automation

**Exit:** hundreds of interlinked, pre-rendered, citable pages.

### Phase 5 — Editorial radar
- Expert queue as the primary internal surface
- Editorial-value scoring (novelty, gap, demand)
- Angle generation + daily digest
- Feedback capture on what experts actually write

**Exit:** experts start their day in the radar.

### Phase 6 — Learning & measurement
- **Recall back-test** against a ground-truth event set (Jan–Sep 2026)
- Time-to-detection dashboard
- **Citation monitoring** across engines
- **Coverage self-audit** loop
- Scoring weights learn from `review_decisions` + published posts

**Exit:** the four KPIs are live and the system improves itself.

---

## 9. What this needs from Kensara

Engineering is on me. Two things are not:

1. **Ground truth** — an expert-compiled list of known India data-protection events
   (2023 → today). Without it, recall is unmeasurable and "most complete tracker" is an
   unbacked claim. This is the single highest-value input you can provide.
2. **Legal judgment** — trust-tier sign-off and defamation review on anything naming a company.

### Honest limits
- 100 % capture is an asymptote. A good net reaches the mid-90s; the last few points come from
  the coverage self-audit and your experts spotting gaps.
- Trust tiers only work if the review gate is actually staffed. The bottleneck will be human
  review throughput, not extraction.

---

## 10. Carried forward from v1

Working plumbing that v2 reuses rather than rebuilds: GitHub Actions cron, Supabase + RLS,
the human review gate, the client-side admin, stealth scraping (`curl_cffi`), TF-IDF dedup
(demoted to a pre-filter), multi-provider LLM fallback, and the guardrail set
(per-run caps, article truncation, retention prune, empty-snapshot protection).
