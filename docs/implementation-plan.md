# Pensieve — Implementation Plan

**Status:** Phase 0 complete (this document). Phase 1 next.
**Author:** Engineering
**Last updated:** 2026-08-05

---

## 1. What Pensieve is

Pensieve is a consumer-intelligence platform. It takes messy, multilingual customer review
data, runs it through a governed data pipeline (Bronze → Silver → Gold), and serves the
result as an interactive analytics dashboard covering sentiment, business topics, trends,
statistical anomalies, data quality, and pipeline health.

**Explicitly not an LLM application.** No OpenAI / Anthropic / Gemini / paid inference APIs.
All NLP runs locally: Lingua for language identification, a locally cached multilingual
Hugging Face transformer for sentiment, and a transparent rule-based classifier for topics.
Everything runs free on a laptop.

### The one-sentence pitch (for a CV)

> A local-first data platform that ingests multilingual customer reviews, enforces schema
> and quality contracts with quarantine of bad records, enriches them with language,
> sentiment and topic signals, aggregates them with PySpark into a Gold layer, detects
> business anomalies statistically, and serves the result through FastAPI to a React
> analytics dashboard.

---

## 2. Environment inspection (verified, not assumed)

The working directory `C:\Users\divya\OneDrive\Divyansh\Development\pensieve` was **empty**.
`git init` has been run. Toolchain actually present on this machine:

| Tool | Found | Verdict |
|---|---|---|
| Python | 3.12.0 | OK — matches target |
| Node | v20.17.0 | OK for Vite 5/6 |
| npm | 10.8.2 | OK |
| Git | 2.43.0.windows.1 | OK |
| Docker | 26.0.0 | OK |
| Docker Compose | v2.26.1-desktop.1 | OK |
| **Java** | **1.8.0_432 (JDK 8)** | **Too old for PySpark 4.x — see R1** |
| **make** | **not installed** | **Needs a shim — see R2** |
| Disk free | 117 GB (88% used) | Adequate, but not roomy |

Verified from PyPI rather than memory:

- `pyspark` 3.5.x declares support for Python 3.8–**3.11 only**.
- `pyspark` 4.0+ declares Python 3.9–3.13 and **requires Java 17+**.

So the combination the brief asks for — Python 3.12 + PySpark — forces **PySpark 4.x**,
which in turn forces **JDK 17+**. This machine has JDK 8. That is a real constraint, not a
theoretical one, and it shapes the plan (see Risks).

---

## 3. Risks and complexity control

Listed most-important first. Each has a decided mitigation, not just a warning.

### R1 — PySpark needs Java 17+; this machine has Java 8 (**high**)

Spark 4 will not start on JDK 8. Additionally, Spark on Windows in local mode usually needs
`winutils.exe` / `hadoop.dll` (a `HADOOP_HOME`) before it can write Parquet to the local
filesystem — a classic Windows-only source of confusing `NativeIO` failures.

**Mitigation (three-layer, no silent substitution):**
1. **Docker is the supported path for the Spark stage on Windows.** A `spark-job` service in
   `docker-compose.yml` built on a JDK 17 base image runs the Silver→Gold job. `make gold`
   detects the situation and routes accordingly. This sidesteps both the JDK and the
   winutils problem entirely.
2. **Native local Spark stays supported** for anyone on Linux/macOS or with JDK 17
   installed. `scripts/check_env.py` reports the detected Java major version and prints the
   exact remediation (`winget install EclipseAdoptium.Temurin.21.JDK`) instead of failing
   with a Java stack trace.
3. PySpark remains the **only** engine that writes Gold. I am not going to quietly
   reimplement Gold in pandas and call it PySpark — the whole point of the layer is to
   demonstrate distributed-style aggregation, and a fake would be indefensible in an
   interview.

### R2 — `make` is not installed on Windows (**medium**)

The brief requires a Makefile and the CI/Docker/Linux path genuinely wants one.

**Mitigation:** ship the canonical `Makefile` (used by CI, Docker, Linux, macOS) **and** a
`make.ps1` PowerShell task runner with identical target names, so `.\make.ps1 setup` works
here today. Both delegate to the same underlying `scripts/*.py` entry points, so there is
one implementation and two thin front doors — no logic duplication.

### R3 — The repository lives inside OneDrive (**medium, easy to underestimate**)

`node_modules/`, `.venv/`, Parquet output under `data/`, and a ~1 GB Hugging Face model
cache sitting inside a synced OneDrive folder causes: sync churn, cloud-quota burn, and
**file-lock errors during writes** that look like random pipeline corruption.

