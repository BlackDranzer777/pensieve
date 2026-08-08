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


@pytest.fixture
def silver_data(settings: PipelineSettings) -> PipelineSettings:
    """A small but dense Silver layer, written through the real pipeline.

    Dense on purpose: the aggregation guards reject cells below `MIN_VOLUME`,
    so a sparse fixture would produce zero anomalies and the tests would be
    asserting against an empty dataset without saying so.
    """
    from pipelines.enrichment.service import enrich_batch

    rows = 400
    dates = pd.date_range("2026-03-01", periods=20)
    positive = "The delivery was incredibly fast and the packaging was perfect!"
    negative = "The courier lost my parcel and the price is far too expensive."

    frame = pd.DataFrame(
        {
            "review_id": [f"r{i}" for i in range(rows)],
            "brand": ["Aurora Foods", "Nimbus Drinks"] * (rows // 2),
            "product": ["Oat Crunch Cereal"] * rows,
            "country": ["GB", "DE"] * (rows // 2),
            "source": ["web"] * rows,
            "rating": pd.array([5, 1] * (rows // 2), dtype="Int8"),
            "created_at": [dates[i % 20] for i in range(rows)],
            "text": [positive if i % 2 else negative for i in range(rows)],
            "normalized_text": [positive if i % 2 else negative for i in range(rows)],
            "ingestion_batch_id": ["batch-1"] * rows,
        }
    )
    enrich_batch(frame, settings=settings)
    return settings


@pytest.fixture
def gold_data(silver_data: PipelineSettings) -> PipelineSettings:
    """Silver, a full Gold build, and run telemetry.

    Telemetry is recorded explicitly because `build_gold` does not produce it —
    the two telemetry datasets describe *pipeline runs*, not reviews, so the
    runner appends them as it goes. A fixture that only called `build_gold`
    would leave them empty, and anything loading them would appear to work
    while moving zero rows.
    """
    from pipelines.aggregation.gold import build_gold
    from pipelines.aggregation.telemetry import record_pipeline_run, record_quality_result

    build_gold(engine_name="duckdb", settings=silver_data)

    record_pipeline_run(
        run_id="run-test-1",
        batch_id="batch-1",
        status="success",
        started_at="2026-03-01T00:00:00+00:00",
        completed_at="2026-03-01T00:01:00+00:00",
        duration_seconds=60.0,
        rows_in=420,
        rows_out=400,
        rows_quarantined=20,
        quality_score=95.0,
        stages=[
            {
                "stage": "ingestion",
                "status": "success",
                "started_at": "2026-03-01T00:00:00+00:00",
                "completed_at": "2026-03-01T00:00:30+00:00",
                "duration_seconds": 30.0,
                "rows_in": 420,
                "rows_out": 420,
                "retry_count": 0,
            }
        ],
        gold_root=silver_data.gold_path,
    )
    record_quality_result(
        run_id="run-test-1",
        batch_id="batch-1",
        recorded_at="2026-03-01T00:01:00+00:00",
        total_records=420,
        valid_records=400,
        invalid_records=20,
        duplicate_records=5,
        missing_required_cells=2,
        unparseable_dates=1,
        score=95.0,
        score_version="1.0.0",
        failures_by_rule={"rating_out_of_range": 20},
        gold_root=silver_data.gold_path,
    )
    return silver_data
