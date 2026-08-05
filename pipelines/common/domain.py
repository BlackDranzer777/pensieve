"""Shared domain vocabulary for Pensieve.

This module is the single source of truth for the enumerations that both the
pipeline and the API must agree on. Defining them once prevents the classic
drift where a pipeline starts emitting a new topic that the dashboard silently
drops on the floor.

Deliberately dependency-free (stdlib only) so any layer can import it cheaply.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Processing version
# ---------------------------------------------------------------------------
# Stamped onto every Silver row. Bump whenever the meaning of an enriched field
# changes (new cleaning rule, different model, changed topic keywords) so that
# rows produced by different logic remain distinguishable after the fact.
PROCESSING_VERSION: Final[str] = "1.0.0"

# Bump when the quality-score weights change, so historical scores stay
# interpretable instead of silently shifting meaning.
QUALITY_SCORE_VERSION: Final[str] = "1.0.0"


class Sentiment(StrEnum):
    """Sentiment classes. `UNKNOWN` marks rows the model could not score."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class Topic(StrEnum):
    """Business topics a review can be about.

    `OTHER` is the explicit fallback when no keyword rule matches. It is a real
    category, not a failure: a healthy share of `other` tells us the taxonomy
    needs extending.
    """

    PRICE = "price"
    TASTE = "taste"
    PACKAGING = "packaging"
    DELIVERY = "delivery"
    CUSTOMER_SUPPORT = "customer_support"
    WEBSITE_EXPERIENCE = "website_experience"
    REFUNDS = "refunds"
    AVAILABILITY = "availability"
    PRODUCT_QUALITY = "product_quality"
    SUSTAINABILITY = "sustainability"
    OTHER = "other"


class Language(StrEnum):
    """Languages supported end to end (detection + sentiment + topic rules).

    Extending support means: add the ISO code here, add it to
    `LINGUA_LANGUAGES`, and add keyword translations to the topic rules. The
    pipeline records anything outside this set as `UNSUPPORTED`.
    """

    ENGLISH = "en"
    POLISH = "pl"
    HINDI = "hi"
    FRENCH = "fr"
    GERMAN = "de"
    SPANISH = "es"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


SUPPORTED_LANGUAGES: Final[frozenset[Language]] = frozenset(
    {
        Language.ENGLISH,
        Language.POLISH,
        Language.HINDI,
        Language.FRENCH,
        Language.GERMAN,
        Language.SPANISH,
    }
)


class ReviewSource(StrEnum):
    """Where a review came from. Unrecognised values normalise to `UNKNOWN`."""

    WEB = "web"
    APP = "app"
    EMAIL = "email"
    MARKETPLACE = "marketplace"
    SOCIAL = "social"
    UNKNOWN = "unknown"


class PipelineStage(StrEnum):
    """Ordered stages of a pipeline run. The order here is the execution order."""

    INGESTION = "ingestion"
    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    ENRICHMENT = "enrichment"
    AGGREGATION = "aggregation"
    ANOMALY_DETECTION = "anomaly_detection"
    LOADING = "loading"


class RunStatus(StrEnum):
    """Lifecycle of a pipeline run or an individual stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # completed, but some records were quarantined or failed


class Severity(StrEnum):
    """Anomaly severity. Assigned by deterministic thresholds, never guessed."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DataLayer(StrEnum):
    """Medallion layers, used for path resolution and logging."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    QUARANTINE = "quarantine"


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------
REQUIRED_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "review_id",
    "brand",
    "text",
    "rating",
    "created_at",
)

OPTIONAL_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "product",
    "country",
    "source",
)

INPUT_COLUMNS: Final[tuple[str, ...]] = REQUIRED_INPUT_COLUMNS + OPTIONAL_INPUT_COLUMNS

SUPPORTED_INPUT_FORMATS: Final[frozenset[str]] = frozenset({".csv", ".json", ".jsonl", ".parquet"})

# Business rules applied during validation. Kept here so the API can describe
# them to users without importing the validation machinery.
MIN_RATING: Final[int] = 1
MAX_RATING: Final[int] = 5
MIN_TEXT_LENGTH: Final[int] = 3
MAX_TEXT_LENGTH: Final[int] = 5_000
EARLIEST_VALID_DATE: Final[str] = "2015-01-01"