**Mitigation:**
- `HF_HOME` defaults to `%LOCALAPPDATA%\pensieve\hf-cache` (outside OneDrive) in `.env.example`.
- `.gitignore` covers `data/bronze|silver|gold|quarantine`, `.venv`, `node_modules`.
- README documents excluding `data/`, `.venv/`, `node_modules/` from OneDrive sync, and
  recommends relocating the repo to e.g. `C:\dev\pensieve`.
- This is a recommendation, not something I will change on the user's behalf.

### R4 — Sentiment model download is ~1.1 GB (**medium**)

Slow first run; unacceptable in CI.

**Mitigation:** pluggable sentiment backend with three implementations behind one interface —
`transformers` (default), a smaller/faster transformer alternative, and a deterministic
**lexicon** backend used by tests and CI. The active backend and model name are recorded on
every row (`sentiment_model_version`) so no one can confuse mock output for real inference.

### R5 — Scope is very large (**high**)

Eight phases with six dashboard pages, a Spark layer, and eleven documents is a lot of
surface area.

**Mitigation:** strict phase gating. A phase is not "done" until lint + type-check + tests
pass and the app still runs. Postponed items are listed in §6 rather than half-built.

### Complexity explicitly rejected

Kafka, Airflow, Kubernetes, Databricks, Redis, cloud infra, spaCy, authentication,
a service mesh of repository interfaces, and a TF-IDF classifier in the MVP. Each would add
keywords and subtract working software. They are named in `docs/architecture.md` as
deliberate non-goals with the reasoning, which is a better interview answer than having
used them.

---

## 4. Repository structure

Follows the requested tree. Deviations are marked **[D]** and justified.

```text
pensieve/
├── apps/
│   ├── web/                          # React + TS + Vite dashboard
│   │   ├── src/
│   │   │   ├── app/                  # app shell, providers, router
│   │   │   ├── components/           # design-system primitives + charts
│   │   │   ├── features/
│   │   │   │   ├── overview/  brands/  reviews/
│   │   │   │   ├── trends/    data-quality/  pipeline-runs/
│   │   │   ├── hooks/  lib/  routes/  types/
│   │   └── tests/
│   └── api/
│       ├── app/
│       │   ├── api/{routes/,dependencies.py}
│       │   ├── core/  database/  models/  repositories/
│       │   ├── schemas/  services/  main.py
│       ├── migrations/               # Alembic
│       └── tests/
├── pipelines/
│   ├── ingestion/  validation/  transformation/
│   ├── enrichment/  aggregation/  jobs/
│   ├── common/                       # config, logging, domain vocabulary  [D]
│   └── tests/
├── analytics/{sql/,notebooks/}
├── data/{samples/,bronze/,silver/,gold/,quarantine/}
├── infrastructure/{docker/,monitoring/}
├── docs/  scripts/  .github/workflows/
├── docker-compose.yml   Makefile   make.ps1  [D]
├── pyproject.toml  [D]              # single root Python project
├── README.md   .env.example   .gitignore
```

**[D1] One root `pyproject.toml` and one `.venv`.** Not one per Python app. The API and the
pipelines share a virtualenv, with optional dependency groups (`api`, `pipelines`, `spark`,
`nlp`, `dev`) so Docker images install only what they need. Two virtualenvs on one laptop
for one project is friction with no benefit at this size.

