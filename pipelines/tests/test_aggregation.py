"""Tests for Gold aggregation and anomaly detection.

Gold datasets are tested through the DuckDB engine, which needs no JVM. The
Spark path runs the *same SQL* and is covered by a `spark`-marked test that CI
skips — the engines share one definition, so testing the logic once is enough.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipelines.aggregation.anomalies import (
    BASELINE_WINDOW_DAYS,
    MIN_PERCENTAGE_CHANGE,
    MIN_VOLUME,
    Z_SCORE_THRESHOLD,
    detect_anomalies,
    detect_topic_anomalies,
)
from pipelines.aggregation.engines import (
    SQL_DIR,
    create_engine,
    load_query,
    read_gold_dataset,
    write_gold_dataset,
)
from pipelines.aggregation.gold import ALL_GOLD_DATASETS, SQL_DATASETS, build_gold
from pipelines.aggregation.telemetry import record_pipeline_run, record_quality_result
from pipelines.common.config import PipelineSettings
from pipelines.common.domain import Severity
from pipelines.enrichment.service import enrich_batch


def daily_series(
    *,
    brand: str = "Aurora Foods",
    days: int = 40,
    value: float = 10.0,
    spike_from: int | None = None,
    spike_value: float = 60.0,
    volume: int = 50,
    noise: float = 0.0,
) -> pd.DataFrame:
    """Build a metric series, optionally with a spike at the end.

    `noise` adds a small deterministic wobble. Real metric series are never
    perfectly flat, and a flat baseline has zero standard deviation — which
    the detector floors, making every subsequent change look enormous. Tests
    about threshold sensitivity need a realistic baseline to be meaningful.
    """
    dates = pd.date_range("2026-01-01", periods=days).strftime("%Y-%m-%d").tolist()
    values = [value + (noise if index % 2 else -noise) for index in range(days)]
    if spike_from is not None:
        for index in range(spike_from, days):
            values[index] = spike_value
    return pd.DataFrame(
        {
            "review_date": dates,
            "brand": [brand] * days,
            "negative_percentage": values,
            "review_count": [volume] * days,
            "average_rating": [4.0] * days,
        }
    )


class TestSqlLibrary:
    def test_every_sql_dataset_has_a_file(self) -> None:
        for dataset in SQL_DATASETS:
            assert (SQL_DIR / f"{dataset}.sql").exists(), f"missing {dataset}.sql"

    def test_queries_load(self) -> None:
        for dataset in SQL_DATASETS:
            assert "SELECT" in load_query(dataset).upper()

    def test_missing_query_raises_clearly(self) -> None:
        with pytest.raises(FileNotFoundError, match="No SQL file"):
            load_query("not_a_real_dataset")

    def test_aggregations_exclude_duplicates(self) -> None:
        """Counting a duplicate twice would inflate volume and skew sentiment.

        Every aggregate over reviews must filter them out; the review still
        exists in Silver and still appears in the Review Explorer.
        """
        for dataset in SQL_DATASETS:
            sql = load_query(dataset).lower()
            assert "is_duplicate_of is null" in sql, f"{dataset} may double-count duplicates"

    def test_rolling_window_never_looks_ahead(self) -> None:
        """A centred window would leak tomorrow into today's baseline and make
        anomaly detection quietly circular."""
        sql = load_query("sentiment_trends").lower()

        assert "rows between 6 preceding and current row" in sql
        assert "following" not in sql


class TestEngineSelection:
    def test_duckdb_engine_is_selectable(self, settings: PipelineSettings) -> None:
        with create_engine("duckdb", settings) as engine:
            assert engine.name == "duckdb"

    def test_unknown_engine_raises(self, settings: PipelineSettings) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            create_engine("hadoop", settings)

    def test_engine_is_recorded_on_every_row(self, settings: PipelineSettings) -> None:
        """So a benchmark can always be traced back to what actually ran."""
        frame = pd.DataFrame({"brand": ["A"], "review_count": [5]})

        write_gold_dataset(frame, "test_dataset", settings.gold_path, "duckdb")
        stored = read_gold_dataset(settings.gold_path, "test_dataset")

        assert (stored["engine"] == "duckdb").all()
        assert "generated_at" in stored.columns

    def test_rewriting_replaces_rather_than_appends(self, settings: PipelineSettings) -> None:
        """Gold is derived and reproducible; a rerun should correct it."""
        frame = pd.DataFrame({"brand": ["A"], "review_count": [5]})

        write_gold_dataset(frame, "test_dataset", settings.gold_path, "duckdb")
        write_gold_dataset(frame, "test_dataset", settings.gold_path, "duckdb")

        assert len(read_gold_dataset(settings.gold_path, "test_dataset")) == 1

    def test_reading_a_missing_dataset_returns_empty(self, settings: PipelineSettings) -> None:
        assert read_gold_dataset(settings.gold_path, "never_written").empty


class TestAnomalyDetection:
    def test_detects_a_clear_spike(self) -> None:
        result = detect_anomalies(daily_series(spike_from=35))

        assert not result.empty
        assert (result["metric"] == "negative_sentiment_rate").any()

    def test_flat_series_produces_nothing(self) -> None:
        """No false positives on stable data — the property that decides
        whether anyone keeps looking at the alerts."""
        assert detect_anomalies(daily_series()).empty

    def test_low_volume_signals_are_ignored(self) -> None:
        """Two negative reviews out of three is 67% negative and means nothing."""
        noisy = daily_series(spike_from=35, volume=MIN_VOLUME - 1)

        assert detect_anomalies(noisy).empty

    def test_small_relative_change_is_ignored(self) -> None:
        """Statistically significant but commercially irrelevant."""
        subtle = daily_series(value=12.0, spike_from=35, spike_value=12.5)

        assert detect_anomalies(subtle).empty

    def test_insufficient_history_produces_nothing(self) -> None:
        short = daily_series(days=BASELINE_WINDOW_DAYS - 2, spike_from=1)

        assert detect_anomalies(short).empty

    def test_empty_input_returns_empty(self) -> None:
        assert detect_anomalies(pd.DataFrame()).empty

    def test_records_the_numbers_behind_the_finding(self) -> None:
        result = detect_anomalies(daily_series(spike_from=35))
        row = result.iloc[0]

        for column in (
            "current_value",
            "baseline_value",
            "percentage_change",
            "z_score",
            "review_count",
            "severity",
            "explanation",
        ):
            assert column in result.columns
        assert row["baseline_value"] < row["current_value"]
        assert row["percentage_change"] > MIN_PERCENTAGE_CHANGE

    def test_explanation_is_deterministic_and_checkable(self) -> None:
        """An alert nobody can verify gets ignored after the second false
        positive."""
        first = detect_anomalies(daily_series(spike_from=35)).iloc[0]["explanation"]
        second = detect_anomalies(daily_series(spike_from=35)).iloc[0]["explanation"]

        assert first == second
        assert "standard deviations" in first
        assert "baseline" in first

    def test_explanation_avoids_overstating_confidence(self) -> None:
        """A 7-day window does not support words like "significant"."""
        explanation = detect_anomalies(daily_series(spike_from=35)).iloc[0]["explanation"]

        for overclaim in ("significant", "confirmed", "proves", "certainly"):
            assert overclaim not in explanation.lower()

    def test_bigger_deviations_get_higher_severity(self) -> None:
        mild = detect_anomalies(daily_series(spike_from=38, spike_value=20.0))
        severe = detect_anomalies(daily_series(spike_from=38, spike_value=500.0))

        assert not mild.empty
        assert not severe.empty
        ranking = [s.value for s in Severity]
        assert ranking.index(severe.iloc[0]["severity"]) >= ranking.index(mild.iloc[0]["severity"])

    def test_direction_is_respected(self) -> None:
        """`negative_sentiment_rate` only fires on increases — negativity
        falling is good news, not an incident."""
        improving = daily_series(value=50.0, spike_from=35, spike_value=5.0)

        result = detect_anomalies(improving)

        if result.empty:
            return  # nothing fired at all, which also satisfies the rule
        assert result[result["metric"] == "negative_sentiment_rate"].empty

    def test_baseline_excludes_the_day_being_tested(self) -> None:
        """Including today in its own baseline drags the mean toward the value
        under test and hides exactly the spikes we look for."""
        result = detect_anomalies(daily_series(spike_from=39, spike_value=100.0))

        assert not result.empty
        assert result.iloc[0]["baseline_value"] == pytest.approx(10.0, abs=0.01)

    def test_topic_anomalies_carry_their_topic(self) -> None:
        frame = daily_series(spike_from=35)
        frame["topic"] = "delivery"

        result = detect_topic_anomalies(frame)

        assert not result.empty
        assert (result["topic"] == "delivery").all()

    def test_z_threshold_is_configurable(self) -> None:
        subtle = daily_series(value=10.0, noise=1.5, spike_from=38, spike_value=14.0)

        strict = detect_anomalies(subtle, z_threshold=10.0)
        lenient = detect_anomalies(subtle, z_threshold=Z_SCORE_THRESHOLD)

        assert strict.empty
        assert len(lenient) >= len(strict)


class TestTelemetry:
    def test_records_a_pipeline_run(self, settings: PipelineSettings) -> None:
        record_pipeline_run(
            run_id="run-1",
            batch_id="batch-1",
            status="success",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            duration_seconds=60.0,
            rows_in=100,
            rows_out=90,
            rows_quarantined=10,
            quality_score=95.0,
            stages=[{"stage": "ingestion", "status": "success"}],
            gold_root=settings.gold_path,
        )

        stored = read_gold_dataset(settings.gold_path, "pipeline_run_metrics")

        assert len(stored) == 1
        assert stored.iloc[0]["rows_per_second"] == pytest.approx(1.5)

    def test_telemetry_is_append_only(self, settings: PipelineSettings) -> None:
        """The point is the trend: "was this batch worse than last week's?"
        is unanswerable if last week's row was overwritten."""
        for index in range(3):
            record_pipeline_run(
                run_id=f"run-{index}",
                batch_id="batch-1",
                status="success",
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:01:00Z",
                duration_seconds=60.0,
                rows_in=100,
                rows_out=90,
                rows_quarantined=10,
                quality_score=95.0,
                stages=[],
                gold_root=settings.gold_path,
            )

        assert len(read_gold_dataset(settings.gold_path, "pipeline_run_metrics")) == 3

    def test_quality_results_are_one_row_per_rule(self, settings: PipelineSettings) -> None:
        """So the dashboard can GROUP BY rule instead of parsing JSON."""
        record_quality_result(
            run_id="run-1",
            batch_id="batch-1",
            recorded_at="2026-01-01T00:00:00Z",
            total_records=100,
            valid_records=90,
            invalid_records=10,
            duplicate_records=3,
            missing_required_cells=5,
            unparseable_dates=2,
            score=95.0,
            score_version="1.0.0",
            failures_by_rule={"rating_out_of_range": 6, "brand_missing": 4},
            gold_root=settings.gold_path,
        )

        stored = read_gold_dataset(settings.gold_path, "data_quality_metrics")

        assert len(stored) == 2
        assert set(stored["rule_id"]) == {"rating_out_of_range", "brand_missing"}

    def test_a_clean_batch_still_records_a_row(self, settings: PipelineSettings) -> None:
        record_quality_result(
            run_id="run-1",
            batch_id="batch-1",
            recorded_at="2026-01-01T00:00:00Z",
            total_records=100,
            valid_records=100,
            invalid_records=0,
            duplicate_records=0,
            missing_required_cells=0,
            unparseable_dates=0,
            score=100.0,
            score_version="1.0.0",
            failures_by_rule={},
            gold_root=settings.gold_path,
        )

        assert len(read_gold_dataset(settings.gold_path, "data_quality_metrics")) == 1


