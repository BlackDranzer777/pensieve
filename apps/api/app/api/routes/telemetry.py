"""Pipeline run, data quality, upload and trigger endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep
from app.database.session import get_db_session
from app.schemas.common import Page
from app.schemas.telemetry import (
    DataQualityReport,
    DatasetUploadResult,
    PipelineRunAccepted,
    PipelineRunDetail,
    PipelineRunOut,
    QualityTrendPoint,
)
from app.services.datasets import DatasetService
from app.services.telemetry import TelemetryService
from pipelines.common.config import get_pipeline_settings

router = APIRouter(tags=["pipeline"])

SessionDep = Annotated[Session, Depends(get_db_session)]


def _telemetry(session: SessionDep) -> TelemetryService:
    return TelemetryService(session)


def _datasets() -> DatasetService:
    return DatasetService(get_pipeline_settings())


TelemetryDep = Annotated[TelemetryService, Depends(_telemetry)]
DatasetDep = Annotated[DatasetService, Depends(_datasets)]


@router.get("/pipeline-runs", response_model=Page[PipelineRunOut], summary="Pipeline run history")
def list_runs(service: TelemetryDep, pagination: PaginationDep) -> Page[PipelineRunOut]:
    return service.runs(pagination)


@router.get(
    "/pipeline-runs/{run_id}",
    response_model=PipelineRunDetail,
    summary="One run with its stage timeline",
)
def get_run(service: TelemetryDep, run_id: uuid.UUID) -> PipelineRunDetail:
    return service.run_detail(run_id)


@router.get(
    "/data-quality",
    response_model=DataQualityReport,
    summary="Quality results for a run, defaulting to the latest",
)
def data_quality(
    service: TelemetryDep,
    run_id: Annotated[uuid.UUID | None, Query(description="Defaults to the latest run")] = None,
) -> DataQualityReport:
    return service.data_quality(run_id)


@router.get(
    "/data-quality/trend",
    response_model=list[QualityTrendPoint],
    summary="Quality score across recent runs",
)
def data_quality_trend(
    service: TelemetryDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
) -> list[QualityTrendPoint]:
    return service.quality_trend(limit)


@router.post(
    "/datasets/upload",
    response_model=DatasetUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset file",
)
async def upload_dataset(
    service: DatasetDep,
    file: Annotated[UploadFile, File(description="CSV, JSON, JSONL or Parquet")],
) -> DatasetUploadResult:
    """Store an uploaded file. Ingestion is a separate call.

    The whole body is read into memory, which is safe only because the service
    enforces a size cap — and it checks the real length after reading, not the
    client's `Content-Length`, which a client is free to lie about.
    """
    content = await file.read()
    return service.store_upload(file.filename or "upload", content)


@router.post(
    "/pipelines/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a pipeline run in the background",
)
def run_pipeline(service: DatasetDep) -> PipelineRunAccepted:
    """Start a run and return immediately.

    **202, not 200.** A full run takes minutes; claiming completion in the
    response would be a lie the client has no way to check. Poll
    `/pipeline-runs` for the outcome.
    """
    return service.trigger_pipeline()
