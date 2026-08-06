"""Validation orchestration: Bronze in, clean records + quarantine out.

Ties together the pieces of the validation stage:

    bronze records
        -> check required columns   (batch-level schema failure)
        -> apply row rules          (every rule on every row)
        -> split valid / invalid
        -> write invalid to quarantine with reasons
        -> normalise text + derive features on the valid records
        -> mark content duplicates
        -> calculate the quality score
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipelines.common.config import PipelineSettings, get_pipeline_settings
from pipelines.common.logging import get_logger
from pipelines.transformation.dedup import mark_duplicates
from pipelines.transformation.text import extract_features, normalize_text
from pipelines.validation.quality import QualityReport, calculate_quality
from pipelines.validation.quarantine import write_quarantine
from pipelines.validation.rules import (
    RuleSeverity,
    ValidationFailure,
    apply_rules,
    missing_required_columns,
)

log = get_logger(__name__)


class SchemaError(ValueError):
    """Raised when required columns are absent from the whole batch.

    Distinct from row-level failures: no amount of quarantining fixes a file
    that has no `text` column, so this aborts the batch rather than rejecting
    every row one at a time with an identical reason.
    """

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"Batch is missing required column(s): {', '.join(missing)}")
        self.missing = missing


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of validating one batch."""

    valid_records: pd.DataFrame
    quality: QualityReport
    failures: list[ValidationFailure]
    quarantine_path: Path | None
    duration_seconds: float
    exact_duplicates: int
    content_duplicates: int

    @property
    def rows_in(self) -> int:
        return self.quality.total_records

    @property
    def rows_out(self) -> int:
        return len(self.valid_records)

    @property
    def rows_quarantined(self) -> int:
        return self.quality.invalid_records


def enrich_valid_records(frame: pd.DataFrame) -> pd.DataFrame:
    """Add normalised text and derived features to records that passed.

    The original `text` column is untouched — `normalized_text` sits beside it,
    so the review drawer can show both and any cleaning bug stays diagnosable.
    """
    if frame.empty:
        return frame

    result = frame.copy()
    result["normalized_text"] = result["text"].fillna("").map(normalize_text)

    features = [extract_features(text) for text in result["text"].fillna("")]
    result["word_count"] = [f.word_count for f in features]
    result["character_count"] = [f.character_count for f in features]
    result["emoji_count"] = [f.emoji_count for f in features]
    result["exclamation_count"] = [f.exclamation_count for f in features]
    result["uppercase_ratio"] = [f.uppercase_ratio for f in features]
    result["has_url"] = [f.has_url for f in features]
    result["has_mention"] = [f.has_mention for f in features]

    # Now that rows are known valid, give them real types. Bronze keeps
    # strings; Silver is where the data becomes typed and analysable.
    result["rating"] = pd.to_numeric(result["rating"], errors="coerce").astype("Int8")
    result["created_at"] = pd.to_datetime(
        result["created_at"], errors="coerce", utc=True, format="mixed"
    )
    return result


def validate_batch(
    frame: pd.DataFrame,
    batch_id: str,
    *,
    settings: PipelineSettings | None = None,
    write_rejects: bool = True,
) -> ValidationResult:
    """Validate one batch of Bronze records.

    Raises:
        SchemaError: a required column is missing from the entire batch.
    """
    settings = settings or get_pipeline_settings()
    started = time.perf_counter()

    missing = missing_required_columns(frame)
    if missing:
        log.error("schema_invalid", batch_id=batch_id, missing_columns=missing)
        raise SchemaError(missing)

    failures = apply_rules(frame)
    rejected_rows = {f.row_index for f in failures if f.severity is RuleSeverity.ERROR}

    quarantine_path = None
    if write_rejects and failures:
        quarantine_path = write_quarantine(frame, failures, batch_id, settings.quarantine_path)

    valid = frame.loc[~frame.index.isin(rejected_rows)].copy()
    valid = enrich_valid_records(valid)

    dedup = mark_duplicates(valid) if not valid.empty else None
    if dedup is not None:
        valid = dedup.frame

    quality = calculate_quality(frame, failures)
    duration = time.perf_counter() - started

    log.info(
        "validation_complete",
        batch_id=batch_id,
        rows_in=len(frame),
        rows_valid=len(valid),
        rows_quarantined=len(rejected_rows),
        quality_score=quality.score,
        duration_seconds=round(duration, 3),
    )

    return ValidationResult(
        valid_records=valid,
        quality=quality,
        failures=failures,
        quarantine_path=quarantine_path,
        duration_seconds=duration,
        exact_duplicates=dedup.exact_duplicates if dedup else 0,
        content_duplicates=dedup.content_duplicates if dedup else 0,
    )