**[D2] Shared domain vocabulary lives in `pipelines/common/domain.py`.** The topic taxonomy,
sentiment labels, supported language codes and `PROCESSING_VERSION` are defined once and
imported by both the pipeline and the API. The alternative — a third `packages/core`
package — is the textbook monorepo answer but adds a package boundary for ~200 lines of
constants. If it grows past constants, extract it then. The dependency direction (API reads
the pipeline's vocabulary) is honest: the API serves what the pipeline produces.

**[D3] `make.ps1`** — see R2.

---

## 5. What is essential for the MVP

The MVP is the full core user story end to end, and nothing else:

1. Seeded synthetic dataset generation, including deliberately dirty records.
2. Ingestion of CSV/JSON → **Bronze** Parquet, raw and unmodified.
3. Pandera + custom validation, with failures written to **quarantine** with reasons.
4. Text normalization, deduplication, derived features.
5. Language (Lingua) + sentiment (local transformer) + topic (rules) enrichment → **Silver**.
6. PySpark aggregation → **Gold** (8 datasets) + statistical anomaly detection.
7. Gold → PostgreSQL load; FastAPI serves it.
8. Six dashboard pages, all reading real seeded backend data.
9. Pipeline run/stage telemetry captured throughout and shown in the UI.
10. Tests at every layer + CI + honest benchmark numbers + the documentation set.

## 6. What is deliberately postponed

| Postponed | Why | When it would matter |
|---|---|---|
| Authentication / RBAC | Not needed to prove the platform works; adds login plumbing to every test | Before any real deployment |
| TF-IDF + LogisticRegression topic model | Rules are explainable and need no labelled data; the ML version needs labels to be honest | Once real labelled reviews exist |
| Airflow / Prefect orchestration | The Makefile + job runner is the orchestrator at this scale | Multi-DAG scheduling, retries across machines |
| Kafka / streaming ingestion | Batch is the correct shape for review analytics | Sub-minute freshness requirement |
| Kubernetes / cloud deploy | Must run free and locally | Real multi-tenant hosting |
| Incremental/CDC Silver merge | Full-batch reprocessing is fine at demo volume | 100M+ rows |
| WebSocket live pipeline progress | Polling is sufficient and far simpler | Long-running production jobs |
| ONNX / quantized sentiment | Correctness first; optimize after benchmarking | Proven CPU bottleneck |

---

## 7. Sentiment model selection

### Decision: `cardiffnlp/twitter-xlm-roberta-base-sentiment` (default)

Verified live from the Hugging Face API on 2026-08-05:

| Candidate | Weights | Licence | Downloads/mo | 3-class? | Notes |
|---|---|---|---|---|---|
| **`cardiffnlp/twitter-xlm-roberta-base-sentiment`** | 1112 MB (`pytorch_model.bin`) | not declared | 932k | yes | XLM-R base; fine-tuned on ~198M multilingual tweets |
| `lxyuan/distilbert-base-multilingual-cased-sentiments-student` | 541 MB (safetensors) | Apache-2.0 | 917k | yes | mBERT-distilled; ~2× faster; tags include hi, de, es, fr, en |
| `nlptown/bert-base-multilingual-uncased-sentiment` | 1339 MB | MIT | 735k | no (1–5 stars) | Only 6 EU languages; no Hindi |
| `tabularisai/multilingual-sentiment-analysis` | 541 MB | **CC-BY-NC-4.0** | 399k | 5-class | Non-commercial licence — rejected |

**Why the Cardiff model wins for this dataset:**

1. **The text shape matches.** It is fine-tuned on short, informal, emoji-heavy
   user-generated text. Product reviews are exactly that. A model trained on formal corpora
   would be a worse fit than its benchmark scores suggest.
2. **Native 3-class output** (negative / neutral / positive) matches our schema directly. The
   `nlptown` alternative emits 1–5 stars, which would need an arbitrary star→sentiment
   threshold *and* would partly duplicate the `rating` column we already have — making the
   sentiment signal circular and much less interesting analytically.
3. **Language coverage.** Explicitly fine-tuned for English, French, German, Spanish and
   **Hindi** — five of our six target languages. The XLM-RoBERTa backbone is pretrained on
   100 languages including Polish.
4. **Licence hygiene.** The strongest small alternative is CC-BY-NC, which is a poor choice
   for anything described as portfolio/commercial work.

**Honest limitation to document and to say out loud in an interview:** Polish is *not* in
either model's fine-tuning set. Polish sentiment therefore relies on XLM-R's cross-lingual
transfer. XLM-R transfers better than mBERT, which is a second reason to prefer Cardiff over
the distilled model — but the correct engineering answer is to record it as a known
limitation in `docs/data-dictionary.md`, surface per-language confidence in the dashboard,
and not pretend the number is as trustworthy as the English one.

**Known implementation quirk:** Cardiff models frequently expose labels as
`LABEL_0/LABEL_1/LABEL_2`. The wrapper maps these explicitly to
`negative/neutral/positive` and asserts the mapping at load time rather than trusting
`id2label` ordering.

### Backend design (satisfies "no repeated large-model loads in tests")

```
SentimentBackend (protocol)
├── TransformersBackend   default; model loaded ONCE per process; batched inference
├── (same class, alt model via PENSIEVE_SENTIMENT_MODEL env var)
└── LexiconBackend        deterministic keyword scorer; no download; used by tests + CI
```

Every Silver row records `sentiment_model_version` (e.g.
`cardiffnlp/twitter-xlm-roberta-base-sentiment@transformers` vs `lexicon-v1`) so real
inference is never confused with the test fallback. Per-batch failures are caught, logged
with the batch id, and the affected rows marked `sentiment = unknown` — one bad batch must
not kill a 1M-row run.

---

## 8. Input schema (the contract with the outside world)

| Column | Type | Required | Rule |
|---|---|---|---|
| `review_id` | string | yes | non-empty; unique within batch |
| `brand` | string | yes | non-empty after trim |
| `product` | string | no | free text |
| `text` | string | yes | non-empty after normalization; 3–5000 chars |
| `country` | string | no | ISO 3166-1 alpha-2 where parseable |
| `rating` | int | yes | 1–5 inclusive |
| `source` | string | no | one of web/app/email/marketplace/social, else `unknown` |
| `created_at` | timestamp | yes | parseable; not in the future; not before 2015-01-01 |

Accepted formats: `.csv`, `.json`, `.jsonl`, `.parquet`.

## 9. Layer schemas

### Bronze — raw, never modified

Everything from the source **as strings**, plus ingestion metadata. Nothing is rejected here;
invalid values are preserved verbatim for traceability.

`_raw_*` source columns · `ingestion_batch_id` · `ingestion_timestamp` · `source_file` ·
`source_format` · `source_row_number` · `ingestion_date` (partition)

Layout: `data/bronze/ingestion_date=YYYY-MM-DD/batch_id=<ulid>/part-*.parquet`
Write mode is append-only; a re-run of the same batch id is a no-op rather than an overwrite.

### Silver — clean, typed, deduplicated, enriched

Typed input columns, plus:

`normalized_text` · `language` · `language_confidence` · `sentiment` · `sentiment_score` ·
`sentiment_model_version` · `primary_topic` · `topics[]` · `topic_match_reason` ·
`word_count` · `character_count` · `emoji_count` · `uppercase_ratio` ·
`exclamation_count` · `has_url` · `has_mention` · `is_duplicate_of` ·
`ingestion_batch_id` · `processing_version` · `processed_at`

`text` (the original) is always retained alongside `normalized_text`.
Layout: `data/silver/review_date=YYYY-MM-DD/part-*.parquet`

### Gold — business-ready aggregates (PySpark)

| Dataset | Grain | Purpose |
|---|---|---|
| `daily_brand_metrics` | date × brand | volume, avg rating, sentiment mix, quality |
| `daily_topic_metrics` | date × brand × topic | which complaints are growing |
| `country_metrics` | date × country | geographic performance |
| `language_distribution` | date × language | audience mix + detection health |
| `sentiment_trends` | date × brand × sentiment | rolling sentiment with baselines |
| `data_quality_metrics` | batch × date | valid/invalid/dupe/missing + score |
| `pipeline_run_metrics` | run | duration, throughput, failures per stage |
| `anomalies` | detection event | statistical deviations with explanations |

### Quarantine

`data/quarantine/batch_id=<ulid>/part-*.parquet` — original values, `batch_id`,
`failure_reason`, `failed_field`, `failed_value`, `rule_id`, `quarantined_at`.
Nothing is ever dropped silently.

### Data-quality score (documented formula, no magic)

```
quality_score = 100
             − 40 × (invalid_records   / total_records)
             − 20 × (duplicate_records / total_records)
             − 25 × (missing_required_cells / (total_records × required_columns))
             − 15 × (unparseable_dates / total_records)
```
Clamped to [0, 100]. Weights are constants in one module, documented, and versioned with the
score so historical scores stay interpretable when weights change.

## 10. PostgreSQL schema

`brands` · `reviews` · `review_topics` · `pipeline_runs` · `pipeline_stage_runs` ·
`data_quality_results` · `anomalies` · `daily_brand_metrics` · `daily_topic_metrics`

Postgres holds application-facing and operational data. Large analytical history stays in
Parquet and is queried with DuckDB. Indexes on the review-explorer filter columns
(`brand_id`, `country`, `language`, `sentiment`, `created_at`, `rating`) plus a trigram/GIN
index for text search.

**Why both Postgres and DuckDB** (an interview question worth rehearsing): Postgres is the
transactional store serving concurrent dashboard queries with indexes and connection
pooling. DuckDB is an embedded OLAP engine that reads Parquet with zero copying — it powers
the Gold→Postgres loader, the `analytics/sql/` query library, and notebook analysis. Using
Postgres for full-scan analytical queries over every review would be the wrong tool; copying
all Parquet into Postgres just to query it would be the wrong architecture.

## 11. API surface

```
GET  /api/v1/health                     GET  /api/v1/trends/sentiment
GET  /api/v1/overview                   GET  /api/v1/trends/topics
GET  /api/v1/brands                     GET  /api/v1/anomalies
GET  /api/v1/brands/comparison          GET  /api/v1/data-quality
GET  /api/v1/reviews                    GET  /api/v1/pipeline-runs
GET  /api/v1/reviews/{review_id}        GET  /api/v1/pipeline-runs/{run_id}
POST /api/v1/datasets/upload            POST /api/v1/pipelines/run
```

Cross-cutting: cursor-free page/size pagination with a consistent envelope, `sort`/`order`,
`q` search, filter sets, `date_from`/`date_to`, Pydantic v2 request+response models, a single
RFC7807-style error shape, OpenAPI at `/docs`, DI for session/repo/settings.
No auth in the MVP (see §6).

## 12. Frontend pages

| Route | Page | Core content |
|---|---|---|
| `/` | Executive overview | KPI row, sentiment mix, top complaint, fastest-growing topic, languages, active anomalies, last pipeline run |
| `/brands` | Brand comparison | Sentiment + rating + volume by brand, topic mix, country/language splits, date filter |
| `/trends` | Trends & anomalies | Sentiment/volume/topic time series, anomaly cards, severity filter, baseline vs current |
| `/reviews` | Review explorer | Server-side paginated table, search, 7 filters, URL-backed state, detail drawer, CSV export |
| `/data-quality` | Data quality | Score gauge + trend, valid/rejected/missing/dupes, quarantine reasons breakdown |
| `/pipeline-runs` | Pipeline runs | Run list + stage timeline, duration, throughput, failures, retries, errors |

Requirements applied to all: responsive, explicit loading/empty/error states, keyboard
accessible controls, Zod-validated responses, reusable chart + filter components, strict
TypeScript (no loose `any`), and **zero hardcoded metrics** — every number comes from the API.

---

## 13. Phases and exit criteria

A phase ends only when: `ruff` + `mypy` + `pytest` pass, `eslint` + `tsc` + `vitest` pass
(once the web app exists), the app still starts, README progress is updated, and the work is
committed.

| # | Phase | Exit criteria |
|---|---|---|
| 1 | Foundation | `docker compose up` gives Postgres + API + web; `/api/v1/health` returns 200; React shell routes; lint/type/test green |
| 2 | Generation & ingestion | `seed_demo_data.py --rows N` is reproducible; Bronze Parquet partitioned; batch metadata recorded |
| 3 | Validation & cleaning | Dirty rows land in quarantine with reasons; dedup works; quality score computed and unit-tested |
| 4 | NLP enrichment | Silver written with language/sentiment/topics; lexicon backend keeps tests fast; real model verified once |
| 5 | PySpark Gold | 8 Gold datasets produced; anomalies detected with explanations; runs in Docker |
| 6 | DB & API | Migrations apply; loader populates Postgres; every endpoint returns real data with tests |
| 7 | Dashboard | All 6 pages render live data with loading/empty/error states |
| 8 | Quality & docs | CI green; benchmark actually executed and numbers recorded; all 6 docs written |

## 14. Commands and dependencies

```bash
make setup      # venv + python deps + npm install + .env
make dev        # API (uvicorn --reload) + web (vite) together
make test       # pytest + vitest
make lint       # ruff + mypy + eslint + tsc + prettier
make seed       # generate synthetic dataset
make pipeline   # bronze → silver → gold end to end
make gold       # PySpark stage only (routes to Docker when JDK < 17)
make benchmark  # timed run, writes docs/benchmarks.md
make clean      # drop generated data + caches
```
On this machine, use `.\make.ps1 <target>` (identical targets) until `make` is installed.

**Python:** fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy, alembic,
psycopg[binary], pandas, pyarrow, duckdb, pandera, lingua-language-detector, transformers,
torch (CPU), scikit-learn, python-ulid, structlog, pyspark (4.x, spark group), pytest,
pytest-cov, httpx, ruff, mypy.

**Node:** react, react-dom, react-router-dom, @tanstack/react-query, @tanstack/react-table,
recharts, zod, react-hook-form, tailwindcss, clsx, date-fns; dev: vite, typescript, vitest,
@testing-library/react, jsdom, eslint, prettier.

**External:** PostgreSQL 16 (Docker), JDK 17+ (Docker for the Spark stage), ~1.1 GB HF model
cached to `HF_HOME` outside OneDrive.

---

## 15. Definition of done for the whole project

- `docker compose up --build` produces a working dashboard with seeded data.
- Every dashboard number traces back to a pipeline output; none are hardcoded.
- Bad records are visible in quarantine, not hidden.
- Benchmarks in the README are numbers I actually measured on this machine, with the
  hardware and row count stated. Nothing is claimed about 1M rows until 1M rows have run.
- Six documentation files exist and are genuinely useful, including an interview guide that
  explains the *why* behind each decision.