class TestBuildGold:
    def test_builds_every_dataset(self, silver_data: PipelineSettings) -> None:
        result = build_gold(engine_name="duckdb", settings=silver_data)

        for dataset in ALL_GOLD_DATASETS:
            assert dataset in result.datasets, f"{dataset} was not built"

    def test_records_which_engine_ran(self, silver_data: PipelineSettings) -> None:
        result = build_gold(engine_name="duckdb", settings=silver_data)

        assert result.engine == "duckdb"
        brand = read_gold_dataset(silver_data.gold_path, "daily_brand_metrics")
        assert (brand["engine"] == "duckdb").all()

    def test_brand_metrics_have_the_expected_columns(self, silver_data: PipelineSettings) -> None:
        build_gold(engine_name="duckdb", settings=silver_data)
        brand = read_gold_dataset(silver_data.gold_path, "daily_brand_metrics")

        for column in (
            "review_date",
            "brand",
            "review_count",
            "average_rating",
            "positive_percentage",
            "negative_percentage",
        ):
            assert column in brand.columns

    def test_percentages_are_within_range(self, silver_data: PipelineSettings) -> None:
        build_gold(engine_name="duckdb", settings=silver_data)
        brand = read_gold_dataset(silver_data.gold_path, "daily_brand_metrics")

        assert brand["negative_percentage"].between(0, 100).all()
        assert brand["positive_percentage"].between(0, 100).all()

    def test_counts_reconcile_with_silver(self, silver_data: PipelineSettings) -> None:
        """Gold must not invent or lose reviews."""
        from pipelines.enrichment.silver import read_silver

        build_gold(engine_name="duckdb", settings=silver_data)
        silver = read_silver(silver_data.silver_path)
        brand = read_gold_dataset(silver_data.gold_path, "daily_brand_metrics")

        non_duplicate = silver["is_duplicate_of"].isna().sum()
        assert brand["review_count"].sum() == non_duplicate

    def test_empty_silver_fails_with_a_useful_message(self, settings: PipelineSettings) -> None:
        with pytest.raises(FileNotFoundError, match="run_pipeline"):
            build_gold(engine_name="duckdb", settings=settings)

    def test_anomaly_ids_are_unique(self, silver_data: PipelineSettings) -> None:
        """Regression: `anomaly_id` must identify exactly one row.

        It originally omitted `topic` and `country`, so a brand-level anomaly
        and a topic-level anomaly on the same brand, metric and day shared an
        id — 160 rows across 146 ids on the real dataset. Nothing surfaced it
        until the Postgres loader used the id as a primary key and 14 rows
        collided.
        """
        build_gold(engine_name="duckdb", settings=silver_data)
        anomalies = read_gold_dataset(silver_data.gold_path, "anomalies")

        duplicated = anomalies["anomaly_id"].duplicated().sum()
        assert duplicated == 0, f"{duplicated} anomaly ids are not unique"


