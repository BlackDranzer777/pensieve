"""Load Silver and Gold Parquet into PostgreSQL.

**Parquet is the source of truth; Postgres is a derived serving copy.** That
one sentence explains every decision in this module:

- The load is a **full replace**, not an incremental merge. Truncate, insert,
  commit. Reconciling a partial merge against an immutable source is work with
  no upside when a clean rebuild takes seconds.
- It runs in **one transaction**. A failure halfway leaves yesterday's data
  serving traffic rather than an empty dashboard.
- Ids derived from source keys are **deterministic** (`uuid5`), so reloading
  produces the same primary keys rather than a new set that breaks every
  bookmarked link.

Why this module imports `app.models`: the loader and the API must agree on the
schema exactly. Two definitions would drift, and the failure mode is a column
the loader fills that the API never reads — invisible until someone asks why a
chart is empty.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import duckdb
import numpy as np
import pandas as pd
from sqlalchemy import DateTime, Integer, create_engine, delete, func, insert, select

from app.models import (
    Anomaly,
    Brand,
    CountryMetric,
    DailyBrandMetric,
    DailyTopicMetric,
    DataQualityResult,
    LanguageDistribution,
    PipelineRun,
    PipelineStageRun,
    Review,
    ReviewDateBounds,
    ReviewTopic,
    SentimentTrend,
)
from pipelines.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from sqlalchemy.orm import Session

    from pipelines.common.config import PipelineSettings

log = get_logger(__name__)

#: Namespace for deterministic ids. Fixed forever — changing it would give
#: every row a new primary key on the next load.
PENSIEVE_NAMESPACE = uuid.UUID("6f1c9d18-2a45-4e77-9b3a-8c5e1f0d7a21")

#: Rows per executemany batch. Large enough that round trips stop dominating,
#: small enough that a failing batch is still readable in a log line.
CHUNK_SIZE = 5_000

#: Tables emptied on every load, in an order that respects foreign keys.
#: Children first: `reviews` references `brands`, so brands cannot go first.
TRUNCATION_ORDER = (
    ReviewTopic,
    Review,
    DataQualityResult,
    PipelineStageRun,
    PipelineRun,
    DailyBrandMetric,
    DailyTopicMetric,
    CountryMetric,
    LanguageDistribution,
    SentimentTrend,
    Anomaly,
    ReviewDateBounds,
    Brand,
)


def stable_id(*parts: object) -> uuid.UUID:
    """A uuid derived from source keys, identical across reloads."""
    return uuid.uuid5(PENSIEVE_NAMESPACE, "|".join(str(part) for part in parts))


@dataclass(slots=True)
class LoadResult:
    """What a load actually did. Printed by the CLI and asserted in tests."""

    rows_by_table: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0

    @property
    def total_rows(self) -> int:
        return sum(self.rows_by_table.values())


class LoaderError(RuntimeError):
    """Raised when the load cannot proceed at all."""


# ---------------------------------------------------------------------------
# Parquet reading
# ---------------------------------------------------------------------------


def _read_parquet(root: Path, *, required: bool = True) -> pd.DataFrame:
    """Read a Parquet directory into a DataFrame.

    DuckDB rather than pandas because it globs partitioned directories natively
    and reads only the columns asked for. An empty result is a legitimate state
    for an optional dataset, so it returns an empty frame rather than raising.
    """
    if not root.exists() or not any(root.rglob("*.parquet")):
        if required:
            raise LoaderError(
                f"No Parquet found under {root}. Run the pipeline first:\n"
                "  python -m pipelines.jobs.run_pipeline\n"
                "  python -m pipelines.jobs.run_gold"
            )
        log.warning("loader_dataset_missing", path=str(root))
        return pd.DataFrame()

    query = (
        f"SELECT * FROM read_parquet('{root.as_posix()}/**/*.parquet', hive_partitioning = true)"  # noqa: S608
    )
    return duckdb.sql(query).to_df()


def _py(value: object) -> Any:
    """Convert pandas and numpy scalars to Python natives.

    Two conversions, both learned the hard way:

    `numpy.int64` and friends come out of `DataFrame.to_dict()`. SQLAlchemy
    coerces them; psycopg's COPY path does not, and fails with "cannot adapt
    type numpy.int64" partway through a load.

    `pandas.Timestamp` subclasses `datetime`, so psycopg accepts it — but
    SQLAlchemy's SQLite dialect type-checks strictly and rejects it. Converting
    here means the loader works against any driver rather than only the one it
    was developed on.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _records(frame: pd.DataFrame, columns: dict[str, str]) -> list[dict[str, Any]]:
    """Rename Parquet columns to model columns and normalise missing values.

    pandas represents a missing number as `NaN`, which psycopg would happily
    write as the float NaN rather than SQL NULL. A NaN average rating silently
    poisons every downstream average, so the conversion happens here, once.
    """
    if frame.empty:
        return []

    missing = [source for source in columns if source not in frame.columns]
    if missing:
        raise LoaderError(f"Parquet is missing expected columns: {missing}")

    subset = frame[list(columns)].rename(columns=columns)
    return [
        {str(key): _clean(value) for key, value in row.items()}
        for row in subset.to_dict(orient="records")
    ]


