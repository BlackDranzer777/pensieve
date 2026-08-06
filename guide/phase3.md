# Phase 3 — Validation, Quarantine, Cleaning and Data Quality

**Status: complete.** Every number below was measured on a real 5,150-row run.

---

## What this phase is about, in one sentence

Phase 3 decides **which records can be trusted**, **explains every rejection**,
and **cleans the survivors** — without ever silently discarding anything.

---

## Why it exists

Phase 2 deliberately put broken records into Bronze. That was the right choice:
Bronze is the immutable record of what actually arrived. But nothing downstream
can compute an average rating from `"seven"`, or place a review on a trend line
when its date is `2026-13-45`.

Something has to draw the line between usable and unusable. That is this phase.

The hard part is not detecting bad data — it is **being accountable about it**.
Any pipeline can call `dropna()`. The difference between a data platform and a
script is whether you can answer:

- How many records did we reject, and why?
- Which field failed, and what was the value?
- Is this batch's data quality better or worse than last week's?
- If a business number looks wrong, was the input bad or is the logic wrong?

A pipeline that quietly drops 8% of its input and reports confident metrics on
the rest is worse than no pipeline, because nobody knows to distrust it.

---

## How it relates to Phase 2

They are two halves of one contract.

| | Phase 2 (Bronze) | Phase 3 (Validation) |
|---|---|---|
| **Promise** | Nothing is lost or altered | Nothing is rejected without a reason |
| **Types** | Everything is a string | Valid records become typed |
| **Bad rows** | Kept, unmodified | Copied to quarantine with an explanation |
| **Text** | Exactly as it arrived | `normalized_text` added; original kept |
| **Rejects?** | Never | Yes, but never destroys — always copies |

Phase 3 **reads** Bronze and never writes to it. Bronze stays immutable. This
means validation can be re-run any number of times — after fixing a rule, after
adding a language — and always against the same pristine input.

That is the direct payoff of Phase 2's "preserve everything as strings"
decision. Because `"seven"` survived ingestion, quarantine can show the person
who sent the file exactly what was wrong. Had ingestion coerced it to `NaN`, all
we could say is "some rating was missing".

**Concrete dependency:** Phase 3 cannot run without Phase 2. It reads Bronze
Parquet, and it uses the `ingestion_batch_id` and `source_row_number` that
Phase 2 attached, so a quarantined record can be traced back to a line number
in the original file.

---

## What it does, step by step

```
Bronze records
    -> check required columns        missing column = whole batch fails
    -> apply every rule to every row
    -> split valid / invalid
    -> write invalid to quarantine   with rule, field, value, reason
    -> normalise text                original preserved alongside
    -> derive text features
    -> assign real types             strings -> Int8, datetime
    -> mark content duplicates       marked, not deleted
    -> calculate the quality score
```

### 1. Schema check comes first

A missing **column** is different from a bad **row**. No amount of quarantining
fixes a file with no `text` column, so that aborts the batch with a clear
error rather than rejecting every row individually with an identical reason.

### 2. Six rules, all applied to every row

| Rule | Field | Severity |
|---|---|---|
| `review_id_missing` | review_id | error |
| `brand_missing` | brand | error |
| `text_invalid` | text | error |
| `rating_out_of_range` | rating | error |
| `created_at_invalid` | created_at | error |
| `review_id_duplicate` | review_id | error |
| `country_malformed` | country | **warning** |

Two design choices worth defending:

**Every rule runs on every row — we do not stop at the first failure.** A record
with both an invalid rating and a broken date reports both, because the person
fixing the upstream feed needs the whole list, not the first item.

**Rules are data, not control flow.** Each carries an id, a field, a severity
and a predicate. That means the API can describe the rule set to users, and the
dashboard can group quarantine reasons by `rule_id` instead of string-matching
error messages.

The `country_malformed` warning shows why severity matters: a typo'd country
code should annotate a review, not throw away an otherwise perfectly good one.

### 3. Quarantine, not deletion

Every failure writes a record carrying its original values plus:

