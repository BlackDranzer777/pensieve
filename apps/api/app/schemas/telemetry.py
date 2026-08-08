"""Response models for pipeline runs and data quality."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

ORM = ConfigDict(from_attributes=True)


class StageRunOut(BaseModel):
    model_config = ORM

    stage_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    rows_in: int | None
    rows_out: int | None
    retry_count: int
    error_message: str | None


class PipelineRunOut(BaseModel):
    model_config = ORM

    id: uuid.UUID
    batch_id: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    input_rows: int
    output_rows: int
    failed_rows: int
    quarantined_rows: int
    duplicate_rows: int
    rows_per_second: float | None
    quality_score: float | None
    error_message: str | None


class PipelineRunDetail(PipelineRunOut):
    """A run with its stage timeline.

    The stages are what make a slow run diagnosable: a total duration says
    something is slow, the per-stage split says what.
    """

    stages: list[StageRunOut] = []


class QualityRuleResult(BaseModel):
    model_config = ORM

    rule_id: str
    check_name: str | None
    status: str
    severity: str | None
    affected_rows: int


class DataQualityReport(BaseModel):
    """The data-quality page in one response.

    `rules` includes rules that passed. Showing only failures makes "the rule
    did not run" and "the rule found nothing" look identical, which is the
    difference between a clean batch and a broken validator.
    """

    run_id: uuid.UUID | None
    batch_id: str | None
    recorded_at: datetime | None
    quality_score: float | None
    total_records: int
    valid_records: int
    quarantined_records: int
    duplicate_records: int
    validity_rate: float | None
    rules: list[QualityRuleResult] = []


class QualityTrendPoint(BaseModel):
    """One run's quality score, for the trend chart."""

    run_id: uuid.UUID
    started_at: datetime
    quality_score: float | None
    input_rows: int
    quarantined_rows: int


class DatasetUploadResult(BaseModel):
    """What happened to an uploaded file.

    Reports where the file landed and how many rows were detected, but does
    **not** claim anything was processed — upload and ingestion are separate
    steps, and conflating them would mean reporting success before validation
    has had a chance to reject anything.
    """

    filename: str
    stored_path: str
    size_bytes: int
    detected_rows: int | None
    message: str


class PipelineRunAccepted(BaseModel):
    """Acknowledgement that a run was started.

    Returned with 202, not 200: the run is still going when this is sent.
    Poll `/pipeline-runs` for the outcome.
    """

    started: bool
    message: str
    poll_url: str
