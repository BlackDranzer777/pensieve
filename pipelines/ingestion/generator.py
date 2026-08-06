"""Configurable synthetic review generator.

Produces realistic multilingual review data, deliberately including the kinds
of broken records that real feeds contain. Those bad rows are the point: a
platform that only ever sees clean input proves nothing about its validation,
quarantine or quality scoring.

Everything is driven by a seed. The same seed always produces byte-identical
output, so a demo, a benchmark and a test all describe the same dataset.

    generate_reviews(rows=10_000, seed=42)
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import pandas as pd

from pipelines.common.domain import Language, ReviewSource, Sentiment, Topic
from pipelines.common.logging import get_logger
from pipelines.ingestion.templates import (
    CLOSERS,
    OPENERS,
    TEMPLATES,
    UNSUPPORTED_LANGUAGE_SAMPLES,
)

log = get_logger(__name__)

DEFAULT_SEED: Final[int] = 42

#: A defect injector: takes a clean row and returns a damaged one.
type ReviewRow = dict[str, object]
type Damager = Callable[[ReviewRow, random.Random], ReviewRow]

# --- Dimensions -------------------------------------------------------------
# Brands carry a category so the BRANDS table has a real dimension to store,
# and so brand-level aggregates can be compared within a category.
BRANDS: Final[tuple[tuple[str, str], ...]] = (
    ("Aurora Foods", "food"),
    ("Nimbus Drinks", "beverage"),
    ("Verdant Care", "personal_care"),
    ("Kestrel Home", "household"),
    ("Solace Wellness", "wellness"),
)

PRODUCTS: Final[dict[str, tuple[str, ...]]] = {
    "Aurora Foods": ("Oat Crunch Cereal", "Wild Berry Jam", "Sourdough Crackers"),
    "Nimbus Drinks": ("Sparkling Elderflower", "Cold Brew Coffee", "Ginger Kombucha"),
    "Verdant Care": ("Aloe Face Wash", "Bamboo Toothbrush", "Rose Hand Cream"),
    "Kestrel Home": ("Linen Bedding Set", "Ceramic Mug", "Cast Iron Pan"),
    "Solace Wellness": ("Magnesium Complex", "Sleep Tea Blend", "Vitamin D Drops"),
}

# Country weighted towards the languages we support, so the language mix in the
# generated data is plausible rather than uniform.
COUNTRY_LANGUAGE: Final[tuple[tuple[str, Language, float], ...]] = (
    ("GB", Language.ENGLISH, 0.22),
    ("US", Language.ENGLISH, 0.18),
    ("IN", Language.HINDI, 0.14),
    ("DE", Language.GERMAN, 0.13),
    ("FR", Language.FRENCH, 0.12),
    ("ES", Language.SPANISH, 0.11),
    ("PL", Language.POLISH, 0.10),
)

SOURCES: Final[tuple[ReviewSource, ...]] = (
    ReviewSource.WEB,
    ReviewSource.APP,
    ReviewSource.MARKETPLACE,
    ReviewSource.EMAIL,
    ReviewSource.SOCIAL,
)

# Rating distribution per sentiment. Real review data is J-shaped — far more
# 5s and 1s than 3s — and sentiment correlates with rating without determining
# it, which keeps sentiment analysis a genuinely separate signal.
RATING_BY_SENTIMENT: Final[dict[Sentiment, tuple[tuple[int, float], ...]]] = {
    Sentiment.POSITIVE: ((5, 0.62), (4, 0.30), (3, 0.06), (2, 0.01), (1, 0.01)),
    Sentiment.NEUTRAL: ((3, 0.48), (4, 0.26), (2, 0.18), (5, 0.05), (1, 0.03)),
    Sentiment.NEGATIVE: ((1, 0.52), (2, 0.31), (3, 0.12), (4, 0.03), (5, 0.02)),
}

SENTIMENT_MIX: Final[tuple[tuple[Sentiment, float], ...]] = (
    (Sentiment.POSITIVE, 0.52),
    (Sentiment.NEGATIVE, 0.31),
    (Sentiment.NEUTRAL, 0.17),
)


@dataclass(frozen=True, slots=True)
class DirtyRecordConfig:
    """How much of each defect to inject, as a fraction of total rows.

    Defaults are deliberately generous — roughly 12% of rows carry some defect
    — so the quarantine and data-quality features have visible work to do in a
    demo. Real feeds are usually cleaner than this.
    """

    duplicate_rate: float = 0.030
    missing_text_rate: float = 0.015
    invalid_rating_rate: float = 0.012
    broken_date_rate: float = 0.012
    html_in_text_rate: float = 0.015
    odd_unicode_rate: float = 0.010
    excess_whitespace_rate: float = 0.010
    unsupported_language_rate: float = 0.008
    missing_brand_rate: float = 0.008
    very_short_text_rate: float = 0.010

    def total_rate(self) -> float:
        return (
            self.duplicate_rate
            + self.missing_text_rate
            + self.invalid_rating_rate
            + self.broken_date_rate
            + self.html_in_text_rate
            + self.odd_unicode_rate
            + self.excess_whitespace_rate
            + self.unsupported_language_rate
            + self.missing_brand_rate
            + self.very_short_text_rate
        )


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Everything that controls a generated dataset."""

    rows: int = 10_000
    seed: int = DEFAULT_SEED
    days: int = 180
    #: The most recent timestamp in the dataset. Defaults to *today at midnight
    #: UTC*, not `now()`, so two runs on the same day produce byte-identical
    #: output — which is what makes ingestion idempotent and benchmarks
    #: comparable. Pin it explicitly in tests for output that never changes.
    end_date: datetime | None = None
    dirty: DirtyRecordConfig = field(default_factory=DirtyRecordConfig)
    #: Give one brand a rising complaint trend so anomaly detection has a real
    #: signal to find rather than only noise.
    inject_anomaly: bool = True
    anomaly_brand: str = "Nimbus Drinks"
    anomaly_topic: Topic = Topic.DELIVERY

    def resolved_end_date(self) -> datetime:
        """The dataset's most recent timestamp.

        Truncating to midnight is what keeps generation deterministic within a
        day. Using `now()` directly would make every run produce a different
        file, so the checksum would never match and ingestion could never
        recognise a re-run as a duplicate.
        """
        if self.end_date is not None:
            return self.end_date
        return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _weighted_choice[T](rng: random.Random, options: tuple[tuple[T, float], ...]) -> T:
    """Pick one option using the supplied weights."""
    values = [value for value, _ in options]
    weights = [weight for _, weight in options]
    return rng.choices(values, weights=weights, k=1)[0]


