"""Silver -> Gold aggregation.

Produces eight business-ready datasets:

    daily_brand_metrics      date x brand          volume, rating, sentiment mix
    daily_topic_metrics      date x brand x topic  which complaints are growing
    country_metrics          date x country        geographic performance
    language_distribution    date x language       audience mix + detection health
    sentiment_trends         date x brand          with 7-day rolling baselines
    anomalies                detection events      statistical deviations
    data_quality_metrics     batch                 quality score over time
    pipeline_run_metrics     run                   duration, throughput, failures

The first five are SQL in `analytics/sql/`, executed by whichever engine you
choose. `anomalies` is computed in pandas because rolling z-scores over a small
result set are clearer that way than as a window-function SQL expression the
next reader has to decode.

The last two are **telemetry, not aggregation** — they describe pipeline runs
rather than reviews, so they are passed through from what `run_pipeline` wrote
rather than derived from Silver.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from pipelines.aggregation.anomalies import detect_anomalies, detect_topic_anomalies
from pipelines.aggregation.engines import (
    GoldEngine,
    create_engine,
    load_query,
    read_gold_dataset,
    write_gold_dataset,
)
from pipelines.common.config import PipelineSettings, get_pipeline_settings
from pipelines.common.logging import get_logger

log = get_logger(__name__)

#: Datasets defined as SQL and executed by the chosen engine.
SQL_DATASETS: tuple[str, ...] = (
    "daily_brand_metrics",
    "daily_topic_metrics",
    "country_metrics",
    "language_distribution",
    "sentiment_trends",
)

#: Telemetry written by the pipeline runner, not derived from Silver.
TELEMETRY_DATASETS: tuple[str, ...] = (
    "data_quality_metrics",
    "pipeline_run_metrics",
)

ALL_GOLD_DATASETS: tuple[str, ...] = (*SQL_DATASETS, "anomalies", *TELEMETRY_DATASETS)


@dataclass(frozen=True, slots=True)
class GoldResult:
    """Outcome of a Gold build."""

    engine: str
    silver_rows: int
    datasets: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    anomaly_count: int = 0

    @property
    def total_rows(self) -> int:
        return sum(self.datasets.values())


def build_gold(
    *,
    engine_name: str = "spark",
    settings: PipelineSettings | None = None,
) -> GoldResult:
    """Build every Gold dataset from Silver.

    Raises:
        EngineUnavailableError: the requested engine could not start. Never
            falls back silently — a DuckDB run you believed was Spark would
            invalidate every benchmark number without telling you.
        FileNotFoundError: Silver is empty. Run the pipeline first.
    """
    settings = settings or get_pipeline_settings()
    settings.ensure_directories()
    started = time.perf_counter()

    if not any(settings.silver_path.glob("review_date=*")):
        raise FileNotFoundError(
            f"Silver layer is empty at {settings.silver_path}.\n"
            "  Run:  python -m pipelines.jobs.run_pipeline"
        )

    counts: dict[str, int] = {}
    anomaly_count = 0

    with create_engine(engine_name, settings) as engine:
        silver_rows = engine.register_silver(settings.silver_path)

        for dataset in SQL_DATASETS:
            frame = engine.run_query(load_query(dataset))
            write_gold_dataset(frame, dataset, settings.gold_path, engine_name)
            counts[dataset] = len(frame)

        anomalies = _build_anomalies(engine, settings, engine_name)
        counts["anomalies"] = len(anomalies)
        anomaly_count = len(anomalies)

    for dataset in TELEMETRY_DATASETS:
        counts[dataset] = len(read_gold_dataset(settings.gold_path, dataset))

    duration = time.perf_counter() - started
    result = GoldResult(
        engine=engine_name,
        silver_rows=silver_rows,
        datasets=counts,
        duration_seconds=duration,
        anomaly_count=anomaly_count,
    )
    log.info(
        "gold_build_complete",
        engine=engine_name,
        silver_rows=silver_rows,
        datasets=len(counts),
        total_gold_rows=result.total_rows,
        anomalies=anomaly_count,
        duration_seconds=round(duration, 3),
    )
    return result


def _build_anomalies(
    engine: GoldEngine, settings: PipelineSettings, engine_name: str
) -> pd.DataFrame:
    """Detect anomalies at both brand and brand-x-topic level.

    Both are needed. A topic-level spike can be invisible at brand level:
    delivery complaints tripling while everything else improves leaves the
    overall negative rate flat.
    """
    brand_metrics = read_gold_dataset(settings.gold_path, "daily_brand_metrics")
    topic_metrics = read_gold_dataset(settings.gold_path, "daily_topic_metrics")

    frames = [
        detect_anomalies(brand_metrics),
        detect_topic_anomalies(topic_metrics),
    ]
    non_empty = [frame for frame in frames if not frame.empty]

    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else pd.DataFrame(
            columns=[
                "anomaly_id",
                "detected_date",
                "brand",
                "metric",
                "topic",
                "country",
                "current_value",
                "baseline_value",
                "percentage_change",
                "z_score",
                "review_count",
                "severity",
                "explanation",
            ]
        )
    )

    write_gold_dataset(combined, "anomalies", settings.gold_path, engine_name)
    return combined
