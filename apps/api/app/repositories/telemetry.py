"""Queries for pipeline runs and data quality."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import DataQualityResult, PipelineRun

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.api.deps import Pagination


class TelemetryRepository:
    """Reads run history and quality results."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def runs(self, pagination: Pagination) -> tuple[list[PipelineRun], int]:
        total = self._session.scalar(select(func.count()).select_from(PipelineRun)) or 0
        statement = (
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        return list(self._session.scalars(statement)), total

    def run_by_id(self, run_id: uuid.UUID) -> PipelineRun | None:
        statement = (
            select(PipelineRun)
            .options(selectinload(PipelineRun.stages))
            .where(PipelineRun.id == run_id)
        )
        return self._session.scalars(statement).first()

    def latest_run(self) -> PipelineRun | None:
        statement = (
            select(PipelineRun)
            .options(selectinload(PipelineRun.quality_results))
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        return self._session.scalars(statement).first()

    def quality_results_for(self, run_id: uuid.UUID) -> list[DataQualityResult]:
        statement = (
            select(DataQualityResult)
            .where(DataQualityResult.pipeline_run_id == run_id)
            .order_by(DataQualityResult.affected_rows.desc())
        )
        return list(self._session.scalars(statement))

    def quality_trend(self, limit: int = 30) -> list[PipelineRun]:
        """Recent runs, oldest first, for the score-over-time chart.

        Fetched newest-first so `limit` takes the *most recent* N, then
        reversed for display. Ordering ascending and limiting would return the
        oldest N instead — the opposite of what a trend chart wants.
        """
        statement = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        return list(reversed(list(self._session.scalars(statement))))

    def quality_totals(self, run_id: uuid.UUID) -> dict[str, Any]:
        """Row counts for one run, taken from the run record itself.

        Not summed from the rule results: a row can fail two rules, so adding
        `affected_rows` across rules double-counts it and can exceed the batch
        size — a number that is obviously wrong, but only if someone notices.
        """
        run = self._session.get(PipelineRun, run_id)
        if run is None:
            return {}
        return {
            "total_records": run.input_rows,
            "valid_records": run.output_rows,
            "quarantined_records": run.quarantined_rows,
            "duplicate_records": run.duplicate_rows,
            "validity_rate": (
                round(run.output_rows / run.input_rows * 100, 2) if run.input_rows else None
            ),
        }