def _pick_text(rng: random.Random, language: Language, topic: Topic, sentiment: Sentiment) -> str:
    """Compose review text: optional opener + template + optional closer.

    The fragments are what give the dataset realistic variety. With one
    template per (language, topic, sentiment) alone, distinct reviews would
    produce byte-identical text and the content deduplicator would report a
    ~46% duplicate rate that reflects the generator, not the data.
    """
    bank = TEMPLATES.get(language, TEMPLATES[Language.ENGLISH])
    by_sentiment = bank.get(topic) or TEMPLATES[Language.ENGLISH][topic]
    phrasings = by_sentiment.get(sentiment) or TEMPLATES[Language.ENGLISH][topic][sentiment]

    body = rng.choice(phrasings)
    opener = rng.choice(OPENERS.get(language, OPENERS[Language.ENGLISH]))
    closer = rng.choice(CLOSERS.get(language, CLOSERS[Language.ENGLISH]))

    if opener:
        # Lower-case the first letter so "Honestly, The price..." reads right.
        body = body[0].lower() + body[1:] if body[:1].isupper() else body
    return f"{opener}{body}{closer}"


def _clean_row(rng: random.Random, config: GeneratorConfig, index: int) -> dict[str, object]:
    """Build one well-formed review."""
    brand, _category = rng.choice(BRANDS)
    product = rng.choice(PRODUCTS[brand])
    country, language = _weighted_choice(
        rng,
        tuple(((code, lang), weight) for code, lang, weight in COUNTRY_LANGUAGE),
    )
    sentiment: Sentiment = _weighted_choice(rng, SENTIMENT_MIX)
    topic: Topic = rng.choice(tuple(t for t in Topic if t is not Topic.OTHER))

    end = config.resolved_end_date()
    created_at = end - timedelta(
        days=rng.randint(0, config.days - 1),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )

    # The injected anomaly: in the final 14 days, one brand's delivery
    # complaints rise sharply. Detection must find this without being told.
    days_from_end = (end - created_at).days
    if (
        config.inject_anomaly
        and brand == config.anomaly_brand
        and days_from_end <= 14
        and rng.random() < 0.55
    ):
        topic = config.anomaly_topic
        sentiment = Sentiment.NEGATIVE

    rating = _weighted_choice(rng, RATING_BY_SENTIMENT[sentiment])

    return {
        "review_id": f"rev-{index:08d}",
        "brand": brand,
        "product": product,
        "text": _pick_text(rng, language, topic, sentiment).replace("{product}", product),
        "country": country,
        "rating": str(rating),
        "source": rng.choice(SOURCES).value,
        "created_at": created_at.replace(microsecond=0).isoformat(),
    }


# --- Defect injectors -------------------------------------------------------
# Each takes a clean row and returns a damaged one. Kept as small named
# functions so tests can exercise them individually and the data dictionary can
# describe exactly what each defect looks like.


