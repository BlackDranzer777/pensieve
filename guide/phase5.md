# Phase 5 — PySpark Aggregation, the Gold Layer and Anomaly Detection

**Status: complete.** Numbers measured on a real 37,800-row Silver layer.

---

## What this phase is about

Phases 2–4 built one row per review. Phase 5 answers the questions a **business
person** actually asks — which nobody wants to ask a 37,800-row table.

> Which brand's complaints are growing?
> Which country has the worst ratings?
> **Is anything unusual happening right now?**

That last one is the difference between a report and a platform.

---

## How it relates to Phase 4

Phase 4 produced Silver: enriched, typed, deduplicated reviews. Every column
Gold needs is already there.

| Silver gives | Gold turns it into |
|---|---|
| `sentiment` + `created_at` + `brand` | `daily_brand_metrics`, `sentiment_trends` |
| `primary_topic` + brand + date | `daily_topic_metrics` — the growing-complaint view |
| `country` | `country_metrics` |
| `language` + `language_confidence` | `language_distribution` |
| `is_duplicate_of` | The filter that stops double-counting |

That last row matters more than it looks. **Every Gold query filters
`is_duplicate_of IS NULL`.** Counting a duplicate twice would inflate volume
and skew the sentiment mix. The review still exists in Silver and still appears
in the Review Explorer — it just does not vote twice. A test asserts this on
every query, because it is the kind of thing that silently rots.

---

## Two engines, one definition

The aggregation logic is **SQL in `analytics/sql/`**, executed by either engine:

```bash
python -m pipelines.jobs.run_gold                  # DuckDB (default)
python -m pipelines.jobs.run_gold --engine spark   # PySpark, needs JDK 17+
```

| | DuckDB | Spark |
|---|---|---|
| RAM | ~50 MB | ~1–2 GB |
| Needs Java 17+ | no | yes |
| Startup | instant | ~15s JVM |
| Duration here | **1.29s** | 30.47s |

**Why SQL rather than DataFrame code:** two engines with two implementations
drift apart. There is one definition of `daily_brand_metrics`, in one file, and
both engines run it. It also makes `analytics/sql/` a real artifact rather than
a decorative folder.

### DuckDB is the default

Spark is the wrong tool at 37,800 rows, and the numbers below say so plainly.
Making it the default meant every local run paid 24x the wall time and carried
a 1.7 GB JDK image for an option that produced byte-identical output.

The Spark path is **not deleted** — the engine, the Dockerfile, the profile and
the test all remain, and the SQL is unchanged either way. It is opt-in:

```bash
docker compose --profile spark build spark-job
docker compose --profile spark run   --rm spark-job
```

That is exactly the point of the abstraction. Switching engines is a flag, not
a rewrite, because the logic never lived in either engine's API.

### There is no automatic fallback

A DuckDB run you believed was Spark would invalidate every benchmark number and
CV claim, with nothing to reveal it. Instead:

- A **preflight check** names the actual problem before Spark starts
- Every Gold row carries an `engine` column recording what produced it

Real output on this machine, from `--engine spark`:

```
Cannot start Spark on this machine:
  - Java 8 detected; PySpark 4 requires Java 17+

Options:
  python -m pipelines.jobs.run_gold          (DuckDB, the default;
                                             identical Gold output)
  docker compose --profile spark build spark-job
  docker compose --profile spark run   --rm spark-job
  python -m pipelines.jobs.run_gold --engine spark --skip-preflight
```

Same principle as `sentiment_model_version`: the data records what made it.

---

## The eight datasets

| Dataset | Grain | Rows |
|---|---|---|
| `daily_brand_metrics` | date × brand | 450 |
| `daily_topic_metrics` | date × brand × topic | 4,769 |
| `country_metrics` | date × country | 630 |
| `language_distribution` | date × language | 636 |
| `sentiment_trends` | date × brand, with rolling baselines | 450 |
| `anomalies` | detection events | 160 |
| `data_quality_metrics` | batch × rule | 5 |
| `pipeline_run_metrics` | run | 1 |

The last two are **telemetry, not aggregation**. They describe pipeline runs,
not reviews, so Silver cannot produce them — the runner appends to them as it
goes. They are append-only, because the whole point is the trend: *"was this
batch worse than last week's?"* is unanswerable if last week's row was
overwritten.

### One detail in `sentiment_trends`

```sql
ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
```

A **trailing** window. A centred window would leak tomorrow's data into today's
baseline and make anomaly detection quietly circular. A test asserts the word
`FOLLOWING` never appears in that query.

---

## Anomaly detection

**No LLM, no black box.** Rolling baselines, z-scores and percentage change —
arithmetic a business analyst can redo in a spreadsheet.

That constraint is the design. An alert nobody can verify gets ignored after
the second false positive.

### The gates

An event must clear **all** of these:

| Gate | Value | Why |
|---|---|---|
| Minimum volume | 10 reviews | Two negative reviews out of three is 67% negative and means nothing |
| Z-score | ≥ 2.0 | Statistically unusual against a 7-day baseline |
| Percentage change | ≥ 25% | Statistically significant but commercially irrelevant is still irrelevant |
| Direction | per metric | Negativity *falling* is good news, not an incident |

Requiring both a z-score and a relative change is what removes most false
positives. Either alone fires constantly.

### The baseline excludes the day being tested

```python
baseline = values.rolling(7, min_periods=3).mean().shift(1)
```