def _insert_chunked(session: Session, model: type[Any], rows: Sequence[dict[str, Any]]) -> int:
    """Bulk-insert rows via PostgreSQL COPY, returning how many were written.

    **Why COPY rather than `executemany`.** The ORM path measured **424s** for
    90,300 rows on this dataset — around 210 rows/sec, because every row costs
    a parse and a round trip. COPY streams them over one statement.

    Columns absent from the row dicts keep their database defaults, which is
    how `loaded_at` gets filled without the loader having to know about it.

    Falls back to `executemany` on any non-PostgreSQL driver so the loader
    still runs against SQLite in tests.
    """
    if not rows:
        return 0

    columns = list(rows[0])
    kinds = _column_kinds(model)
    typed = [_coerce_row(kinds, row) for row in rows]
    connection = session.connection()

    if connection.dialect.name != "postgresql":
        for start in range(0, len(typed), CHUNK_SIZE):
            session.execute(insert(model), typed[start : start + CHUNK_SIZE])
        return len(typed)

    quoted = ", ".join(f'"{column}"' for column in columns)
    statement = f'COPY "{model.__tablename__}" ({quoted}) FROM STDIN'

    # The raw psycopg connection. Taking it from the live SQLAlchemy connection
    # rather than opening a new one is what keeps COPY inside the loader's
    # single transaction — a separate connection would commit independently and
    # defeat the all-or-nothing guarantee.
    raw = connection.connection.driver_connection
    with raw.cursor() as cursor, cursor.copy(statement) as copy:  # type: ignore[union-attr]
        for row in typed:
            copy.write_row([row[column] for column in columns])

    return len(typed)


def _column_kinds(model: type[Any]) -> tuple[frozenset[str], frozenset[str]]:
    """`(integer columns, datetime columns)` for a model.

    Derived from the model rather than listed by hand, so a column added later
    is handled automatically instead of failing on its first load. Computed
    once per batch by the caller — per row it would cost an isinstance sweep
    of every column, 90,000 times over.
    """
    integers = frozenset(
        column.name for column in model.__table__.columns if isinstance(column.type, Integer)
    )
    datetimes = frozenset(
        column.name for column in model.__table__.columns if isinstance(column.type, DateTime)
    )
    return integers, datetimes


def _coerce_row(
    kinds: tuple[frozenset[str], frozenset[str]], row: dict[str, Any]
) -> dict[str, Any]:
    """Fit a row's values to the column types the model declares.

    Two mismatches the Parquet layers reliably produce:

    **Integers arriving as floats.** pandas widens any integer column
    containing a null to float64, so a count of 14 arrives as `14.0`.
    SQLAlchemy narrows it back; COPY does not, and Postgres rejects "14.0"
    for an integer column.

    **Timestamps arriving as ISO strings.** Silver stores `processed_at` as
    text, and the stage timings inside `stages_json` are strings by
    construction. psycopg parses them; SQLAlchemy's SQLite dialect does not.
    """
    integers, datetimes = kinds
    coerced: dict[str, Any] = {}

    for column, value in row.items():
        if value is None:
            coerced[column] = None
        elif column in integers:
            coerced[column] = int(value)
        elif column in datetimes and isinstance(value, str):
            coerced[column] = datetime.fromisoformat(value)
        else:
            coerced[column] = value

    return coerced