def _damage_missing_text(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["text"] = rng.choice(["", "   ", None])
    return row


def _damage_invalid_rating(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["rating"] = rng.choice(["0", "6", "11", "-2", "five", "", "4.5"])
    return row


def _damage_broken_date(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["created_at"] = rng.choice(
        ["not-a-date", "2026-13-45", "", "31/02/2025", "0000-00-00", "2099-01-01T00:00:00"]
    )
    return row


def _damage_html(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    text = str(row["text"])
    row["text"] = rng.choice(
        [
            f"<p>{text}</p>",
            f'<div class="review"><strong>{text}</strong></div>',
            f"{text}<br/><a href='http://spam.example.com'>click here</a>",
            f"&lt;b&gt;{text}&lt;/b&gt; &amp; more",
        ]
    )
    return row


def _damage_odd_unicode(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    text = str(row["text"])
    row["text"] = rng.choice(
        [
            f"﻿{text}",  # byte-order mark
            f"{text}​​",  # zero-width spaces
            text.replace(" ", " "),  # non-breaking spaces
            f"Ｔｈｉｓ　ｉｓ　ｗｉｄｅ： {text}",  # full-width characters
            f"{text} ́́́",  # stray combining accents
        ]
    )
    return row


def _damage_whitespace(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    text = str(row["text"])
    row["text"] = rng.choice(
        [f"     {text}     ", text.replace(" ", "    "), f"{text}\n\n\n\t\t{text}"]
    )
    return row


def _damage_unsupported_language(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["text"] = rng.choice(UNSUPPORTED_LANGUAGE_SAMPLES)
    return row


def _damage_missing_brand(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["brand"] = rng.choice(["", "   ", None])
    return row


def _damage_very_short(row: dict[str, object], rng: random.Random) -> dict[str, object]:
    row["text"] = rng.choice(["ok", "!", "5", "meh", ":)"])
    return row


def generate_reviews(
    rows: int = 10_000,
    seed: int = DEFAULT_SEED,
    *,
    config: GeneratorConfig | None = None,
) -> pd.DataFrame:
    """Generate a synthetic review dataset.

    Args:
        rows: Number of records to produce, including damaged ones.
        seed: Random seed. The same seed always yields identical output.
        config: Full configuration; `rows` and `seed` are ignored when given.

    Returns:
        A DataFrame with the input-contract columns, all as strings — matching
        what a real CSV export would look like, defects included.
    """
    config = config or GeneratorConfig(rows=rows, seed=seed)
    rng = random.Random(config.seed)  # noqa: S311 - reproducibility, not security

    records: list[dict[str, object]] = [
        _clean_row(rng, config, index) for index in range(config.rows)
    ]

    dirty = config.dirty
    damage_plan: tuple[tuple[str, float, Damager], ...] = (
        ("missing_text", dirty.missing_text_rate, _damage_missing_text),
        ("invalid_rating", dirty.invalid_rating_rate, _damage_invalid_rating),
        ("broken_date", dirty.broken_date_rate, _damage_broken_date),
        ("html_in_text", dirty.html_in_text_rate, _damage_html),
        ("odd_unicode", dirty.odd_unicode_rate, _damage_odd_unicode),
        ("excess_whitespace", dirty.excess_whitespace_rate, _damage_whitespace),
        ("unsupported_language", dirty.unsupported_language_rate, _damage_unsupported_language),
        ("missing_brand", dirty.missing_brand_rate, _damage_missing_brand),
        ("very_short_text", dirty.very_short_text_rate, _damage_very_short),
    )

    # Damage distinct rows so defects do not stack on the same record, which
    # would make the quarantine reason ambiguous.
    available = list(range(len(records)))
    rng.shuffle(available)
    cursor = 0
    applied: dict[str, int] = {}

    for name, rate, damage in damage_plan:
        count = min(int(config.rows * rate), len(available) - cursor)
        for _ in range(count):
            records[available[cursor]] = damage(records[available[cursor]], rng)
            cursor += 1
        applied[name] = count

    # Duplicates are appended rather than replacing rows: a duplicate is an
    # extra copy of an existing review, not a corruption of one.
    duplicate_count = int(config.rows * dirty.duplicate_rate)
    duplicates = [dict(records[rng.randrange(len(records))]) for _ in range(duplicate_count)]
    records.extend(duplicates)
    applied["duplicate"] = duplicate_count

    frame = pd.DataFrame(records).astype("string")

    log.info(
        "synthetic_data_generated",
        seed=config.seed,
        clean_rows=config.rows,
        total_rows=len(frame),
        defects=applied,
        defect_share=round(sum(applied.values()) / len(frame), 4),
    )
    return frame
