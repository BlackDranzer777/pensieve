"""Ingestion orchestration.

Implements the ingestion flow end to end:

    source file
        -> validate file type       (reject unsupported)
        -> read raw records          (everything as strings)
        -> compute checksum
        -> already ingested?         (yes: return the existing batch)
        -> store the original file
        -> write Bronze partition
        -> return an IngestionResult

The checksum step is what makes this safe to re-run. A retried job re-ingesting
the same file gets the original batch back instead of duplicating every row.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipelines.common.config import PipelineSettings, get_pipeline_settings
from pipelines.common.logging import get_logger
from pipelines.ingestion.batch import (
    BatchMetadata,
    build_batch_metadata,
    compute_checksum,
    find_batch_by_checksum,
    validate_source_format,
)
from pipelines.ingestion.bronze import batch_partition_path, write_bronze
from pipelines.ingestion.readers import read_source

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of ingesting one file."""

    batch: BatchMetadata
    partition_path: Path
    rows_ingested: int
    duration_seconds: float
    #: True when the file had already been ingested and nothing new was written.
    was_already_ingested: bool

    @property
    def rows_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.rows_ingested / self.duration_seconds


def ingest_file(
    source_path: Path,
    *,
    settings: PipelineSettings | None = None,
    generator_seed: int | None = None,
    force: bool = False,
) -> IngestionResult:
    """Ingest one file into Bronze.

    Args:
        source_path: File to ingest.
        settings: Overrides the process-wide settings; useful in tests.
        generator_seed: Recorded in the manifest when the file came from the
            synthetic generator, so the dataset can be reproduced exactly.
        force: Ingest again even if a batch with this checksum exists. Off by
            default because duplicating rows is almost never what you want.

    Raises:
        FileNotFoundError, UnsupportedFormatError, MalformedSourceError,
        EmptySourceError: all propagate with the reason intact. Ingestion
        failures must be loud — a silently skipped file is worse than a crash.
    """
    settings = settings or get_pipeline_settings()
    started = time.perf_counter()

    # Fail on an unsupported extension before reading a single byte.
    validate_source_format(source_path)

    checksum = compute_checksum(source_path)
    existing = None if force else find_batch_by_checksum(settings.bronze_path, checksum)
    if existing is not None:
        log.info(
            "batch_already_ingested",
            batch_id=existing.batch_id,
            checksum=checksum[:12],
            source_file=source_path.name,
        )
        return IngestionResult(
            batch=existing,
            partition_path=batch_partition_path(settings.bronze_path, existing),
            rows_ingested=0,
            duration_seconds=time.perf_counter() - started,
            was_already_ingested=True,
        )

    frame = read_source(source_path)
    batch = build_batch_metadata(source_path, row_count=len(frame), generator_seed=generator_seed)

    settings.bronze_path.mkdir(parents=True, exist_ok=True)
    partition = write_bronze(frame, batch, settings.bronze_path, source_path=source_path)

    duration = time.perf_counter() - started
    result = IngestionResult(
        batch=batch,
        partition_path=partition,
        rows_ingested=len(frame),
        duration_seconds=duration,
        was_already_ingested=False,
    )
    log.info(
        "ingestion_complete",
        batch_id=batch.batch_id,
        rows=result.rows_ingested,
        duration_seconds=round(duration, 3),
        rows_per_second=round(result.rows_per_second, 1),
    )
    return result


def ingest_dataframe(
    frame: pd.DataFrame,
    *,
    source_name: str,
    settings: PipelineSettings | None = None,
) -> IngestionResult:
    """Ingest an in-memory DataFrame by writing it to `data/samples/` first.

    Bronze must always be traceable to a real file, so rather than special-case
    in-memory input we persist it and then take the normal path. That keeps one
    ingestion code path instead of two that can drift.
    """
    settings = settings or get_pipeline_settings()
    settings.samples_path.mkdir(parents=True, exist_ok=True)

    staged = settings.samples_path / source_name
    frame.to_parquet(staged, engine="pyarrow", index=False)
    return ingest_file(staged, settings=settings)
