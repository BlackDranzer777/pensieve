"""Pipeline telemetry: run history and data-quality results over time.

Two of the eight Gold datasets describe **the pipeline**, not the reviews:

    pipeline_run_metrics    duration, throughput, rows, failures per run
    data_quality_metrics    the quality score for each batch, over time

They cannot be derived from Silver — Silver contains reviews, not run
history — so the pipeline runner appends to them as it goes.

These are append-only. Every run adds a row and none are rewritten, because
the point is the trend: "was this batch worse than last week's?" is only
answerable if last week's row still exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipelines.common.logging import get_logger

log = get_logger(__name__)


def append_gold_rows(rows: list[dict[str, object]], dataset: str, gold_root: Path) -> Path:
    """Append rows to an append-only Gold dataset.

    Each run writes its own part file rather than rewriting one shared file.
    Rewriting would mean a crash mid-write could lose the entire history, and
    concurrent runs would race for the same file.
    """
    if not rows:
        return gold_root / dataset

    target_dir = gold_root / dataset
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(target_dir.glob("part-*.parquet")))
    target = target_dir / f"part-{existing:04d}.parquet"

    pd.DataFrame(rows).to_parquet(target, engine="pyarrow", compression="snappy", index=False)
    log.info("telemetry_appended", dataset=dataset, rows=len(rows), path=str(target))
    return target


def record_pipeline_run(
    *,
    run_id: str,
    batch_id: str | None,
    status: str,
    started_at: str,
    completed_at: str,
    duration_seconds: float,
    rows_in: int,
    rows_out: int,
    rows_quarantined: int,
    quality_score: float,
    stages: list[dict[str, object]],
    gold_root: Path,
) -> None:
    """Record one pipeline run and its stages."""
    throughput = rows_out / duration_seconds if duration_seconds > 0 else 0.0

    append_gold_rows(
        [
            {
                "run_id": run_id,
                "batch_id": batch_id,
                "status": status,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": round(duration_seconds, 3),
                "rows_in": rows_in,
                "rows_out": rows_out,
                "rows_quarantined": rows_quarantined,
                "rows_per_second": round(throughput, 2),
                "quality_score": quality_score,
                "stage_count": len(stages),
                "failed_stages": sum(1 for s in stages if s.get("status") == "failed"),
                # Stages are stored as JSON in one column rather than a second
                # dataset. Phase 6 unpacks them into `pipeline_stage_runs`;
                # keeping them together here means a run and its stages cannot
                # be written half-way and end up inconsistent.
                "stages_json": json.dumps(stages),
            }
        ],
        "pipeline_run_metrics",
        gold_root,
    )


def record_quality_result(
    *,
    run_id: str,
    batch_id: str | None,
    recorded_at: str,
    total_records: int,
    valid_records: int,
    invalid_records: int,
    duplicate_records: int,
    missing_required_cells: int,
    unparseable_dates: int,
    score: float,
    score_version: str,
    failures_by_rule: dict[str, int],
    gold_root: Path,
) -> None:
    """Record the data-quality result for one batch.

    `failures_by_rule` is flattened into one row per rule rather than stored as
    a blob, so the Data Quality page can group quarantine reasons with a plain
    GROUP BY instead of parsing JSON in the API.
    """
    base: dict[str, object] = {
        "run_id": run_id,
        "batch_id": batch_id,
        "recorded_at": recorded_at,
        "total_records": total_records,
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "duplicate_records": duplicate_records,
        "missing_required_cells": missing_required_cells,
        "unparseable_dates": unparseable_dates,
        "quality_score": score,
        "score_version": score_version,
        "validity_rate": round(valid_records / total_records, 4) if total_records else 0.0,
    }

    rows: list[dict[str, object]] = []
    if failures_by_rule:
        rows.extend(
            {**base, "rule_id": rule_id, "rule_failure_count": count}
            for rule_id, count in failures_by_rule.items()
        )
    else:
        rows.append({**base, "rule_id": None, "rule_failure_count": 0})

    append_gold_rows(rows, "data_quality_metrics", gold_root)
