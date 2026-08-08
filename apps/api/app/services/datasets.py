"""Dataset upload and pipeline triggering.

The only two write endpoints in the API. Both are deliberately narrow: upload
stores a file and says what it saw, and the trigger starts a pipeline and
returns immediately. Neither pretends to have done the other's job.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.errors import UnsupportedFormatError, ValidationFailedError
from app.schemas.telemetry import DatasetUploadResult, PipelineRunAccepted
from pipelines.common.domain import SUPPORTED_INPUT_FORMATS
from pipelines.common.logging import get_logger

if TYPE_CHECKING:
    from pipelines.common.config import PipelineSettings

log = get_logger(__name__)

#: 200 MB. Large enough for a real export, small enough that a stray upload
#: cannot fill the disk before anything notices.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

#: Everything outside this set is stripped from an uploaded filename.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(raw: str) -> str:
    """Reduce a client-supplied filename to something safe to write.

    An uploaded name is attacker-controlled. `../../.env` or an absolute path
    would otherwise let a request write anywhere the API process can reach, so
    only the final path component is kept and everything unusual is replaced.
    """
    stem = Path(raw).name
    cleaned = _SAFE_NAME.sub("_", stem).lstrip(".")
    if not cleaned:
        raise ValidationFailedError("The uploaded file has no usable filename.")
    return cleaned[:150]


class DatasetService:
    def __init__(self, settings: PipelineSettings) -> None:
        self._settings = settings

    def store_upload(self, filename: str, content: bytes) -> DatasetUploadResult:
        """Validate and save an uploaded dataset.

        Does **not** ingest it. Ingestion is a separate call, because a file
        that stored successfully and a file that survived validation are
        different facts, and reporting them together would mean claiming the
        second before it is known.
        """
        name = safe_filename(filename)
        suffix = Path(name).suffix.lower()

        if suffix not in SUPPORTED_INPUT_FORMATS:
            raise UnsupportedFormatError(
                f"'{suffix or name}' is not a supported format.",
                details={"supported": sorted(SUPPORTED_INPUT_FORMATS)},
            )
        if not content:
            raise ValidationFailedError("The uploaded file is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationFailedError(
                "The uploaded file is too large.",
                details={
                    "size_bytes": len(content),
                    "max_bytes": MAX_UPLOAD_BYTES,
                },
            )

        destination = self._settings.samples_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        log.info("dataset_uploaded", filename=name, size_bytes=len(content))
        return DatasetUploadResult(
            filename=name,
            stored_path=str(destination),
            size_bytes=len(content),
            detected_rows=_count_rows(content, suffix),
            message=(
                "File stored. It has not been ingested yet — "
                "POST /api/v1/pipelines/run to process it."
            ),
        )

    def trigger_pipeline(self) -> PipelineRunAccepted:
        """Start a pipeline run in a detached process.

        A full run takes minutes, so it cannot happen inside a request. The
        process is detached rather than awaited, and progress is reported the
        same way it is for a run started from the terminal — through
        `pipeline_runs`, which the pipeline writes itself. No second source of
        truth for run status.
        """
        command = [sys.executable, "-m", "pipelines.jobs.run_pipeline"]
        try:
            subprocess.Popen(  # noqa: S603 - fixed command, no user input
                command,
                cwd=self._settings.repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise ValidationFailedError(f"Could not start the pipeline: {exc}") from exc

        log.info("pipeline_triggered", command=" ".join(command))
        return PipelineRunAccepted(
            started=True,
            message=(
                "Pipeline started. It runs in the background; poll the runs endpoint for status."
            ),
            poll_url="/api/v1/pipeline-runs",
        )


def _count_rows(content: bytes, suffix: str) -> int | None:
    """Best-effort row estimate, purely informational.

    Returns None rather than guessing for formats where a line is not a row.
    A wrong count shown confidently is worse than no count.
    """
    if suffix == ".csv":
        lines = content.count(b"\n")
        return max(0, lines - 1)  # minus the header
    if suffix == ".jsonl":
        return content.count(b"\n")
    return None
