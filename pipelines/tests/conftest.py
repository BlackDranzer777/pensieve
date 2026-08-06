"""Shared fixtures for pipeline tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from pipelines.common.config import PipelineSettings
from pipelines.ingestion.generator import GeneratorConfig, generate_reviews

#: A pinned end date so generated data never depends on when the tests run.
FIXED_END_DATE = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> PipelineSettings:
    """Settings pointing at an isolated temporary data root.

    The sentiment backend is pinned to `lexicon` rather than inherited from
    the developer's `.env`. Without this the suite silently loads the real
    1.1 GB transformer — it took 52 seconds and produced a confusing failure
    where a test asserting `lexicon-v1` saw a Cardiff model version. Tests
    must not depend on local configuration.
    """
    configured = PipelineSettings(
        PENSIEVE_DATA_ROOT=str(tmp_path),
        PENSIEVE_SENTIMENT_BACKEND="lexicon",
    )
    configured.ensure_directories()
    return configured


@pytest.fixture
def clean_reviews() -> pd.DataFrame:
    """200 well-formed reviews with no injected defects."""
    from pipelines.ingestion.generator import DirtyRecordConfig

    return generate_reviews(
        config=GeneratorConfig(
            rows=200,
            seed=1,
            end_date=FIXED_END_DATE,
            dirty=DirtyRecordConfig(
                duplicate_rate=0.0,
                missing_text_rate=0.0,
                invalid_rating_rate=0.0,
                broken_date_rate=0.0,
                html_in_text_rate=0.0,
                odd_unicode_rate=0.0,
                excess_whitespace_rate=0.0,
                unsupported_language_rate=0.0,
                missing_brand_rate=0.0,
                very_short_text_rate=0.0,
            ),
            inject_anomaly=False,
        )
    )


@pytest.fixture
def messy_reviews() -> pd.DataFrame:
    """500 reviews including the full range of injected defects."""
    return generate_reviews(config=GeneratorConfig(rows=500, seed=7, end_date=FIXED_END_DATE))


@pytest.fixture
def csv_file(tmp_path: Path, messy_reviews: pd.DataFrame) -> Iterator[Path]:
    """A CSV on disk containing the messy dataset."""
    path = tmp_path / "reviews.csv"
    messy_reviews.to_csv(path, index=False, encoding="utf-8")
    yield path
