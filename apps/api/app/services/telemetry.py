"""Business logic for pipeline runs and data quality."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import NotFoundError
from app.repositories.telemetry import TelemetryRepository
from app.schemas.common import Page, PageMeta
from app.schemas.telemetry import (
    DataQualityReport,
    PipelineRunDetail,
    PipelineRunOut,
    QualityRuleResult,
    QualityTrendPoint,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.api.deps import Pagination


class TelemetryService:
    def __init__(self, session: Session) -> None:
        self._repo = TelemetryRepository(session)

    def runs(self, pagination: Pagination) -> Page[PipelineRunOut]:
        runs, total = self._repo.runs(pagination)
        return Page[PipelineRunOut](
            items=[PipelineRunOut.model_validate(run) for run in runs],
            meta=PageMeta.build(pagination.page, pagination.page_size, total),
        )

    def run_detail(self, run_id: uuid.UUID) -> PipelineRunDetail:
        run = self._repo.run_by_id(run_id)
        if run is None:
            raise NotFoundError(f"Pipeline run '{run_id}' was not found.")
        return PipelineRunDetail.model_validate(run)

    def data_quality(self, run_id: uuid.UUID | None = None) -> DataQualityReport:
        """The quality report for one run, defaulting to the most recent.

        An empty report is returned rather than a 404 when no run exists yet.
        A dashboard opened before the first pipeline run should say "no data",
        not show an error — nothing is broken.
        """
        run = self._repo.run_by_id(run_id) if run_id else self._repo.latest_run()
        if run is None:
            if run_id is not None:
                raise NotFoundError(f"Pipeline run '{run_id}' was not found.")
            return DataQualityReport(
                run_id=None,
                batch_id=None,
                recorded_at=None,
                quality_score=None,
                total_records=0,
                valid_records=0,
                quarantined_records=0,
                duplicate_records=0,
                validity_rate=None,
                rules=[],
            )

        totals = self._repo.quality_totals(run.id)
        rules = self._repo.quality_results_for(run.id)
        return DataQualityReport(
            run_id=run.id,
            batch_id=run.batch_id,
            recorded_at=run.completed_at or run.started_at,
            quality_score=run.quality_score,
            rules=[QualityRuleResult.model_validate(rule) for rule in rules],
            **totals,
        )

    def quality_trend(self, limit: int = 30) -> list[QualityTrendPoint]:
        return [
            QualityTrendPoint(
                run_id=run.id,
                started_at=run.started_at,
                quality_score=run.quality_score,
                input_rows=run.input_rows,
                quarantined_rows=run.quarantined_rows,
            )
            for run in self._repo.quality_trend(limit)
        ]
