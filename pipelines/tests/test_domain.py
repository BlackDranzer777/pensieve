"""Tests for the shared domain vocabulary.

These guard the contract that the pipeline and the API both depend on. A typo
in an enum value here would not raise anywhere — it would quietly produce rows
the dashboard filters out, which is exactly the kind of bug that is expensive
to find later.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

import pytest

from pipelines.common.domain import (
    EARLIEST_VALID_DATE,
    INPUT_COLUMNS,
    MAX_RATING,
    MAX_TEXT_LENGTH,
    MIN_RATING,
    MIN_TEXT_LENGTH,
    OPTIONAL_INPUT_COLUMNS,
    PROCESSING_VERSION,
    REQUIRED_INPUT_COLUMNS,
    SUPPORTED_INPUT_FORMATS,
    SUPPORTED_LANGUAGES,
    DataLayer,
    Language,
    PipelineStage,
    ReviewSource,
    RunStatus,
    Sentiment,
    Severity,
    Topic,
)


@pytest.mark.parametrize(
    "enum_cls",
    [Sentiment, Topic, Language, ReviewSource, PipelineStage, RunStatus, Severity, DataLayer],
)
def test_enum_values_are_unique_and_snake_case(enum_cls: type[StrEnum]) -> None:
    """Values become column contents and API filter strings, so they must be
    stable, unique and free of surprises like spaces or capitals."""
    values = [member.value for member in enum_cls]

    assert len(values) == len(set(values)), f"{enum_cls.__name__} has duplicate values"
    for value in values:
        assert value == value.lower(), f"{value!r} is not lowercase"
        assert " " not in value, f"{value!r} contains a space"
        assert value.replace("_", "").isalnum(), f"{value!r} has unexpected characters"


def test_every_supported_language_is_a_real_language_member() -> None:
    assert SUPPORTED_LANGUAGES.issubset(set(Language))


def test_unknown_and_unsupported_are_not_treated_as_supported() -> None:
    """`unknown` and `unsupported` are outcomes of detection, not languages we
    claim to support end to end."""
    assert Language.UNKNOWN not in SUPPORTED_LANGUAGES
    assert Language.UNSUPPORTED not in SUPPORTED_LANGUAGES


def test_supported_languages_cover_the_documented_set() -> None:
    assert {lang.value for lang in SUPPORTED_LANGUAGES} == {"en", "pl", "hi", "fr", "de", "es"}


def test_sentiment_has_an_explicit_unknown_state() -> None:
    """Model failures must be representable; a crashed batch cannot silently
    become 'neutral'."""
    assert Sentiment.UNKNOWN in set(Sentiment)


def test_topic_taxonomy_includes_the_other_fallback() -> None:
    assert Topic.OTHER in set(Topic)


def test_topic_taxonomy_matches_the_documented_business_topics() -> None:
    expected = {
        "price",
        "taste",
        "packaging",
        "delivery",
        "customer_support",
        "website_experience",
        "refunds",
        "availability",
        "product_quality",
        "sustainability",
        "other",
    }
    assert {topic.value for topic in Topic} == expected


def test_input_columns_are_required_plus_optional_without_overlap() -> None:
    assert set(REQUIRED_INPUT_COLUMNS).isdisjoint(OPTIONAL_INPUT_COLUMNS)
    assert set(INPUT_COLUMNS) == set(REQUIRED_INPUT_COLUMNS) | set(OPTIONAL_INPUT_COLUMNS)


def test_required_columns_cover_the_minimum_useful_review() -> None:
    """Without these five fields a review cannot be analysed at all."""
    assert set(REQUIRED_INPUT_COLUMNS) == {"review_id", "brand", "text", "rating", "created_at"}


def test_supported_formats_are_lowercase_with_a_leading_dot() -> None:
    for suffix in SUPPORTED_INPUT_FORMATS:
        assert suffix.startswith("."), f"{suffix!r} should start with a dot"
        assert suffix == suffix.lower()


def test_validation_bounds_are_sane() -> None:
    assert MIN_RATING < MAX_RATING
    assert 0 < MIN_TEXT_LENGTH < MAX_TEXT_LENGTH


def test_earliest_valid_date_is_an_iso_date() -> None:
    assert date.fromisoformat(EARLIEST_VALID_DATE).year == 2015


def test_processing_version_is_semver_shaped() -> None:
    """Silver rows are stamped with this; a malformed value would make version
    comparisons across reprocessing runs meaningless."""
    parts = PROCESSING_VERSION.split(".")

    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_pipeline_stages_are_declared_in_execution_order() -> None:
    assert list(PipelineStage) == [
        PipelineStage.INGESTION,
        PipelineStage.VALIDATION,
        PipelineStage.TRANSFORMATION,
        PipelineStage.ENRICHMENT,
        PipelineStage.AGGREGATION,
        PipelineStage.ANOMALY_DETECTION,
        PipelineStage.LOADING,
    ]


def test_enums_behave_as_plain_strings() -> None:
    """They are `StrEnum`s so they can be written straight into Parquet and
    compared against raw strings coming back from the database.

    The `str` annotation is the assertion that matters: it only type-checks
    because `StrEnum` members really are `str` instances.
    """
    sentiment: str = Sentiment.POSITIVE
    assert sentiment == "positive"
    assert f"{Topic.DELIVERY}" == "delivery"
    assert Sentiment("positive") is Sentiment.POSITIVE
