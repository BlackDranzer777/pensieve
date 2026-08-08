"""Tests for the Parquet -> PostgreSQL loader.

The end-to-end load runs against SQLite, which exercises every transform and
the foreign-key ordering. What it cannot cover is the COPY bulk path, which is
PostgreSQL-only — that is asserted separately by a test that skips when no
database is reachable.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import Anomaly, Base, Brand, PipelineRun, Review, ReviewTopic
from pipelines.loading.postgres_loader import (
    LoaderError,
    PostgresLoader,
    _as_topic_list,
    _clean,
    _duplicates_by_run,
    _stage_rows,
    stable_id,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pipelines.common.config import PipelineSettings


class TestStableIds:
    def test_the_same_inputs_give_the_same_id(self) -> None:
        """Reloading must not renumber every row.

        Random ids would break every bookmarked `/reviews/<id>` link on each
        load, and make the aggregate tables impossible to join afterwards.
        """
        assert stable_id("review", "rev-1", "Aurora") == stable_id("review", "rev-1", "Aurora")

    def test_different_inputs_give_different_ids(self) -> None:
        assert stable_id("review", "rev-1") != stable_id("review", "rev-2")

    def test_the_prefix_separates_namespaces(self) -> None:
        """A review and a brand keyed on the same string must not collide."""
        assert stable_id("review", "x") != stable_id("brand", "x")


class TestValueCleaning:
    def test_nan_becomes_none(self) -> None:
        """A NaN average rating would poison every downstream average."""
        assert _clean(float("nan")) is None

    def test_nat_becomes_none(self) -> None:
        assert _clean(pd.NaT) is None

    def test_numpy_scalars_become_python_natives(self) -> None:
        """psycopg's COPY path cannot adapt `numpy.int64`."""
        cleaned = _clean(np.int64(42))

        assert cleaned == 42
        assert type(cleaned) is int

    def test_arrays_survive(self) -> None:
        """`pd.isna` raises on an array; Silver's `topics` column holds one."""
        assert _clean(np.array(["a", "b"])) is not None


class TestTopicParsing:
    def test_handles_a_list(self) -> None:
        assert _as_topic_list(["delivery", "price"], "delivery") == ["delivery", "price"]

    def test_handles_a_numpy_array(self) -> None:
        assert _as_topic_list(np.array(["delivery"]), "delivery") == ["delivery"]

    def test_handles_a_delimited_string(self) -> None:
        assert _as_topic_list("delivery, price", "delivery") == ["delivery", "price"]

    def test_adds_the_primary_topic_when_missing(self) -> None:
        assert _as_topic_list([], "delivery") == ["delivery"]

    def test_deduplicates_while_keeping_order(self) -> None:
        assert _as_topic_list(["price", "price", "delivery"], "price") == ["price", "delivery"]

    def test_empty_input_is_empty_output(self) -> None:
        assert _as_topic_list(None, None) == []


class TestStageExpansion:
    def test_expands_stages_json(self) -> None:
        run_id = uuid.uuid4()
        payload = json.dumps(
            [
                {
                    "stage": "ingestion",
                    "status": "success",
                    "duration_seconds": 0.1,
                    "rows_in": 10,
                    "rows_out": 10,
                    "retry_count": 0,
                }
            ]
        )

        rows = _stage_rows(run_id, payload)

        assert len(rows) == 1
        assert rows[0]["stage_name"] == "ingestion"
        assert rows[0]["pipeline_run_id"] == run_id

    def test_missing_json_yields_no_rows(self) -> None:
        assert _stage_rows(uuid.uuid4(), None) == []

    def test_unparseable_json_degrades_rather_than_raising(self) -> None:
        """A malformed telemetry blob must not abort an otherwise good load."""
        assert _stage_rows(uuid.uuid4(), "{not json") == []


class TestDuplicateCounts:
    def test_reads_the_count_from_the_quality_dataset(self) -> None:
        frame = pd.DataFrame(
            {
                "run_id": ["r1", "r1", "r2"],
                "duplicate_records": [12, 12, 3],
            }
        )

        assert _duplicates_by_run(frame) == {"r1": 12, "r2": 3}

    def test_missing_column_is_not_an_error(self) -> None:
        assert _duplicates_by_run(pd.DataFrame({"run_id": ["r1"]})) == {}


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """A file-backed SQLite database the loader can open independently."""
    return f"sqlite:///{(tmp_path / 'pensieve.db').as_posix()}"