@pytest.mark.spark
class TestSparkEngine:
    """Runs the same SQL through Spark. Skipped in CI (needs Java 17+)."""

    def test_spark_produces_the_same_results_as_duckdb(self, settings: PipelineSettings) -> None:
        pytest.importorskip("pyspark")

        rows = 200
        dates = pd.date_range("2026-03-01", periods=10)
        frame = pd.DataFrame(
            {
                "review_id": [f"r{i}" for i in range(rows)],
                "brand": ["Aurora Foods"] * rows,
                "product": ["Oat Crunch Cereal"] * rows,
                "country": ["GB"] * rows,
                "source": ["web"] * rows,
                "rating": pd.array([5, 1] * (rows // 2), dtype="Int8"),
                "created_at": [dates[i % 10] for i in range(rows)],
                "text": [f"The delivery was fast, review {i}." for i in range(rows)],
                "normalized_text": [f"The delivery was fast, review {i}." for i in range(rows)],
                "ingestion_batch_id": ["batch-1"] * rows,
            }
        )
        enrich_batch(frame, settings=settings)

        build_gold(engine_name="duckdb", settings=settings)
        duck = read_gold_dataset(settings.gold_path, "daily_brand_metrics")

        build_gold(engine_name="spark", settings=settings)
        spark = read_gold_dataset(settings.gold_path, "daily_brand_metrics")

        assert len(duck) == len(spark)
        assert duck["review_count"].sum() == spark["review_count"].sum()
