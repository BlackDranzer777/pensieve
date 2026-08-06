"""Quarantine storage for records that failed validation.

Rejected records are never dropped. Each is written to Parquet carrying its
original values plus everything needed to understand and fix the rejection:

    original values (every source column, unchanged)
    batch_id
    rule_id            which rule rejected it
    failed_field       which column was at fault
    failed_value       the offending value, truncated
    failure_reason     human-readable explanation
    severity
    source_row_number  the row in the file the sender will recognise
    quarantined_at

A record breaking several rules produces several quarantine rows — one per
failure — so the reasons breakdown on the dashboard adds up honestly.

Layout: `data/quarantine/batch_id=<ulid>/part-0000.parquet`
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from pipelines.common.logging import get_logger
from pipelines.validation.rules import ValidationFailure

log = get_logger(__name__)

QUARANTINE_COLUMNS: tuple[str, ...] = (
    "batch_id",
    "rule_id",
    "failed_field",
    "failed_value",
    "failure_reason",
    "severity",
    "quarantined_at",
)


def build_quarantine_frame(
    frame: pd.DataFrame,
    failures: list[ValidationFailure],
    batch_id: str,
) -> pd.DataFrame:
    """Join failures back to their source rows.

    Returns an empty frame when nothing failed — a clean batch is a legitimate
    outcome, not an edge case to special-case elsewhere.
    """
    if not failures:
        return pd.DataFrame()

    quarantined_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, object]] = []

    for failure in failures:
        # `.to_dict()` on the original row preserves every source column
        # exactly as ingested, which is what makes the record fixable.
        # Keys are coerced to `str` because pandas types them as `Hashable`.
        original: dict[str, object] = {
            str(column): value for column, value in frame.loc[failure.row_index].to_dict().items()
        }
        rows.append(
            {
                **original,
                "batch_id": batch_id,
                "rule_id": failure.rule_id,
                "failed_field": failure.field,
                "failed_value": failure.failed_value,
                "failure_reason": failure.reason,
                "severity": failure.severity.value,
                "quarantined_at": quarantined_at,
            }
        )

    return pd.DataFrame(rows).astype("string")


def write_quarantine(
    frame: pd.DataFrame,
    failures: list[ValidationFailure],
    batch_id: str,
    quarantine_root: Path,
) -> Path | None:
    """Write quarantined records for one batch.

    Returns the partition path, or None when there was nothing to quarantine.
    """
    quarantine_frame = build_quarantine_frame(frame, failures, batch_id)
    if quarantine_frame.empty:
        log.info("quarantine_empty", batch_id=batch_id)
        return None

    partition = quarantine_root / f"batch_id={batch_id}"
    partition.mkdir(parents=True, exist_ok=True)
    target = partition / "part-0000.parquet"
    quarantine_frame.to_parquet(target, engine="pyarrow", compression="snappy", index=False)

    by_rule = quarantine_frame["rule_id"].value_counts().to_dict()
    log.info(
        "quarantine_written",
        batch_id=batch_id,
        records=len(quarantine_frame),
        distinct_rows=len({f.row_index for f in failures}),
        by_rule=by_rule,
        path=str(partition),
    )
    return partition


def read_quarantine(quarantine_root: Path, *, batch_id: str | None = None) -> pd.DataFrame:
    """Read quarantined records, optionally for a single batch."""
    pattern = f"batch_id={batch_id}/*.parquet" if batch_id else "batch_id=*/*.parquet"
    paths = sorted(quarantine_root.glob(pattern))
    if not paths:
        return pd.DataFrame()
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
