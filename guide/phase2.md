# Phase 2 — Data Generation and Ingestion into Bronze

**Status: complete.** Everything below was run against the real pipeline; the
numbers are measured, not estimated.

---

## What this phase is for

Phase 1 built a working shell with nothing in it. Phase 2 answers one question:
**how does data get into the platform, and what guarantees do we make about it
once it is there?**

It delivers two things:

1. A **synthetic review generator** — realistic multilingual review data that
   deliberately includes broken records.
2. An **ingestion pipeline** — reads a file in any supported format and writes
   it to the Bronze layer, unchanged and traceable.

No cleaning, no validation, no analysis. Those are Phase 3's job. Phase 2 only
gets data in and promises not to damage it.

---

## Why generate data at all?

Because there is no real review dataset that is multilingual, covers our ten
business topics, has a known-correct answer, and contains exactly the kinds of
defects that test the validation layer.

A generator gives us something a downloaded dataset cannot: **we know the right
answer.** When quarantine catches 63 out-of-range ratings, we know we injected
63, so we can tell whether validation works. With a real dataset you can only
count what you caught, never what you missed.

It also has to include bad records on purpose. A pipeline only ever tested on
clean input proves nothing about how it handles the input it will actually get.

---

## What the generator produces

Run it:

```bash
python scripts/seed_demo_data.py --rows 5000
```

Measured output:

```
5,150 rows written to data/samples/reviews_5000_seed42.csv (0.9 MB) in 0.17s
```

5,000 clean rows plus 150 appended duplicates. Across:

| Dimension | Values |
|---|---|
| Brands | 5, each with a category and 3 products |
| Countries | GB, US, IN, DE, FR, ES, PL — weighted, not uniform |
| Languages | English, Polish, Hindi, French, German, Spanish |
| Topics | All 10 business topics |
| Sentiment | 52% positive, 31% negative, 17% neutral |
| Ratings | J-shaped — far more 5s and 1s than 3s, like real reviews |
| History | 180 days by default |

### The injected defects — about 12% of rows

| Defect | Rate | What it looks like |
|---|---|---|
| Duplicate records | 3.0% | An extra copy of an existing review |
| HTML in text | 1.5% | `<p>`, `<div class="review">`, escaped entities |
| Missing text | 1.5% | `""`, `"   "`, `None` |
| Invalid rating | 1.2% | `0`, `6`, `-2`, `"five"`, `"4.5"` |
| Broken date | 1.2% | `not-a-date`, `2026-13-45`, `31/02/2025` |
| Odd Unicode | 1.0% | BOM, zero-width spaces, full-width characters |
| Excess whitespace | 1.0% | Leading/trailing runs, embedded newlines |
| Very short text | 1.0% | `"ok"`, `"!"`, `":)"` |
| Unsupported language | 0.8% | Italian, Portuguese, Dutch, Danish |
| Missing brand | 0.8% | `""`, `None` |

### One injected signal

The generator also plants a **rising trend**: in the final 14 days, one brand's
delivery complaints climb sharply. Phase 5's anomaly detection has to find it
without being told it exists. Without this, anomaly detection would be tested
against noise.

---

## Reproducibility

The same `--rows` and `--seed` always produce byte-identical output. This is not
a nicety — it is what makes benchmarks comparable and ingestion idempotent.

**A bug found here, by running it rather than trusting tests:** the generator
originally anchored timestamps to `datetime.now()`, so the "same" seed produced
different data every run. Every run therefore had a different checksum, so
ingestion could never recognise a re-run as a duplicate. Now the default anchor
is *today at midnight UTC*, and tests pin `end_date` explicitly.

---

## The ingestion pipeline

```
source file
    -> validate file type          reject unsupported extensions
    -> read raw records            everything as strings
    -> compute SHA-256 checksum
    -> already ingested?           yes: return the existing batch
    -> store the original file
    -> write the Bronze partition
```

Measured on 5,150 rows:

```
batch_id   : 01KZBKPECRF42C509VFACH9QPZ
rows       : 5,150
throughput : 52,541 rows/sec
checksum   : 05ec3af60ed38e7e...
```

### The three Bronze guarantees

**1. Nothing is modified.** Every value lands exactly as read, as a string. A
rating of `"seven"` and a date of `"not-a-date"` survive intact. Parsing here
would destroy the evidence Phase 3 needs to explain a rejection.

This required a specific fix: pandas converts the literal strings `"NA"`,
`"null"` and `"None"` into missing values by default, so a review whose text is
genuinely the word "None" would become indistinguishable from missing data.
`keep_default_na=False` prevents that.

**2. Nothing is rejected.** Broken rows belong in Bronze too. They are
quarantined later by a stage that can say *why*.

**3. Nothing is overwritten.** Each batch owns a directory. Re-ingesting an
identical file is a no-op; a genuine batch-id collision raises rather than
silently replacing data.

### Layout

```
data/bronze/ingestion_date=2026-08-06/batch_id=01KZBKPECRF42C509VFACH9QPZ/
    part-0000.parquet          the records + ingestion metadata
    _batch_manifest.json       provenance, self-describing
    source/reviews_5000.csv    the original file, byte for byte
```

Keeping the source file means a parser bug found in six months can be replayed
against exactly the bytes that arrived, not against our interpretation of them.

### Idempotency, demonstrated

```bash
python scripts/seed_demo_data.py --rows 5000   # writes a batch
python scripts/seed_demo_data.py --rows 5000   # "Identical file already ingested"
```

One batch on disk after two runs. Identity comes from **content**, not
filename — the same file under a different name is still recognised as a
duplicate.

This matters because pipelines get retried. Without it, a job that failed
after ingestion but before aggregation would double every row on the retry.

---

## Supported formats

`.csv`, `.json`, `.jsonl`, `.parquet` — all normalised to the same all-string
frame. Unsupported extensions are rejected before a single byte is read.

Malformed JSONL reports the **line number**: in a million-line export, "line 2"
is the difference between a minute and an afternoon.

---

## Files

| File | Role |
|---|---|
| `pipelines/ingestion/generator.py` | Synthetic data generation, defect injection |
| `pipelines/ingestion/templates.py` | Multilingual review text, openers and closers |
| `pipelines/ingestion/readers.py` | CSV / JSON / JSONL / Parquet readers |
| `pipelines/ingestion/batch.py` | Batch identity, checksums, manifests, idempotency |
| `pipelines/ingestion/bronze.py` | Partitioned Bronze writer and reader |
| `pipelines/ingestion/service.py` | Orchestration |
| `scripts/seed_demo_data.py` | CLI |

---

## A second bug worth recording

The first full run reported **878 content duplicates out of 1,891 records
(46%)** — against an injected duplicate rate of 3%.

The deduplicator was right; the generator was wrong. With roughly one template
per (language, topic, sentiment), genuinely different reviews produced
byte-identical text. Adding per-language openers and closers expanded the
combinatorial space by about 48x, and the rate dropped to **4.4%** — the 3% we
inject plus a small, realistic natural collision rate.

Neither this nor the determinism bug was caught by a passing test suite. Both
turned up by running the pipeline on real data and finding a number that looked
wrong.

---

## What Phase 2 hands to Phase 3

A Bronze layer containing raw, untouched, traceable records — including all the
broken ones — with a batch id, a checksum, and the original file preserved.

Phase 3's entire job is to decide which of those records are trustworthy, and
to explain every rejection.

Continue to [phase3.md](phase3.md).