# ---------------------------------------------------------------------------
# The loader
# ---------------------------------------------------------------------------


class PostgresLoader:
    """Loads every Parquet layer into PostgreSQL in one transaction."""

    def __init__(self, settings: PipelineSettings, database_url: str) -> None:
        self._settings = settings
        self._database_url = database_url
        self._brand_ids: dict[str, uuid.UUID] = {}

    # -- brands ------------------------------------------------------------

    def _load_brands(self, session: Session, silver: pd.DataFrame) -> int:
        """Create one brand row per distinct name in Silver.

        Brands arrive as free text, so the name is the natural key. Ids are
        derived from it, which means the same brand keeps the same id across
        reloads and any bookmarked `/brands/<id>` link keeps working.
        """
        names = sorted({str(name) for name in silver["brand"].dropna().unique()})
        if not names:
            raise LoaderError("Silver contains no brands; refusing to load an empty dataset.")

        self._brand_ids = {name: stable_id("brand", name) for name in names}
        rows = [{"id": self._brand_ids[name], "name": name} for name in names]
        return _insert_chunked(session, Brand, rows)

    def _brand_id_for(self, name: object) -> uuid.UUID | None:
        return self._brand_ids.get(str(name))

    # -- reviews -----------------------------------------------------------

    def _load_reviews(
        self, session: Session, silver: pd.DataFrame, run_id: uuid.UUID | None
    ) -> int:
        """Load every Silver row, duplicates included.

        Duplicates are loaded deliberately. They genuinely arrived and belong
        in the Review Explorer; `is_duplicate_of` is what keeps them out of the
        aggregates, exactly as it does in the Gold SQL.
        """
        rows = _records(
            silver,
            {
                "review_id": "external_review_id",
                "product": "product",
                "source": "source",
                "country": "country",
                "rating": "rating",
                "text": "original_text",
                "normalized_text": "normalized_text",
                "created_at": "review_created_at",
                "language": "language",
                "language_confidence": "language_confidence",
                "sentiment": "sentiment",
                "sentiment_score": "sentiment_score",
                "sentiment_model_version": "sentiment_model_version",
                "word_count": "word_count",
                "is_duplicate_of": "is_duplicate_of",
                "processed_at": "processed_at",
            },
        )

        brands = silver["brand"].tolist()
        prepared: list[dict[str, Any]] = []
        skipped_unknown_brand = 0

        for row, brand_name in zip(rows, brands, strict=True):
            brand_id = self._brand_id_for(brand_name)
            if brand_id is None:  # pragma: no cover - brands come from this frame
                skipped_unknown_brand += 1
                continue
            row["id"] = stable_id("review", row["external_review_id"], brand_name)
            row["brand_id"] = brand_id
            row["pipeline_run_id"] = run_id
            # Ratings arrive as float64 because pandas widens integer columns
            # that contain any nulls; Postgres wants a real integer.
            if row["rating"] is not None:
                row["rating"] = int(row["rating"])
            if row["word_count"] is not None:
                row["word_count"] = int(row["word_count"])
            prepared.append(row)

        if skipped_unknown_brand:  # pragma: no cover - defensive
            log.warning("loader_reviews_unknown_brand", rows=skipped_unknown_brand)

        # A duplicate external id across two brands is legal, but the same id
        # twice for one brand would violate the derived primary key. Silver's
        # own duplicate marking does not prevent it, so drop the collisions
        # here and say how many rather than letting the insert fail opaquely.
        seen: set[uuid.UUID] = set()
        deduped: list[dict[str, Any]] = []
        for row in prepared:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            deduped.append(row)

        collisions = len(prepared) - len(deduped)
        if collisions:
            log.warning("loader_reviews_id_collisions", rows=collisions)

        return _insert_chunked(session, Review, deduped)

    def _load_review_topics(self, session: Session, silver: pd.DataFrame) -> int:
        """Expand each review's topics into rows, keeping the matched keywords.

        Silver stores topics as a list and the primary one separately. One row
        per topic is what makes "how many reviews mention delivery at all"
        answerable, rather than only "how many are *mainly* about delivery".
        """
        rows: list[dict[str, Any]] = []
        seen: set[uuid.UUID] = set()

        columns = ("review_id", "brand", "primary_topic", "topics", "topic_match_reason")
        for external_id, brand, primary, topics, reason in zip(
            *(silver[column] for column in columns), strict=True
        ):
            review_id = stable_id("review", external_id, brand)
            if review_id in seen:
                continue
            seen.add(review_id)

            for topic in _as_topic_list(topics, primary):
                rows.append(
                    {
                        "id": stable_id("review_topic", external_id, brand, topic),
                        "review_id": review_id,
                        "topic": topic,
                        "is_primary": topic == primary,
                        "matched_keywords": str(reason) if reason is not None else None,
                    }
                )

        return _insert_chunked(session, ReviewTopic, rows)

    # -- telemetry ---------------------------------------------------------

    def _load_pipeline_runs(
        self, session: Session, runs: pd.DataFrame, quality: pd.DataFrame
    ) -> tuple[int, int]:
        """Load run rows and expand `stages_json` into stage rows.

        The duplicate count lives in the quality dataset rather than the run
        dataset, so it is joined in here. Leaving it at zero would understate
        every "how much of this batch was usable" figure on the dashboard.
        """
        if runs.empty:
            return 0, 0

        duplicates_by_run = _duplicates_by_run(quality)
        run_rows: list[dict[str, Any]] = []
        stage_rows: list[dict[str, Any]] = []

        for record in runs.to_dict(orient="records"):
            run_key = str(record["run_id"])
            run_uuid = stable_id("pipeline_run", run_key)
            quarantined = _int(record.get("rows_quarantined"))
            run_rows.append(
                {
                    "id": run_uuid,
                    "batch_id": _clean(record.get("batch_id")),
                    "status": str(record.get("status") or "unknown"),
                    "started_at": record["started_at"],
                    "completed_at": _clean(record.get("completed_at")),
                    "duration_seconds": _clean(record.get("duration_seconds")),
                    "input_rows": _int(record.get("rows_in")),
                    "output_rows": _int(record.get("rows_out")),
                    "quarantined_rows": quarantined,
                    # Identical to `quarantined_rows` in this pipeline: the only
                    # way a row fails to reach Silver is by being quarantined.
                    # Kept as its own column because the ERD specifies it, and
                    # because a future stage could fail rows without
                    # quarantining them — at which point the two diverge.
                    "failed_rows": quarantined,
                    "duplicate_rows": duplicates_by_run.get(run_key, 0),
                    "rows_per_second": _clean(record.get("rows_per_second")),
                    "quality_score": _clean(record.get("quality_score")),
                }
            )
            stage_rows.extend(_stage_rows(run_uuid, record.get("stages_json")))

        written_runs = _insert_chunked(session, PipelineRun, run_rows)
        written_stages = _insert_chunked(session, PipelineStageRun, stage_rows)
        return written_runs, written_stages

    def _load_quality_results(self, session: Session, quality: pd.DataFrame) -> int:
        """One row per validation rule per run."""
        if quality.empty:
            return 0

        rows: list[dict[str, Any]] = []
        for record in quality.to_dict(orient="records"):
            rule_id = str(record["rule_id"])
            failures = _int(record.get("rule_failure_count"))
            rows.append(
                {
                    "id": stable_id("quality", record["run_id"], rule_id),
                    "pipeline_run_id": stable_id("pipeline_run", record["run_id"]),
                    "batch_id": _clean(record.get("batch_id")),
                    "rule_id": rule_id,
                    "check_name": rule_id.replace("_", " "),
                    # A rule that rejected nothing passed. Recording it at all
                    # is the point: "no rows failed" and "the rule never ran"
                    # look identical if only failures are stored.
                    "status": "failed" if failures else "passed",
                    "affected_rows": failures,
                    "score": _clean(record.get("quality_score")),
                    "recorded_at": _clean(record.get("recorded_at")),
                }
            )
        return _insert_chunked(session, DataQualityResult, rows)

    # -- aggregates --------------------------------------------------------

    def _load_brand_keyed(
        self,
        session: Session,
        frame: pd.DataFrame,
        model: type[Any],
        columns: dict[str, str],
        key_prefix: str,
        extra_key: str | None = None,
    ) -> int:
        """Load a Gold dataset whose grain includes `brand`.

        Gold stores the brand name; Postgres stores a foreign key. Resolving it
        here, against the map built when brands were loaded, is what keeps the
        aggregate tables joinable to `reviews`.
        """
        rows = _records(frame, columns)
        if not rows:
            return 0

        prepared: list[dict[str, Any]] = []
        for row, brand_name in zip(rows, frame["brand"], strict=True):
            brand_id = self._brand_id_for(brand_name)
            if brand_id is None:  # pragma: no cover - defensive
                continue
            key_parts = [key_prefix, brand_name, row["metric_date"]]
            if extra_key is not None:
                key_parts.append(row[extra_key])
            row["id"] = stable_id(*key_parts)
            row["brand_id"] = brand_id
            prepared.append(row)

        return _insert_chunked(session, model, prepared)

    def _load_date_keyed(
        self,
        session: Session,
        frame: pd.DataFrame,
        model: type[Any],
        columns: dict[str, str],
        key_prefix: str,
        key_column: str,
    ) -> int:
        """Load a Gold dataset keyed by date plus one dimension."""
        rows = _records(frame, columns)
        for row in rows:
            row["id"] = stable_id(key_prefix, row["metric_date"], row[key_column])
        return _insert_chunked(session, model, rows)

    def _load_anomalies(self, session: Session, frame: pd.DataFrame) -> int:
        rows = _records(
            frame,
            {
                "anomaly_id": "anomaly_key",
                "detected_date": "detected_date",
                "metric": "metric",
                "topic": "topic",
                "country": "country",
                "current_value": "current_value",
                "baseline_value": "baseline_value",
                "percentage_change": "percentage_change",
                "z_score": "z_score",
                "review_count": "review_count",
                "severity": "severity",
                "explanation": "explanation",
                "generated_at": "detected_at",
            },
        )
        if not rows:
            return 0

        for row, brand_name in zip(rows, frame["brand"], strict=True):
            row["id"] = stable_id("anomaly", row["anomaly_key"])
            row["brand_id"] = self._brand_id_for(brand_name)
            if row["review_count"] is not None:
                row["review_count"] = int(row["review_count"])

        return _insert_chunked(session, Anomaly, rows)

    def _refresh_date_bounds(self, session: Session, silver: pd.DataFrame) -> int:
        """Cache the dataset's date range so the Overview need not scan for it."""
        dates = pd.to_datetime(silver["created_at"], utc=True, errors="coerce").dropna()
        if dates.empty:  # pragma: no cover - Silver always has dates
            return 0

        session.execute(
            insert(ReviewDateBounds).values(
                id=1,
                earliest=dates.min().date(),
                latest=dates.max().date(),
                review_count=len(silver),
                refreshed_at=pd.Timestamp.now(tz="UTC").to_pydatetime(),
            )
        )
        return 1

    # -- orchestration -----------------------------------------------------

    def load_all(self) -> LoadResult:
        """Read every layer and replace the contents of PostgreSQL."""
        started = time.perf_counter()
        settings = self._settings

        silver = _read_parquet(settings.silver_path)
        gold = settings.gold_path
        datasets = {
            name: _read_parquet(gold / name, required=False)
            for name in (
                "daily_brand_metrics",
                "daily_topic_metrics",
                "country_metrics",
                "language_distribution",
                "sentiment_trends",
                "anomalies",
                "pipeline_run_metrics",
                "data_quality_metrics",
            )
        }

        log.info("loader_started", silver_rows=len(silver))

        engine = create_engine(self._database_url, pool_pre_ping=True)
        from sqlalchemy.orm import sessionmaker

        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        counts: dict[str, int] = {}

        # One transaction for the whole load. A failure at the last table
        # rolls back to the previous good dataset rather than leaving the
        # dashboard half-populated with no indication which half.
        with factory() as session, session.begin():
            for model in TRUNCATION_ORDER:
                session.execute(delete(model))

            counts["brands"] = self._load_brands(session, silver)

            # Runs before reviews: `reviews.pipeline_run_id` points at this
            # table, so loading reviews first fails on the foreign key.
            runs, stages = self._load_pipeline_runs(
                session,
                datasets["pipeline_run_metrics"],
                datasets["data_quality_metrics"],
            )
            counts["pipeline_runs"] = runs
            counts["pipeline_stage_runs"] = stages
            counts["data_quality_results"] = self._load_quality_results(
                session, datasets["data_quality_metrics"]
            )

            run_id = _first_run_uuid(datasets["pipeline_run_metrics"])
            counts["reviews"] = self._load_reviews(session, silver, run_id)
            counts["review_topics"] = self._load_review_topics(session, silver)

            counts["daily_brand_metrics"] = self._load_brand_keyed(
                session,
                datasets["daily_brand_metrics"],
                DailyBrandMetric,
                {
                    "review_date": "metric_date",
                    "review_count": "review_count",
                    "average_rating": "average_rating",
                    "positive_count": "positive_count",
                    "neutral_count": "neutral_count",
                    "negative_count": "negative_count",
                    "positive_percentage": "positive_percentage",
                    "negative_percentage": "negative_percentage",
                    "average_sentiment_score": "average_sentiment_score",
                    "country_count": "country_count",
                    "language_count": "language_count",
                },
                "daily_brand",
            )
            counts["daily_topic_metrics"] = self._load_brand_keyed(
                session,
                datasets["daily_topic_metrics"],
                DailyTopicMetric,
                {
                    "review_date": "metric_date",
                    "topic": "topic",
                    "review_count": "review_count",
                    "average_rating": "average_rating",
                    "negative_count": "negative_count",
                    "negative_percentage": "negative_percentage",
                    "average_sentiment_score": "average_sentiment_score",
                },
                "daily_topic",
                extra_key="topic",
            )
            counts["sentiment_trends"] = self._load_brand_keyed(
                session,
                datasets["sentiment_trends"],
                SentimentTrend,
                {
                    "review_date": "metric_date",
                    "review_count": "review_count",
                    "negative_count": "negative_count",
                    "negative_percentage": "negative_percentage",
                    "average_rating": "average_rating",
                    "average_sentiment_score": "average_sentiment_score",
                    "negative_percentage_7d": "negative_percentage_7d",
                    "review_count_7d": "review_count_7d",
                },
                "sentiment_trend",
            )
            counts["country_metrics"] = self._load_date_keyed(
                session,
                datasets["country_metrics"],
                CountryMetric,
                {
                    "review_date": "metric_date",
                    "country": "country",
                    "review_count": "review_count",
                    "average_rating": "average_rating",
                    "negative_count": "negative_count",
                    "negative_percentage": "negative_percentage",
                    "brand_count": "brand_count",
                },
                "country_metric",
                "country",
            )
            counts["language_distribution"] = self._load_date_keyed(
                session,
                datasets["language_distribution"],
                LanguageDistribution,
                {
                    "review_date": "metric_date",
                    "language": "language",
                    "review_count": "review_count",
                    "average_confidence": "average_confidence",
                    "negative_count": "negative_count",
                    "average_rating": "average_rating",
                },
                "language_distribution",
                "language",
            )
            counts["anomalies"] = self._load_anomalies(session, datasets["anomalies"])
            counts["review_date_bounds"] = self._refresh_date_bounds(session, silver)

        duration = time.perf_counter() - started
        result = LoadResult(rows_by_table=counts, duration_seconds=duration)
        log.info(
            "loader_complete",
            rows=result.total_rows,
            duration_seconds=round(duration, 2),
            tables=len(counts),
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: object) -> Any:
    """NaN and NaT become None; everything else passes through.

    `pd.isna` raises on a list or array rather than returning a scalar, which
    is why this is wrapped: Silver's `topics` column holds arrays, and a bare
    `if pd.isna(value)` would blow up on them.
    """
    if value is None:
        return None
    try:
        # `pd.isna` has no overload for a bare `object`, so the call is
        # narrowed here rather than loosening the signature to Any — callers
        # genuinely do pass values of unknown type.
        if bool(pd.isna(value)):  # type: ignore[call-overload]
            return None
    except (TypeError, ValueError):  # pragma: no cover - arrays and lists
        return value
    return _py(value)


