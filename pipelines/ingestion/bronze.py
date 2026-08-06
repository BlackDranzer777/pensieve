"""Writing the Bronze layer.

Bronze is the immutable record of what arrived. Three rules govern it:

1. **Nothing is modified.** Values land exactly as they were read, as strings.
2. **Nothing is rejected.** Invalid rows belong in Bronze too; they are
   quarantined later, in a stage that can explain *why*.
3. **Nothing is overwritten.** Each batch owns its own directory. Re-ingesting
   an identical file is a no-op, never a silent replacement.

Layout:

    data/bronze/ingestion_date=YYYY-MM-DD/batch_id=<ulid>/
        part-0000.parquet
        _batch_manifest.json
        source/<original filename>
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from pipelines.common.logging import get_logger
from pipelines.ingestion.batch import MANIFEST_FILENAME, BatchMetadata

log = get_logger(__name__)

# Ingestion metadata attached to every Bronze row. Prefixed to keep them
# clearly distinct from columns that came from the source file.
INGESTION_COLUMNS: tuple[str, ...] = (
    "ingestion_batch_id",
    "ingestion_timestamp",
    "source_file",
    "source_format",
    "source_row_number",
)


def batch_partition_path(bronze_root: Path, batch: BatchMetadata) -> Path:
    """Return the directory this batch owns."""
    return (
        bronze_root
        / f"ingestion_date={batch.ingestion_date.isoformat()}"
        / f"batch_id={batch.batch_id}"
    )


def add_ingestion_metadata(frame: pd.DataFrame, batch: BatchMetadata) -> pd.DataFrame:
    """Attach provenance columns without touching the source columns.

    `source_row_number` is 1-based and reflects the row's position in the
    original file, so a quarantined record can be traced back to a line the
    person who sent the file will recognise.
    """
    enriched = frame.copy()
    enriched["ingestion_batch_id"] = batch.batch_id
    enriched["ingestion_timestamp"] = batch.ingested_at.isoformat()
    enriched["source_file"] = batch.source_file
    enriched["source_format"] = batch.source_format
    enriched["source_row_number"] = range(1, len(enriched) + 1)
    return enriched


def write_bronze(
    frame: pd.DataFrame,
    batch: BatchMetadata,
    bronze_root: Path,
    *,
    source_path: Path | None = None,
) -> Path:
    """Write one batch to Bronze and return its partition directory.

    Args:
        frame: Raw records, all columns as strings.
        batch: Provenance for this batch.
        bronze_root: Root of the Bronze layer.
        source_path: If given, the original file is copied in alongside the
            Parquet. Keeping the source means a parsing bug found months later
            can be re-run against exactly the bytes that arrived, rather than
            against our interpretation of them.

    Raises:
        FileExistsError: the batch directory already exists. Callers should use
            `find_batch_by_checksum` first; reaching this means a genuine
            batch-id collision, which must never be silently overwritten.
    """
    partition = batch_partition_path(bronze_root, batch)
    if partition.exists():
        raise FileExistsError(
            f"Bronze partition already exists for batch {batch.batch_id}: {partition}. "
            "Bronze is append-only; refusing to overwrite."
        )

    partition.mkdir(parents=True, exist_ok=False)

    enriched = add_ingestion_metadata(frame, batch)
    parquet_path = partition / "part-0000.parquet"
    enriched.to_parquet(parquet_path, engine="pyarrow", compression="snappy", index=False)

    (partition / MANIFEST_FILENAME).write_text(batch.to_json(), encoding="utf-8")

    if source_path is not None and source_path.exists():
        source_dir = partition / "source"
        source_dir.mkdir(exist_ok=True)
        shutil.copy2(source_path, source_dir / source_path.name)

    log.info(
        "bronze_written",
        batch_id=batch.batch_id,
        rows=len(enriched),
        columns=len(enriched.columns),
        path=str(partition),
        bytes=parquet_path.stat().st_size,
    )
    return partition


def read_bronze_batch(bronze_root: Path, batch_id: str) -> pd.DataFrame:
    """Read a single Bronze batch back by id."""
    matches = list(bronze_root.glob(f"*/batch_id={batch_id}/*.parquet"))
    if not matches:
        raise FileNotFoundError(f"No Bronze partition found for batch {batch_id!r}.")
    return pd.concat((pd.read_parquet(path) for path in sorted(matches)), ignore_index=True)


def read_bronze(bronze_root: Path, *, ingestion_date: str | None = None) -> pd.DataFrame:
    """Read the whole Bronze layer, or one ingestion date's worth of it.

    Returns an empty DataFrame when nothing has been ingested — an empty layer
    is a legitimate state, not an error.
    """
    pattern = (
        f"ingestion_date={ingestion_date}/*/*.parquet"
        if ingestion_date
        else "ingestion_date=*/*/*.parquet"
    )
    paths = sorted(bronze_root.glob(pattern))
    if not paths:
        log.info("bronze_empty", root=str(bronze_root), ingestion_date=ingestion_date)
        return pd.DataFrame()

    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    log.info("bronze_read", partitions=len(paths), rows=len(frame))
    return frame
