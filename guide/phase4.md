# Phase 4 — NLP Enrichment and the Silver Layer

**Status: complete.** All numbers measured on a real 4,729-row run.

---

## What this phase is about

Phases 2 and 3 built a data platform: data arrives, is preserved, validated,
cleaned and scored. Everything so far was about **trustworthiness**.

Phase 4 is the first phase about **meaning**. It answers three questions no
amount of validation can:

- What language is this review written in?
- Is the customer happy or unhappy?
- What are they actually talking about?

This is where Pensieve stops being a well-governed pipeline and starts being
*consumer intelligence*.

---

## How it relates to Phase 3

Phase 3 hands over records with a guarantee, and Phase 4 spends that guarantee.

| Phase 3 provided | Phase 4 uses it to |
|---|---|
| `normalized_text` | Feed Lingua and keyword matching without HTML noise |
| 421 bad rows already quarantined | Never spend transformer time on unusable data |
| `rating` as `Int8`, `created_at` as a timestamp | Skip defensive parsing entirely |
| The original `text`, untouched | Show both in the review drawer later |
| Derived features already computed | Add only the three NLP columns |

That second row is worth pausing on. At **30 reviews/second** on CPU, scoring
the 421 invalid records would have cost 14 seconds of pure waste on every run —
and at a million rows it would be hours. Validating before enriching is not
just tidy; it is the difference between a pipeline that scales and one that
does not.

---

## The three enrichments

### 1. Language — Lingua

Chosen over langdetect and fastText because it reports **confidence** and stays
accurate on short text. Reviews are often one sentence, and classic n-gram
detectors become unreliable below ~20 words.

Three outcomes, deliberately kept distinct:

| Value | Meaning |
|---|---|
| `en` `pl` `hi` `fr` `de` `es` | Detected, confident, supported end to end |
| `unsupported` | Confidently a real language we do not support |
| `unknown` | Below the confidence floor, or too short to call |

Collapsing the last two would hide a real difference. "Confidently Italian"
says *consider supporting Italian*. "Unknown" says *this text is too short to
judge*. Those lead to different decisions.

Making that work required putting **non-supported languages into the detector's
candidate set**. Without Italian, Portuguese and Dutch as options, Lingua is
forced to choose among our six and confidently returns the wrong one.

Measured on 4,729 reviews:

```
en 1861 · de 646 · hi 636 · fr 581 · es 458 · pl 440
unknown 75 · unsupported 32
```

The 32 unsupported records are the Italian/Portuguese/Dutch/Danish rows the
generator injected on purpose — detected correctly, flagged honestly.

### 2. Sentiment — a local transformer

`cardiffnlp/twitter-xlm-roberta-base-sentiment`, ~1.1 GB, running on CPU.
**No LLM, no API, no per-request cost.**

Two backends behind one protocol:

| Backend | Stamp on every row | Purpose |
|---|---|---|
| `TransformersBackend` | `cardiffnlp/...@transformers` | Real inference |
| `LexiconBackend` | `lexicon-v1` | Tests and CI, no download |

**Every row records which backend produced it.** That is what stops lexicon
output from being mistaken for real inference in a dashboard or a benchmark —
the mock is clearly labelled in the data itself, not just in a config file.

The single clearest argument for the transformer:

```
"Always in stock, I have never had trouble finding it."

  lexicon      -> negative      "never" is in the negative word list
  transformer  -> positive 0.647   reads the negation correctly
```

A bag-of-words scorer cannot see negation. That is not a bug to fix in the
lexicon; it is the reason a real model exists.

Verified across languages:

```
positive 0.944  Absolutely fantastic, best purchase I have made all year!
negative 0.960  Terrible quality, it broke after two days.
neutral  0.591  The package arrived on the expected date.
negative 0.919  Die Lieferung war schrecklich spät und niemand konnte helfen.
positive 0.894  स्वाद बहुत बढ़िया है, बहुत पसंद आया।
positive 0.871  Świetna cena, produkt jest tańszy niż u konkurencji.
```

**Polish is not in this model's fine-tuning set.** It works through
XLM-RoBERTa's cross-lingual transfer — which is precisely why that backbone was
chosen over an mBERT-based alternative. It stays a documented limitation rather
than a guarantee, and per-language confidence is stored so the dashboard can
show it.

One implementation trap worth knowing: Cardiff models expose labels as
`LABEL_0/1/2`, and the ordering is a property of the checkpoint, not a
convention. The mapping is explicit and **asserted at load time**, so swapping
in a model with different ordering fails loudly instead of silently inverting
every sentiment in the warehouse.

### 3. Topics — explainable rules, not a model

Rule-based on purpose, for three reasons:

**No labelled data.** Training a topic classifier needs thousands of
hand-labelled reviews. Inventing labels would teach a model our guesses.

**Explainability.** When the dashboard says a review is about `delivery`, it
also says *why*: `matched: courier, parcel`. A fine-tuned transformer would
score better and explain nothing.

**Editable by non-engineers.** A product manager can read `topic_rules.py` and
say "we call that a delivery problem too" — and adding the word is a one-line
change, not a retraining run.

Keywords carry weights (strong = 2, weak = 1), so multi-topic reviews resolve
sensibly rather than by dictionary order:

```
"The delivery was late and customer service never replied"
   primary : customer_support
   topics  : customer_support, delivery
   reason  : matched: customer service, replied
```

`other` is the honest fallback when nothing matches. A rising `other` share is
the signal that the taxonomy is drifting away from what customers discuss.

TF-IDF + Logistic Regression remains the documented next step, once real
labelled data exists. That is an improvement, not a prerequisite.

---

## The Silver layer