def _int(value: object) -> int:
    """Coerce a possibly-missing numeric to a plain int, defaulting to zero."""
    cleaned = _clean(value)
    return 0 if cleaned is None else int(cleaned)


def _as_topic_list(topics: object, primary: object) -> list[str]:
    """Normalise Silver's `topics` field into a list of distinct topic names.

    It arrives as a list, a numpy array or a delimited string depending on how
    the Parquet was written, so each form is handled rather than assumed.
    """
    values: Iterable[object]
    if topics is None:
        values = []
    elif isinstance(topics, str):
        values = [part.strip() for part in topics.split(",")]
    elif hasattr(topics, "tolist"):
        values = topics.tolist()
    elif isinstance(topics, (list, tuple)):
        values = topics
    else:  # pragma: no cover - defensive
        values = []

    names = [str(value) for value in values if value is not None and str(value).strip()]
    if primary is not None and str(primary) not in names:
        names.append(str(primary))

    # dict.fromkeys keeps first-seen order, which keeps the primary topic
    # ordering stable rather than shuffling it through a set.
    return list(dict.fromkeys(names))


def _stage_rows(run_uuid: uuid.UUID, stages_json: object) -> list[dict[str, Any]]:
    """Expand a run's `stages_json` blob into stage rows."""
    if not isinstance(stages_json, str) or not stages_json.strip():
        return []
    try:
        stages = json.loads(stages_json)
    except json.JSONDecodeError:  # pragma: no cover - written by our own code
        log.warning("loader_stages_unparseable", run_id=str(run_uuid))
        return []

    rows: list[dict[str, Any]] = []
    for stage in stages:
        name = str(stage.get("stage", "unknown"))
        rows.append(
            {
                "id": stable_id("stage", run_uuid, name),
                "pipeline_run_id": run_uuid,
                "stage_name": name,
                "status": str(stage.get("status", "unknown")),
                "started_at": stage.get("started_at"),
                "completed_at": stage.get("completed_at"),
                "duration_seconds": stage.get("duration_seconds"),
                "rows_in": stage.get("rows_in"),
                "rows_out": stage.get("rows_out"),
                "processed_rows": stage.get("rows_out"),
                "retry_count": int(stage.get("retry_count") or 0),
                "error_message": stage.get("error_message"),
            }
        )
    return rows