```
batch_id · rule_id · failed_field · failed_value
failure_reason · severity · quarantined_at
```

A row breaking three rules produces three quarantine records — so the reasons
breakdown on the dashboard adds up honestly instead of under-counting.

### 4. Cleaning — structure, not expression

This is the restraint that matters most. We remove **noise**; we keep
**signal**.

| Removed | Kept |
|---|---|
| HTML tags and entities | Capitals — `TERRIBLE` is not `terrible` |
| Zero-width chars, BOM, soft hyphens | Emoji — a real sentiment signal |
| Broken and excessive whitespace | Exclamation marks (runs shortened to 2, not 1) |
| URLs, emails, @mentions → placeholders | The original text, always, in a separate column |

Lower-casing everything and stripping punctuation is the reflex move. It would
also delete exactly the intensity the Phase 4 sentiment model exists to detect.
`"TERRIBLE!!!"` and `"terrible."` are not the same review.

**The original `text` is never modified.** `normalized_text` is an additional
column, and both travel to the dashboard so the review drawer can show them
side by side.

### 5. Duplicates: two kinds, handled differently

| Kind | Meaning | Treatment |
|---|---|---|
| **Same `review_id`** | Upstream system fault | Quarantined — someone should know |
| **Same content, different id** | Customer submitted twice | **Kept and marked** with `is_duplicate_of` |

Content duplicates are found by hashing normalised brand + text, so
`"  GREAT  service!!! "` and `"<p>GREAT service!!</p>"` collide correctly.
Brand is included so two brands receiving the same generic praise are not
merged into one review.

Marking rather than deleting matters: *"how many people complained"* and *"how
many complaints were filed"* are different questions, and the dashboard should
answer both.

### 6. The quality score

```
quality_score = 100
              - 40 x invalid_rate
              - 20 x duplicate_rate
              - 25 x missing_required_rate
              - 15 x unparseable_date_rate
```

Clamped to [0, 100]. **The weights are a judgement call, not a law** — which is
why the score is versioned (`QUALITY_SCORE_VERSION`) and every component is
returned alongside it, so changing the weights cannot silently reinterpret
history.

The reasoning: invalid records are weighted heaviest because they are unusable.
Missing values come next — the record exists but is incomplete. Duplicates are
milder, since the information is present, merely repeated. Unparseable dates are
last, because a review with a broken timestamp still carries usable sentiment;
it just cannot be plotted.

An empty batch scores **0, not 100**. A perfect score for a batch containing
nothing would be actively misleading on a dashboard.

The score can always explain itself:

```
Quality score: 95.9 / 100  (formula v1.0.0)
  100.0  base
  -  3.3  invalid records: 421 of 5,150 (8.2% x weight 40)
  -  0.6  duplicate records: 150 of 5,150 (2.9% x weight 20)
  -  0.1  missing required values: 129 of 5,150 (0.5% x weight 25)
  -  0.1  unparseable dates: 47 of 5,150 (0.9% x weight 15)
  =  95.9
```

A score nobody can derive is a score nobody should trust.

---

## Measured results

Real run, 5,150 Bronze records:

```
rows in       : 5,150
valid         : 4,729
quarantined   : 421
failures      : 424      (three rows broke two rules each)
content dupes : 430
quality score : 95.89
duration      : 0.69s
```

Quarantine, by rule:

```
review_id_duplicate    150
text_invalid           111
rating_out_of_range     63
created_at_invalid      60
brand_missing           40
```

Those counts match what the generator injected — which is the point of
generating data with known defects.

Cleaning, on real rows:

```
RAW : '<div class="review"><strong>Vitamin D Drops niedostępny od miesięcy...</strong></div>'
NORM: 'Vitamin D Drops niedostępny od miesięcy, brak informacji o dostawie.'

RAW : '     Sabor horrible, amargo y con un regusto extraño.     '
NORM: 'Sabor horrible, amargo y con un regusto extraño.'
```

---

## Two bugs found here, both instructive

