"""Batch identity, checksums and idempotency.

Every ingestion produces a *batch*: a unit of raw data that entered the
platform together, identified by a sortable ULID and fingerprinted by the
SHA-256 checksum of its source file.

The checksum is what makes ingestion idempotent. Re-running the pipeline on a
file that has already been ingested returns the existing batch instead of
writing a second copy of the same rows into Bronze — which is exactly the
behaviour you want when a job is retried after a downstream failure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ulid import ULID

from pipelines.common.domain import SUPPORTED_INPUT_FORMATS
from pipelines.common.logging import get_logger

log = get_logger(__name__)

# Read the file in chunks so a multi-gigabyte input never has to fit in memory.
_CHECKSUM_CHUNK_BYTES = 1024 * 1024

MANIFEST_FILENAME = "_batch_manifest.json"


class UnsupportedFormatError(ValueError):
    """Raised when a source file's extension is not one we can read."""

    def __init__(self, suffix: str) -> None:
        supported = ", ".join(sorted(SUPPORTED_INPUT_FORMATS))
        super().__init__(f"Unsupported file format {suffix!r}. Supported formats: {supported}.")
        self.suffix = suffix


@dataclass(frozen=True, slots=True)
class BatchMetadata:
    """Provenance for one ingested batch.

    Written alongside the Bronze partition as `_batch_manifest.json` so a batch
    remains self-describing even if the database is lost.
    """

    batch_id: str
    source_file: str
    source_format: str
    file_checksum: str
    file_size_bytes: int
    row_count: int
    ingested_at: datetime
    ingestion_date: date
    generator_seed: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["ingested_at"] = self.ingested_at.isoformat()
        payload["ingestion_date"] = self.ingestion_date.isoformat()
        return json.dumps(payload, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> BatchMetadata:
        payload = json.loads(raw)
        payload["ingested_at"] = datetime.fromisoformat(payload["ingested_at"])
        payload["ingestion_date"] = date.fromisoformat(payload["ingestion_date"])
        return cls(**payload)


def new_batch_id() -> str:
    """Return a fresh ULID.

    ULIDs are preferred over UUID4 here because they sort lexicographically by
    creation time. Since batch ids are used as directory names, `ls` on the
    Bronze layer comes back in chronological order for free.
    """
    return str(ULID())


def compute_checksum(path: Path) -> str:
    """SHA-256 of a file's contents, streamed in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHECKSUM_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_format(path: Path) -> str:
    """Return the normalised extension, or raise `UnsupportedFormatError`."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_INPUT_FORMATS:
        raise UnsupportedFormatError(suffix)
    return suffix.lstrip(".")


def build_batch_metadata(
    source_path: Path,
    row_count: int,
    *,
    batch_id: str | None = None,
    generator_seed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> BatchMetadata:
    """Describe a batch about to be written to Bronze."""
    now = datetime.now(UTC)
    return BatchMetadata(
        batch_id=batch_id or new_batch_id(),
        source_file=source_path.name,
        source_format=validate_source_format(source_path),
        file_checksum=compute_checksum(source_path),
        file_size_bytes=source_path.stat().st_size,
        row_count=row_count,
        ingested_at=now,
        ingestion_date=now.date(),
        generator_seed=generator_seed,
        extra=extra or {},
    )


def iter_existing_manifests(bronze_root: Path) -> list[BatchMetadata]:
    """Read every batch manifest already present in the Bronze layer.

    A corrupt or unreadable manifest is logged and skipped rather than aborting
    the scan: one damaged batch should not make the platform refuse to ingest
    anything new.
    """
    if not bronze_root.exists():
        return []

    manifests: list[BatchMetadata] = []
    for manifest_path in sorted(bronze_root.rglob(MANIFEST_FILENAME)):
        try:
            manifests.append(BatchMetadata.from_json(manifest_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            log.warning(
                "batch_manifest_unreadable",
                path=str(manifest_path),
                error=str(exc),
                error_type=type(exc).__name__,
            )
    return manifests


def find_batch_by_checksum(bronze_root: Path, checksum: str) -> BatchMetadata | None:
    """Return an already-ingested batch with this checksum, if one exists.

    This is the idempotency check from the ingestion design: identical file
    contents mean the same batch, regardless of filename or ingestion time.
    """
    for manifest in iter_existing_manifests(bronze_root):
        if manifest.file_checksum == checksum:
            return manifest
    return None