That `.shift(1)` is load-bearing. Including today in its own baseline drags the
mean toward the value under test and hides exactly the spikes we look for.

### Every anomaly explains itself

```
Nimbus Drinks: daily review volume rose from 4.86 to 16.00 (+229.4%), which is
4.5 standard deviations from the 7-day baseline. Based on 16 reviews on the day.
```

Deterministic, checkable, and deliberately free of words like "significant" or
"confirmed" — a 7-day window does not support that much confidence. A test
asserts those words never appear.

### It found the planted signal

The generator plants a rising delivery-complaint trend for one brand in the
final 14 days. Detection is never told this exists.

It found **6 matching anomalies**, the strongest at 4.5 standard deviations.

---

## The bug this phase surfaced

The first Gold build detected **zero** topic-level anomalies and zero negative
sentiment anomalies. The detector looked broken.

It was not. A synthetic-spike test caught a +250% jump at z=2.3 immediately.
The problem was the **data**:

```
brand-day cells meeting MIN_VOLUME:   2%
topic-day cells meeting MIN_VOLUME:   0%     <- median 1 review per cell
```

10,000 reviews spread across 180 days × 5 brands × 11 topics is about **one
review per cell**. `MIN_VOLUME` was correctly rejecting statistically
meaningless data — the guard doing exactly its job.

The fix was the dataset, not the code. The seed script now defaults to 40,000
rows over 90 days, giving ~8 reviews per brand-topic-day, and topic-level
anomalies appear across nine topics.

**This is a genuinely useful thing to have hit.** "Your anomaly detection needs
enough volume per cell to say anything" is a real analytical constraint, not a
bug — and it is a good interview answer about why thresholds exist.

### A second, smaller gap

A perfectly flat series has zero standard deviation, making the z-score
undefined — so a stable metric that suddenly jumps was skipped entirely, which
is the most obvious anomaly there is. The spread is now floored at 1% of the
baseline. Real data always has some variance; the floor only matters for
synthetic or genuinely static series.

---

## Measured performance

37,800 Silver rows:

| Engine | Duration | Anomalies | Notes |
|---|---|---|---|
| **DuckDB** | **1.29s** | 160 | In-process, ~50 MB |
| **Spark** (Docker, JDK 21) | **30.47s** | 160 | Same SQL, JVM startup dominates |

Both produce **identical row counts across all eight datasets** and find the
same 160 anomalies — which is the whole point of keeping one SQL definition.

Spark being 24× slower here is expected and correct. At 37,800 rows the JVM
startup is the entire cost. The same SQL would run unchanged against a cluster
and a thousand times the data, where the ratio inverts completely.

That is the honest interview answer: *"Spark is the wrong tool at this size,
and I can show you the numbers. It's there because the architecture should not
have to change when the data grows."*

**And then I acted on my own measurement.** DuckDB became the default and the
1.7 GB Spark image was deleted from this machine. Keeping a 24×-slower default
because it sounds more impressive on a CV is the exact opposite of what the
benchmark was for.

---

## Two Docker fixes

**`openjdk-17-jre-headless` no longer exists.** The `python:3.12-slim` base
moved to Debian trixie, which ships JDK 21 and dropped 17. Spark 4 supports
both, so the image now installs 21.

**`analytics/` was not copied into the image.** The Gold queries are read from
disk at runtime, so Spark started perfectly, registered all 37,800 Silver rows,
then failed on `No SQL file for daily_brand_metrics`. A neat demonstration that
the SQL really is loaded at runtime rather than embedded in code.

---

## Files

| File | Role |
|---|---|
| `pipelines/aggregation/engines.py` | Engine abstraction, Spark and DuckDB implementations |
| `pipelines/aggregation/gold.py` | Orchestration of the eight datasets |
| `pipelines/aggregation/anomalies.py` | Rolling baselines, z-scores, severity, explanations |
| `pipelines/aggregation/telemetry.py` | Append-only run and quality history |
| `analytics/sql/*.sql` | The five SQL-defined datasets |
| `pipelines/jobs/run_gold.py` | CLI, preflight check, engine selection |

---

## What Phase 5 hands to Phase 6

Eight Gold datasets in Parquet — pre-aggregated, small, and shaped exactly like
the dashboard pages that will consume them.

Phase 6 loads them into PostgreSQL and exposes them through the remaining 13
API endpoints. The mapping is close to one-to-one:

| Gold dataset | Endpoint | Page |
|---|---|---|
| `daily_brand_metrics` | `/brands`, `/brands/comparison` | Brand comparison |
| `daily_topic_metrics` | `/trends/topics` | Trends |
| `sentiment_trends` | `/trends/sentiment` | Trends |
| `anomalies` | `/anomalies` | Trends & anomalies |
| `data_quality_metrics` | `/data-quality` | Data quality |
| `pipeline_run_metrics` | `/pipeline-runs` | Pipeline runs |

Because Gold is already aggregated, those endpoints are simple indexed reads
rather than scans over 37,800 rows — which is the entire reason the layer
exists.

---

## Where this sits

```
Phase 2   raw file      -> Bronze          nothing lost
Phase 3   Bronze        -> clean records   nothing rejected without a reason
Phase 4   clean records -> Silver          language, sentiment, topics
Phase 5   Silver        -> Gold            aggregation and anomalies   <- you are here
Phase 6   Gold          -> PostgreSQL      the API serves it
```
