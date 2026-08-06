"""Tests for readers, Bronze storage and the ingestion service."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipelines.common.config import PipelineSettings
from pipelines.ingestion.batch import (
    MANIFEST_FILENAME,
    BatchMetadata,
    UnsupportedFormatError,
    build_batch_metadata,
    compute_checksum,
    find_batch_by_checksum,
    new_batch_id,
    validate_source_format,
)
from pipelines.ingestion.bronze import (
    INGESTION_COLUMNS,
    read_bronze,
    read_bronze_batch,
    write_bronze,
)
from pipelines.ingestion.readers import (
    EmptySourceError,
    MalformedSourceError,
    read_source,
)
from pipelines.ingestion.service import ingest_file


class TestBatchIdentity:
    def test_batch_ids_are_unique(self) -> None:
        assert len({new_batch_id() for _ in range(500)}) == 500

    def test_batch_ids_sort_chronologically(self) -> None:
        """ULIDs sort by creation time, so `ls` on Bronze is in order."""
        ids = [new_batch_id() for _ in range(20)]

        assert ids == sorted(ids)

    def test_checksum_is_stable_for_identical_content(self, tmp_path: Path) -> None:
        first = tmp_path / "a.csv"
        second = tmp_path / "b.csv"
        first.write_text("review_id,text\n1,hello\n", encoding="utf-8")
        second.write_text("review_id,text\n1,hello\n", encoding="utf-8")

        assert compute_checksum(first) == compute_checksum(second)

    def test_checksum_changes_with_content(self, tmp_path: Path) -> None:
        path = tmp_path / "a.csv"
        path.write_text("one", encoding="utf-8")
        before = compute_checksum(path)
        path.write_text("two", encoding="utf-8")

        assert compute_checksum(path) != before

    def test_manifest_round_trips(self, tmp_path: Path) -> None:
        source = tmp_path / "reviews.csv"
        source.write_text("review_id\n1\n", encoding="utf-8")
        batch = build_batch_metadata(source, row_count=1, generator_seed=42)

        restored = BatchMetadata.from_json(batch.to_json())

        assert restored == batch

    @pytest.mark.parametrize("suffix", [".csv", ".json", ".jsonl", ".parquet"])
    def test_supported_formats_are_accepted(self, suffix: str) -> None:
        assert validate_source_format(Path(f"x{suffix}")) == suffix.lstrip(".")

    @pytest.mark.parametrize("suffix", [".txt", ".xlsx", ".pdf", ""])
    def test_unsupported_formats_are_rejected(self, suffix: str) -> None:
        with pytest.raises(UnsupportedFormatError):
            validate_source_format(Path(f"x{suffix}"))


class TestReaders:
    def test_reads_csv_without_coercing_values(self, tmp_path: Path) -> None:
        """The Bronze guarantee: a broken value must survive so it can later be
        quarantined with its original content shown."""
        path = tmp_path / "r.csv"
        path.write_text(
            "review_id,rating,created_at,text\n"
            "r1,seven,not-a-date,hello\n"
            "r2,5,2026-01-01T00:00:00,world\n",
            encoding="utf-8",
        )

        frame = read_source(path)

        assert frame.loc[0, "rating"] == "seven"
        assert frame.loc[0, "created_at"] == "not-a-date"
        assert all(dtype == "string" for dtype in frame.dtypes)

    def test_does_not_convert_the_literal_word_none_to_missing(self, tmp_path: Path) -> None:
        """pandas turns "None"/"NA"/"null" into NaN by default, which would make
        a genuine review reading "None" look like missing data."""
        path = tmp_path / "r.csv"
        path.write_text("review_id,text\nr1,None\nr2,NA\nr3,null\n", encoding="utf-8")

        frame = read_source(path)

        assert list(frame["text"]) == ["None", "NA", "null"]

    def test_reads_json_array(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        path.write_text(json.dumps([{"review_id": "r1", "rating": 5}]), encoding="utf-8")

        assert read_source(path).loc[0, "review_id"] == "r1"

    def test_reads_single_json_object(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"review_id": "r1"}), encoding="utf-8")

        assert len(read_source(path)) == 1

    def test_reads_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        path.write_text('{"review_id": "r1"}\n{"review_id": "r2"}\n', encoding="utf-8")

        assert len(read_source(path)) == 2

    def test_jsonl_reports_the_offending_line_number(self, tmp_path: Path) -> None:
        """In a million-line file, "line 2" is the difference between a minute
        and an afternoon."""
        path = tmp_path / "r.jsonl"
        path.write_text('{"review_id": "r1"}\nNOT JSON\n', encoding="utf-8")

        with pytest.raises(MalformedSourceError, match="line 2"):
            read_source(path)

    def test_reads_parquet(self, tmp_path: Path, clean_reviews: pd.DataFrame) -> None:
        path = tmp_path / "r.parquet"
        clean_reviews.to_parquet(path, index=False)

        assert len(read_source(path)) == len(clean_reviews)

    def test_preserves_multilingual_text(self, tmp_path: Path) -> None:
        path = tmp_path / "r.csv"
        path.write_text("review_id,text\nr1,स्वाद बहुत बढ़िया है\nr2,Świetna cena\n", encoding="utf-8")

        frame = read_source(path)

        assert frame.loc[0, "text"] == "स्वाद बहुत बढ़िया है"
        assert frame.loc[1, "text"] == "Świetna cena"

    def test_rejects_an_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "r.csv"
        path.write_text("review_id,text\n", encoding="utf-8")

        with pytest.raises(EmptySourceError):
            read_source(path)

    def test_rejects_malformed_json(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(MalformedSourceError):
            read_source(path)

    def test_missing_file_raises_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_source(tmp_path / "nope.csv")


class TestBronze:
    def test_writes_partitioned_by_date_and_batch(
        self, tmp_path: Path, clean_reviews: pd.DataFrame
    ) -> None:
        source = tmp_path / "r.csv"
        clean_reviews.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=len(clean_reviews))

        partition = write_bronze(clean_reviews, batch, tmp_path / "bronze")

        assert partition.name == f"batch_id={batch.batch_id}"
        assert partition.parent.name == f"ingestion_date={batch.ingestion_date.isoformat()}"
        assert (partition / "part-0000.parquet").exists()
        assert (partition / MANIFEST_FILENAME).exists()

    def test_attaches_ingestion_metadata(self, tmp_path: Path, clean_reviews: pd.DataFrame) -> None:
        source = tmp_path / "r.csv"
        clean_reviews.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=len(clean_reviews))

        write_bronze(clean_reviews, batch, tmp_path / "bronze")
        stored = read_bronze_batch(tmp_path / "bronze", batch.batch_id)

        for column in INGESTION_COLUMNS:
            assert column in stored.columns
        assert (stored["ingestion_batch_id"] == batch.batch_id).all()
        assert stored["source_row_number"].tolist() == list(range(1, len(clean_reviews) + 1))

    def test_preserves_source_values_exactly(self, tmp_path: Path) -> None:
        raw = pd.DataFrame(
            {"review_id": ["r1"], "rating": ["seven"], "text": ["  <b>messy</b>  "]}
        ).astype("string")
        source = tmp_path / "r.csv"
        raw.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=1)

        write_bronze(raw, batch, tmp_path / "bronze")
        stored = read_bronze_batch(tmp_path / "bronze", batch.batch_id)

        assert stored.loc[0, "rating"] == "seven"
        assert stored.loc[0, "text"] == "  <b>messy</b>  "

    def test_copies_the_original_file(self, tmp_path: Path, clean_reviews: pd.DataFrame) -> None:
        """Keeping the source means a parser bug found later can be replayed
        against the exact bytes that arrived."""
        source = tmp_path / "original.csv"
        clean_reviews.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=len(clean_reviews))

        partition = write_bronze(clean_reviews, batch, tmp_path / "bronze", source_path=source)

        assert (partition / "source" / "original.csv").exists()

    def test_refuses_to_overwrite_an_existing_batch(
        self, tmp_path: Path, clean_reviews: pd.DataFrame
    ) -> None:
        """Bronze is append-only. A silent overwrite would destroy the raw record."""
        source = tmp_path / "r.csv"
        clean_reviews.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=len(clean_reviews))
        write_bronze(clean_reviews, batch, tmp_path / "bronze")

        with pytest.raises(FileExistsError, match="append-only"):
            write_bronze(clean_reviews, batch, tmp_path / "bronze")

    def test_reading_an_empty_layer_returns_an_empty_frame(self, tmp_path: Path) -> None:
        assert read_bronze(tmp_path / "bronze").empty

    def test_reads_across_multiple_batches(
        self, tmp_path: Path, clean_reviews: pd.DataFrame
    ) -> None:
        bronze = tmp_path / "bronze"
        for index in range(3):
            source = tmp_path / f"r{index}.csv"
            clean_reviews.to_csv(source, index=False)
            write_bronze(clean_reviews, build_batch_metadata(source, len(clean_reviews)), bronze)

        assert len(read_bronze(bronze)) == 3 * len(clean_reviews)

    def test_find_by_checksum_locates_an_existing_batch(
        self, tmp_path: Path, clean_reviews: pd.DataFrame
    ) -> None:
        source = tmp_path / "r.csv"
        clean_reviews.to_csv(source, index=False)
        batch = build_batch_metadata(source, row_count=len(clean_reviews))
        write_bronze(clean_reviews, batch, tmp_path / "bronze")

        found = find_batch_by_checksum(tmp_path / "bronze", batch.file_checksum)

        assert found is not None
        assert found.batch_id == batch.batch_id

    def test_find_by_checksum_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert find_batch_by_checksum(tmp_path / "bronze", "deadbeef") is None


class TestIngestionService:
    def test_ingests_a_csv_end_to_end(self, settings: PipelineSettings, csv_file: Path) -> None:
        result = ingest_file(csv_file, settings=settings)

        assert result.was_already_ingested is False
        assert result.rows_ingested > 0
        assert result.partition_path.exists()
        assert result.rows_per_second > 0

    def test_re_ingesting_the_same_file_is_a_no_op(
        self, settings: PipelineSettings, csv_file: Path
    ) -> None:
        """Idempotency: a retried job must not duplicate every row."""
        first = ingest_file(csv_file, settings=settings)
        second = ingest_file(csv_file, settings=settings)

        assert second.was_already_ingested is True
        assert second.batch.batch_id == first.batch.batch_id
        assert second.rows_ingested == 0
        assert len(list(settings.bronze_path.rglob(MANIFEST_FILENAME))) == 1

    def test_force_ingests_a_second_copy(self, settings: PipelineSettings, csv_file: Path) -> None:
        first = ingest_file(csv_file, settings=settings)
        second = ingest_file(csv_file, settings=settings, force=True)

        assert second.batch.batch_id != first.batch.batch_id
        assert len(list(settings.bronze_path.rglob(MANIFEST_FILENAME))) == 2

    def test_identical_content_under_a_different_name_is_still_a_duplicate(
        self, settings: PipelineSettings, csv_file: Path, tmp_path: Path
    ) -> None:
        """Identity comes from content, not filename."""
        renamed = tmp_path / "different_name.csv"
        renamed.write_bytes(csv_file.read_bytes())

        ingest_file(csv_file, settings=settings)
        second = ingest_file(renamed, settings=settings)

        assert second.was_already_ingested is True

    def test_records_the_generator_seed_in_the_manifest(
        self, settings: PipelineSettings, csv_file: Path
    ) -> None:
        result = ingest_file(csv_file, settings=settings, generator_seed=1234)

        assert result.batch.generator_seed == 1234

    def test_unsupported_format_fails_before_reading(
        self, settings: PipelineSettings, tmp_path: Path
    ) -> None:
        path = tmp_path / "notes.txt"
        path.write_text("hello", encoding="utf-8")

        with pytest.raises(UnsupportedFormatError):
            ingest_file(path, settings=settings)

    def test_missing_file_raises(self, settings: PipelineSettings, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ingest_file(tmp_path / "absent.csv", settings=settings)