def _duplicates_by_run(quality: pd.DataFrame) -> dict[str, int]:
    """Duplicate row count per run, read from the quality dataset.

    The value is repeated on every rule row for a run, so any one of them will
    do — `max` simply avoids depending on which row comes first.
    """
    if quality.empty or "duplicate_records" not in quality.columns:
        return {}
    grouped = quality.groupby("run_id")["duplicate_records"].max()
    return {str(run_id): _int(value) for run_id, value in grouped.items()}


def _first_run_uuid(runs: pd.DataFrame) -> uuid.UUID | None:
    """The most recent run, used to stamp `reviews.pipeline_run_id`."""
    if runs.empty or "run_id" not in runs.columns:
        return None
    latest = runs.sort_values("started_at").iloc[-1]
    return stable_id("pipeline_run", latest["run_id"])


def load_to_postgres(settings: PipelineSettings, database_url: str) -> LoadResult:
    """Convenience entry point used by the CLI and the tests."""
    return PostgresLoader(settings, database_url).load_all()


def table_counts(database_url: str) -> dict[str, int]:
    """Row count per table, for verifying a load actually landed."""
    engine = create_engine(database_url, pool_pre_ping=True)
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine)
    counts: dict[str, int] = {}
    with factory() as session:
        # Reversed so the output reads parents-first, which is the order a
        # human checks them in: brands, then reviews, then everything else.
        for model in reversed(TRUNCATION_ORDER):
            counts[str(model.__tablename__)] = (
                session.scalar(select(func.count()).select_from(model)) or 0
            )
    return counts
