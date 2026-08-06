"""The Silver layer: clean, typed, enriched, review-level records.

Silver is what every analytical question is actually asked of. Bronze is the
archive; Gold is pre-aggregated summaries. Silver is the one place holding one
row per review with everything known about it.

Partitioned by `review_date` — the date the customer wrote the review — not by
ingestion date. Almost every query is "what happened in the last 30 days",
which prunes to a handful of directories. Partitioning by ingestion date would
scatter one review-day across every batch that ever delivered it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipelines.common.domain import PROCESSING_VERSION
from pipelines.common.logging import get_logger

log = get_logger(__name__)

#: Columns Silver guarantees. The API and Gold aggregations may rely on these.
SILVER_COLUMNS: tuple[str, ...] = (
    # identity and dimensions
    "review_id",
    "brand",
    "product",
    "country",
    "source",
    "rating",
    "created_at",
    "review_date",
    # text, original and cleaned
    "text",
    "normalized_text",
    # language
    "language",
    "language_confidence",
    "language_detected_name",
    # sentiment
    "sentiment",
    "sentiment_score",
    "sentiment_model_version",
    # topics
    "primary_topic",
    "topics",
    "topic_match_reason",
    # derived text features
    "word_count",
    "character_count",
    "emoji_count",
    "exclamation_count",
    "uppercase_ratio",
    "has_url",
    "has_mention",
    # duplication
    "content_fingerprint",
    "is_duplicate_of",
    # lineage
    "ingestion_batch_id",
    "processing_version",
    "processed_at",
)


def write_silver(frame: pd.DataFrame, silver_root: Path) -> list[Path]:
    """Write enriched records to Silver, partitioned by review date.

    Existing partitions are **replaced** for the dates present in this frame,
    not appended to. Silver is a derived layer: re-running enrichment after
    fixing a bug should produce a corrected Silver, not two contradictory
    copies of the same review. Bronze remains the immutable record, so nothing
    is lost by rewriting here.
    """
    if frame.empty:
        log.info("silver_write_skipped", reason="empty frame")
        return []

    silver_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for review_date, group in frame.groupby("review_date", sort=True):
        partition = silver_root / f"review_date={review_date}"
        partition.mkdir(parents=True, exist_ok=True)

        target = partition / "part-0000.parquet"
        group.drop(columns=["review_date"]).to_parquet(
            target, engine="pyarrow", compression="snappy", index=False
        )
        written.append(target)

    log.info(
        "silver_written",
        rows=len(frame),
        partitions=len(written),
        columns=len(frame.columns),
        bytes=sum(path.stat().st_size for path in written),
    )
    return written


def read_silver(
    silver_root: Path, *, date_from: str | None = None, date_to: str | None = None
) -> pd.DataFrame:
    """Read Silver, optionally restricted to a date range.

    The date filter is applied to **directory names before opening any file**,
    which is the whole reason for partitioning: a 30-day query on two years of
    data reads 30 directories, not 730.
    """
    if not silver_root.exists():
        return pd.DataFrame()

    partitions = sorted(silver_root.glob("review_date=*"))
    selected: list[Path] = []
    for partition in partitions:
        review_date = partition.name.removeprefix("review_date=")
        if date_from and review_date < date_from:
            continue
        if date_to and review_date > date_to:
            continue
        selected.extend(sorted(partition.glob("*.parquet")))

    if not selected:
        log.info("silver_empty", root=str(silver_root), date_from=date_from, date_to=date_to)
        return pd.DataFrame()

    frames = []
    for path in selected:
        part = pd.read_parquet(path)
        # Restore the partition column, which Hive-style layout keeps in the
        # path rather than the file.
        part["review_date"] = path.parent.name.removeprefix("review_date=")
        frames.append(part)

    frame = pd.concat(frames, ignore_index=True)
    log.info("silver_read", partitions=len(selected), rows=len(frame))
    return frame


def finalise_silver_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add lineage columns and order the frame to the Silver contract.

    Columns not in `SILVER_COLUMNS` are dropped rather than carried along.
    Passing extra columns through silently is how a derived layer slowly turns
    back into a copy of the raw one.
    """
    result = frame.copy()
    result["processing_version"] = PROCESSING_VERSION
    result["processed_at"] = pd.Timestamp.now(tz="UTC").isoformat()

    for column in SILVER_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    return result[list(SILVER_COLUMNS)]
