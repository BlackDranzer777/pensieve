"""End-to-end pipeline runner: Bronze -> validate -> enrich -> Silver.

    python -m pipelines.jobs.run_pipeline
    python -m pipelines.jobs.run_pipeline --batch-id 01KZBK...
    python -m pipelines.jobs.run_pipeline --sentiment-backend lexicon

Records per-stage telemetry — duration, rows in, rows out, throughput — which
is what Phase 6 loads into `pipeline_runs` and `pipeline_stage_runs` and what
the Pipeline Runs dashboard page displays.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - direct execution convenience
    sys.path.insert(0, str(REPO_ROOT))

from ulid import ULID  # noqa: E402

from pipelines.aggregation.telemetry import (  # noqa: E402
    record_pipeline_run,
    record_quality_result,
)
from pipelines.common.config import get_pipeline_settings  # noqa: E402
from pipelines.common.domain import PipelineStage, RunStatus  # noqa: E402
from pipelines.common.logging import configure_logging, get_logger  # noqa: E402
from pipelines.enrichment.service import enrich_batch  # noqa: E402
from pipelines.ingestion.bronze import read_bronze, read_bronze_batch  # noqa: E402
from pipelines.validation.service import ValidationResult, validate_batch  # noqa: E402

log = get_logger(__name__)


@dataclass
class StageRun:
    """Telemetry for one pipeline stage."""

    stage: PipelineStage
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_in: int = 0
    rows_out: int = 0
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None or self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def rows_per_second(self) -> float:
        duration = self.duration_seconds
        return 0.0 if duration <= 0 else self.rows_out / duration


@dataclass
class PipelineRun:
    """Telemetry for one end-to-end run."""

    run_id: str
    batch_id: str | None = None
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    stages: list[StageRun] = field(default_factory=list)
    quality_score: float = 0.0
    rows_in: int = 0
    rows_out: int = 0
    rows_quarantined: int = 0

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    def stage(self, stage: PipelineStage) -> StageRun:
        record = StageRun(stage=stage, started_at=datetime.now(UTC))
        self.stages.append(record)
        return record


def run_pipeline(
    *,
    batch_id: str | None = None,
    write: bool = True,
) -> PipelineRun:
    """Run validation and enrichment over Bronze data.

    Args:
        batch_id: Process only this batch. Default processes all of Bronze.
        write: Persist Silver and quarantine output.

    A stage failure marks the run FAILED and stops — continuing after a broken
    stage would write Silver records derived from data we know is wrong.
    """
    settings = get_pipeline_settings()
    settings.ensure_directories()
    run = PipelineRun(run_id=str(ULID()), batch_id=batch_id)

    # --- read Bronze ------------------------------------------------------
    stage = run.stage(PipelineStage.INGESTION)
    try:
        frame = (
            read_bronze_batch(settings.bronze_path, batch_id)
            if batch_id
            else read_bronze(settings.bronze_path)
        )
        stage.rows_in = stage.rows_out = len(frame)
        stage.status = RunStatus.SUCCESS
    except (FileNotFoundError, OSError, ValueError) as exc:
        stage.status = RunStatus.FAILED
        stage.error_message = str(exc)
        stage.completed_at = datetime.now(UTC)
        run.status = RunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        log.exception("pipeline_failed", stage=stage.stage.value, error=str(exc))
        return run
    stage.completed_at = datetime.now(UTC)

    if frame.empty:
        run.status = RunStatus.SUCCESS
        run.completed_at = datetime.now(UTC)
        log.warning("pipeline_no_data", bronze_path=str(settings.bronze_path))
        return run

    run.rows_in = len(frame)
    resolved_batch = batch_id or str(frame["ingestion_batch_id"].iloc[0])
    run.batch_id = resolved_batch

    # --- validate ---------------------------------------------------------
    stage = run.stage(PipelineStage.VALIDATION)
    stage.rows_in = len(frame)
    try:
        validation = validate_batch(frame, resolved_batch, settings=settings, write_rejects=write)
    except Exception as exc:
        stage.status = RunStatus.FAILED
        stage.error_message = str(exc)
        stage.completed_at = datetime.now(UTC)
        run.status = RunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        log.exception("pipeline_failed", stage=stage.stage.value, error=str(exc))
        return run

    stage.rows_out = validation.rows_out
    stage.status = RunStatus.PARTIAL if validation.rows_quarantined else RunStatus.SUCCESS
    stage.completed_at = datetime.now(UTC)
    run.quality_score = validation.quality.score
    run.rows_quarantined = validation.rows_quarantined

    # --- enrich -----------------------------------------------------------
    stage = run.stage(PipelineStage.ENRICHMENT)
    stage.rows_in = validation.rows_out
    try:
        enrichment = enrich_batch(validation.valid_records, settings=settings, write=write)
    except Exception as exc:
        stage.status = RunStatus.FAILED
        stage.error_message = str(exc)
        stage.completed_at = datetime.now(UTC)
        run.status = RunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        log.exception("pipeline_failed", stage=stage.stage.value, error=str(exc))
        return run

    stage.rows_out = enrichment.rows
    stage.status = RunStatus.SUCCESS
    stage.completed_at = datetime.now(UTC)

    run.rows_out = enrichment.rows
    run.status = RunStatus.PARTIAL if run.rows_quarantined else RunStatus.SUCCESS
    run.completed_at = datetime.now(UTC)

    if write:
        _record_telemetry(run, validation, settings.gold_path)

    log.info(
        "pipeline_complete",
        run_id=run.run_id,
        batch_id=run.batch_id,
        status=run.status.value,
        rows_in=run.rows_in,
        rows_out=run.rows_out,
        rows_quarantined=run.rows_quarantined,
        quality_score=run.quality_score,
        duration_seconds=round(run.duration_seconds, 3),
    )
    return run


def _record_telemetry(run: PipelineRun, validation: ValidationResult, gold_root: Path) -> None:
    """Persist run and quality telemetry as Gold datasets.

    Written here rather than derived in the Gold job because it describes the
    *pipeline*, not the reviews — Silver has no record of how long a run took
    or how many rows it rejected.
    """
    record_pipeline_run(
        run_id=run.run_id,
        batch_id=run.batch_id,
        status=run.status.value,
        started_at=run.started_at.isoformat(),
        completed_at=(run.completed_at or run.started_at).isoformat(),
        duration_seconds=run.duration_seconds,
        rows_in=run.rows_in,
        rows_out=run.rows_out,
        rows_quarantined=run.rows_quarantined,
        quality_score=run.quality_score,
        stages=[
            {
                "stage": stage.stage.value,
                "status": stage.status.value,
                "started_at": stage.started_at.isoformat() if stage.started_at else None,
                "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
                "duration_seconds": round(stage.duration_seconds, 3),
                "rows_in": stage.rows_in,
                "rows_out": stage.rows_out,
                "rows_per_second": round(stage.rows_per_second, 2),
                "retry_count": 0,
                "error_message": stage.error_message,
            }
            for stage in run.stages
        ],
        gold_root=gold_root,
    )

    quality = validation.quality
    record_quality_result(
        run_id=run.run_id,
        batch_id=run.batch_id,
        recorded_at=(run.completed_at or run.started_at).isoformat(),
        total_records=quality.total_records,
        valid_records=quality.valid_records,
        invalid_records=quality.invalid_records,
        duplicate_records=quality.duplicate_records,
        missing_required_cells=quality.missing_required_cells,
        unparseable_dates=quality.unparseable_dates,
        score=quality.score,
        score_version=quality.version,
        failures_by_rule=quality.failures_by_rule,
        gold_root=gold_root,
    )


def _print_report(run: PipelineRun) -> None:
    print(f"\nPipeline run {run.run_id}")
    print(f"  batch         : {run.batch_id}")
    print(f"  status        : {run.status.value}")
    print(f"  rows in       : {run.rows_in:,}")
    print(f"  rows to silver: {run.rows_out:,}")
    print(f"  quarantined   : {run.rows_quarantined:,}")
    print(f"  quality score : {run.quality_score}")
    print(f"  duration      : {run.duration_seconds:.2f}s")
    print("\n  stages:")
    for stage in run.stages:
        marker = {
            RunStatus.SUCCESS: "ok",
            RunStatus.PARTIAL: "partial",
            RunStatus.FAILED: "FAILED",
        }.get(stage.status, stage.status.value)
        print(
            f"    {stage.stage.value:<14} {marker:<8} "
            f"{stage.rows_in:>7,} -> {stage.rows_out:>7,}  "
            f"{stage.duration_seconds:6.2f}s  {stage.rows_per_second:>9,.0f} rows/s"
        )
        if stage.error_message:
            print(f"      error: {stage.error_message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Pensieve pipeline: Bronze -> Silver.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--batch-id", default=None, help="process only this batch")
    parser.add_argument(
        "--no-write", action="store_true", help="run without writing Silver or quarantine"
    )
    parser.add_argument(
        "--sentiment-backend",
        choices=["transformers", "lexicon"],
        default=None,
        help="override the configured sentiment backend",
    )
    args = parser.parse_args(argv)

    if args.sentiment_backend:
        import os

        os.environ["PENSIEVE_SENTIMENT_BACKEND"] = args.sentiment_backend
        get_pipeline_settings.cache_clear()

    settings = get_pipeline_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    started = time.perf_counter()
    run = run_pipeline(batch_id=args.batch_id, write=not args.no_write)
    _print_report(run)
    print(f"\n  wall clock: {time.perf_counter() - started:.2f}s")

    return 0 if run.status is not RunStatus.FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