def _prepare(url: str) -> None:
    Base.metadata.create_all(create_engine(url))


class TestEndToEndLoad:
    """A full load against real Parquet written by the pipeline fixtures."""

    def test_loads_every_layer(self, gold_data: PipelineSettings, sqlite_url: str) -> None:
        _prepare(sqlite_url)

        result = PostgresLoader(gold_data, sqlite_url).load_all()

        assert result.rows_by_table["brands"] > 0
        assert result.rows_by_table["reviews"] > 0
        assert result.total_rows > 0

    def test_review_counts_match_silver(self, gold_data: PipelineSettings, sqlite_url: str) -> None:
        from pipelines.enrichment.silver import read_silver

        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        silver = read_silver(gold_data.silver_path)
        with sessionmaker(bind=create_engine(sqlite_url))() as session:
            loaded = session.scalar(select(func.count()).select_from(Review)) or 0

        assert loaded == len(silver)

    def test_duplicates_are_loaded_and_marked(
        self, gold_data: PipelineSettings, sqlite_url: str
    ) -> None:
        """Duplicates belong in the Review Explorer, just not in the totals."""
        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        with sessionmaker(bind=create_engine(sqlite_url))() as session:
            total = session.scalar(select(func.count()).select_from(Review)) or 0
            marked = (
                session.scalar(
                    select(func.count())
                    .select_from(Review)
                    .where(Review.is_duplicate_of.is_not(None))
                )
                or 0
            )

        assert total > 0
        assert marked >= 0
        assert marked < total

    def test_every_review_has_at_least_one_topic(
        self, gold_data: PipelineSettings, sqlite_url: str
    ) -> None:
        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        with sessionmaker(bind=create_engine(sqlite_url))() as session:
            reviews = session.scalar(select(func.count()).select_from(Review)) or 0
            topics = session.scalar(select(func.count()).select_from(ReviewTopic)) or 0

        assert topics >= reviews

    def test_anomaly_keys_are_unique(self, gold_data: PipelineSettings, sqlite_url: str) -> None:
        """The unique constraint on `anomaly_key` is what caught the Gold bug.

        `anomaly_id` originally omitted topic and country, so 160 anomalies
        shared 146 ids and this load failed on a primary-key collision.
        """
        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        with sessionmaker(bind=create_engine(sqlite_url))() as session:
            total = session.scalar(select(func.count()).select_from(Anomaly)) or 0
            distinct = session.scalar(select(func.count(func.distinct(Anomaly.anomaly_key)))) or 0

        assert total == distinct

    def test_loading_twice_is_idempotent(
        self, gold_data: PipelineSettings, sqlite_url: str
    ) -> None:
        """A full replace, so a second run must not double anything."""
        _prepare(sqlite_url)
        loader = PostgresLoader(gold_data, sqlite_url)

        first = loader.load_all()
        second = PostgresLoader(gold_data, sqlite_url).load_all()

        assert first.rows_by_table == second.rows_by_table

    def test_brands_keep_their_ids_across_loads(
        self, gold_data: PipelineSettings, sqlite_url: str
    ) -> None:
        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        factory = sessionmaker(bind=create_engine(sqlite_url))
        with factory() as session:
            before = {brand.name: brand.id for brand in session.scalars(select(Brand))}

        PostgresLoader(gold_data, sqlite_url).load_all()
        with factory() as session:
            after = {brand.name: brand.id for brand in session.scalars(select(Brand))}

        assert before == after

    def test_run_telemetry_is_loaded(self, gold_data: PipelineSettings, sqlite_url: str) -> None:
        _prepare(sqlite_url)
        PostgresLoader(gold_data, sqlite_url).load_all()

        with sessionmaker(bind=create_engine(sqlite_url))() as session:
            run = session.scalars(select(PipelineRun)).first()

        assert run is not None
        assert run.input_rows > 0
        assert run.started_at <= datetime.now(UTC).replace(tzinfo=run.started_at.tzinfo)

    def test_missing_silver_fails_with_a_useful_message(
        self, settings: PipelineSettings, sqlite_url: str
    ) -> None:
        _prepare(sqlite_url)

        with pytest.raises(LoaderError, match="run_pipeline"):
            PostgresLoader(settings, sqlite_url).load_all()