31 columns, one row per review, partitioned by **`review_date`** — the day the
customer wrote it, not the day we ingested it. Almost every analytical query is
"the last 30 days", which then reads 30 directories instead of all 180.

```
data/silver/review_date=2026-05-01/part-0000.parquet
```

Silver **replaces** a partition rather than appending to it. It is a derived
layer: re-running enrichment after fixing a bug should produce a corrected
Silver, not two contradictory copies of the same review. Bronze remains the
immutable record, so rewriting here loses nothing.

---

## Measured performance

Full run, 5,150 Bronze rows on a 16-core CPU:

| Stage | Duration | Throughput |
|---|---|---|
| Ingestion | 0.33s | 15,514 rows/s |
| Validation | 0.83s | 5,709 rows/s |
| Language detection | 6.75s | 700 rows/s |
| Topic classification | 0.34s | 13,845 rows/s |
| Sentiment — lexicon | 0.06s | 76,768 rows/s |
| **Sentiment — transformer** | — | **30 rows/s** |

Sentiment on CPU dominates by three orders of magnitude. That is not a defect;
it is 278 million parameters doing real work. It is also why the lexicon
backend exists, and why the Phase 8 benchmark will report both.

### Three optimisations found by measuring

**Transformers batching: 12 → 30 rows/s.** A `transformers` pipeline handed a
list processes it **one item at a time** unless `batch_size` is set on the
pipeline. It looks batched, reads as batched, and runs sequentially. This was
the single largest win in the phase.

**Topic alternation regexes: 1,552 → 13,845 rows/s (9x).** The naive form
compiled one regex per keyword and ran ~200 searches per review. Combining each
topic's keywords into a single alternation runs 20. Longest-first ordering
matters, because regex alternation is first-match-wins and `service` would
otherwise shadow `customer service`.

**Truncating text for detection: 10.60 → 6.75s.** Language is identifiable long
before a review ends, so only the first 300 characters are used. The resulting
distribution is byte-identical — no accuracy was traded for the speed.

---

## Bugs found by running it

**`HF_HOME` was silently ignored.** It was set in `.env`, read into our settings
object, and never reached `os.environ` — which is where `transformers` actually
looks. The 1.1 GB model downloaded to the default cache instead of the
configured path, with no error. Settings now export it explicitly *before*
transformers is imported.

**The tokenizer needs two undeclared dependencies.** XLM-RoBERTa is
SentencePiece-based, and converting it needs `sentencepiece` **and** `protobuf`.
Missing either fails deep inside a traceback that ends up mentioning `tiktoken`
— a thoroughly misleading place to start debugging. Both are now in the `nlp`
extra.

**The test suite was reading the developer's `.env`.** The `settings` fixture
inherited `PENSIEVE_SENTIMENT_BACKEND=transformers`, so the "fast" unit suite
silently loaded the real model — 52 seconds, and one confusing failure where a
test asserting `lexicon-v1` saw a Cardiff version string. The fixture now pins
the backend, matching what CI does.

**A unit test depended on the network.** `test_a_nonexistent_model_fails_loudly`
reached Hugging Face and spent ~30 seconds retrying — longer than the rest of
the suite combined, and it would behave differently offline. Setting
`HF_HUB_OFFLINE=1` makes it fail immediately and deterministically. Suite time:
46s → 19.7s.

**"never" is not a negative word.** The lexicon classified *"Always in stock, I
have never had trouble finding it"* as negative. Removed — and the case became
a regression test, plus the clearest demonstration of why the transformer is
the default.

---

## Files

| File | Role |
|---|---|
| `pipelines/enrichment/language.py` | Lingua wrapper, confidence floor, supported/unsupported split |
| `pipelines/enrichment/sentiment.py` | Backend protocol, transformer and lexicon implementations |
| `pipelines/enrichment/topic_rules.py` | Multilingual keyword sets — the editable part |
| `pipelines/enrichment/topics.py` | Scoring, primary selection, explanation |
| `pipelines/enrichment/silver.py` | Silver contract, partitioned writer and reader |
| `pipelines/enrichment/service.py` | Orchestration |
| `pipelines/jobs/run_pipeline.py` | End-to-end runner with per-stage telemetry |

---

## What Phase 4 hands to Phase 5

A Silver layer with one row per review and everything known about it:

```
identity    review_id  brand  product  country  source  rating  created_at
text        text  normalized_text
language    language  language_confidence  language_detected_name
sentiment   sentiment  sentiment_score  sentiment_model_version
topics      primary_topic  topics  topic_match_reason
features    word_count  character_count  emoji_count  exclamation_count
            uppercase_ratio  has_url  has_mention
dedup       content_fingerprint  is_duplicate_of
lineage     ingestion_batch_id  processing_version  processed_at
```

Phase 5 reads this with PySpark and produces **Gold** — eight aggregate
datasets, plus statistical anomaly detection.

Everything Gold needs is now present:

- `sentiment` + `created_at` + `brand` → `daily_brand_metrics`, `sentiment_trends`
- `primary_topic` + `brand` + date → `daily_topic_metrics`, and the fastest-growing complaint
- `country` → `country_metrics`
- `language` → `language_distribution`
- `is_duplicate_of` → aggregations that must not double-count
- The **injected delivery-complaint spike** in the final 14 days is now visible
  as real `sentiment=negative, primary_topic=delivery` rows — which is exactly
  the signal anomaly detection has to find without being told it exists.

---

## Where this sits

```
Phase 2   raw file      -> Bronze          nothing lost
Phase 3   Bronze        -> clean records   nothing rejected without a reason
Phase 4   clean records -> Silver          language, sentiment, topics   <- you are here
Phase 5   Silver        -> Gold            aggregation and anomalies
```