**`pd.NA` is not `None`.** `Series.map()` passes `pd.NA` for missing values, and
`pd.NA` raises `TypeError` on truth testing. A guard written as
`if text is None` passed every unit test — which only ever fed it `None` — and
crashed on the first real batch. Fixed with a single `isinstance(value, str)`
coercion applied across the module, plus a regression test that feeds it
`pd.NA`, `NaN` and `None`.

**`\w` does not match Unicode combining marks.** Counting words with
`\b\w[\w'-]*\b` split every Hindi word in two at the virama or nukta, so
`"स्वाद बहुत बढ़िया है"` counted as 8 words instead of 4. Replaced with
whitespace tokenisation keeping tokens that contain a word character — correct
across all six languages.

The second one is the kind of bug that never surfaces if you only test in
English. It would have quietly inflated `word_count` for an entire market.

---

## Files

| File | Role |
|---|---|
| `pipelines/validation/rules.py` | Rule definitions and the vectorised checks |
| `pipelines/validation/quarantine.py` | Quarantine writer and reader |
| `pipelines/validation/quality.py` | The quality score and its explanation |
| `pipelines/validation/service.py` | Orchestration |
| `pipelines/transformation/text.py` | Normalisation and feature extraction |
| `pipelines/transformation/dedup.py` | Content fingerprinting and duplicate marking |

---

## What Phase 3 hands to Phase 4

A set of **clean, typed, deduplicated records with derived features** — and,
crucially, a guarantee about them.

The columns Phase 4 receives:

```
review_id  brand  product  country  source
text                  the original, untouched
normalized_text       cleaned, ready for NLP
rating                Int8, guaranteed 1-5
created_at            datetime, guaranteed parseable and in range
word_count  character_count  emoji_count
exclamation_count  uppercase_ratio  has_url  has_mention
content_fingerprint  is_duplicate_of
```

### Why this is exactly what Phase 4 needs

Phase 4 runs language detection, a transformer sentiment model and topic
classification. Each of those depends on something Phase 3 provides:

- **Language detection needs clean text.** Lingua fed `"<p>Świetna cena</p>"`
  has to contend with HTML tokens that belong to no language. Feeding it
  `normalized_text` removes that noise — while `text` is still there if we ever
  need to check what was actually written.

- **The sentiment model must not waste time on garbage.** Running a 1.1 GB
  transformer over 421 records that were never valid is pure cost. Because
  Phase 3 rejected them first, Phase 4 only scores records worth scoring.

- **Topic classification needs normalised text but original casing.** Keyword
  matching against `"DELIVERY WAS LATE!!!"` works because normalisation removed
  the HTML and whitespace without flattening the words.

- **Derived features are already computed**, so Phase 4 adds only its three NLP
  columns rather than re-walking every string.

- **Guaranteed types remove an entire class of defensive code.** Phase 4 can
  assume `rating` is an integer 1-5 and `created_at` is a real timestamp,
  because anything else is already in quarantine.

Phase 4 then adds `language`, `language_confidence`, `sentiment`,
`sentiment_score`, `sentiment_model_version`, `primary_topic`, `topics[]` and
`topic_match_reason`, and writes the result to the **Silver** layer.

---

## What it does *not* do

Worth being explicit, because these are easy to assume:

- **No language detection.** `unsupported_language` records pass validation
  cleanly — they are valid reviews, just not in a language we support end to
  end. Phase 4 detects and flags them.
- **No sentiment or topics.** That is Phase 4.
- **No aggregation.** That is Phase 5.
- **No writing to Silver.** Phase 3 returns clean records in memory; Phase 4
  enriches them and persists the result.
- **No database.** Everything is still Parquet and pandas. PostgreSQL arrives
  in Phase 6.

---

## Where this sits

```
Phase 2   raw file      -> Bronze          nothing lost, nothing altered
Phase 3   Bronze        -> clean records   nothing rejected without a reason  <- you are here
Phase 4   clean records -> Silver          language, sentiment, topics
Phase 5   Silver        -> Gold            aggregation and anomalies
```
