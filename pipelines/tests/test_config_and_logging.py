"""Tests for pipeline settings and structured logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines.common.config import PipelineSettings, get_pipeline_settings
from pipelines.common.domain import DataLayer
from pipelines.common.logging import configure_logging, get_logger


class TestPipelineSettings:
    def test_relative_data_root_resolves_against_the_repository(self) -> None:
        """Paths must not depend on the current working directory: the pipeline
        is launched from the repo root, from scripts/, and from pytest."""
        settings = PipelineSettings(PENSIEVE_DATA_ROOT="data")

        assert settings.data_root.is_absolute()
        assert settings.data_root.name == "data"

    def test_absolute_data_root_is_left_alone(self, tmp_path: Path) -> None:
        settings = PipelineSettings(PENSIEVE_DATA_ROOT=str(tmp_path))

        assert settings.data_root == tmp_path

    def test_layer_paths_are_nested_under_the_data_root(self, tmp_path: Path) -> None:
        settings = PipelineSettings(PENSIEVE_DATA_ROOT=str(tmp_path))

        assert settings.bronze_path == tmp_path / "bronze"
        assert settings.silver_path == tmp_path / "silver"
        assert settings.gold_path == tmp_path / "gold"
        assert settings.quarantine_path == tmp_path / "quarantine"
        assert settings.layer_path(DataLayer.BRONZE) == settings.bronze_path

    def test_ensure_directories_creates_every_layer(self, tmp_path: Path) -> None:
        settings = PipelineSettings(PENSIEVE_DATA_ROOT=str(tmp_path))

        settings.ensure_directories()

        for path in (
            settings.bronze_path,
            settings.silver_path,
            settings.gold_path,
            settings.quarantine_path,
            settings.samples_path,
        ):
            assert path.is_dir()

    def test_ensure_directories_is_idempotent(self, tmp_path: Path) -> None:
        settings = PipelineSettings(PENSIEVE_DATA_ROOT=str(tmp_path))

        settings.ensure_directories()
        settings.ensure_directories()  # must not raise

        assert settings.bronze_path.is_dir()

    @pytest.mark.parametrize("value", [0, 513])
    def test_sentiment_batch_size_is_bounded(self, value: int) -> None:
        with pytest.raises(ValueError, match=r"sentiment_batch_size|less than|greater than"):
            PipelineSettings(PENSIEVE_SENTIMENT_BATCH_SIZE=value)

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_language_confidence_must_be_a_probability(self, value: float) -> None:
        with pytest.raises(ValueError, match=r"language_min_confidence|less than|greater than"):
            PipelineSettings(PENSIEVE_LANGUAGE_MIN_CONFIDENCE=value)

    def test_sentiment_backend_rejects_unknown_values(self) -> None:
        """A typo here would otherwise silently fall back to some default and
        mislabel which model produced the results."""
        with pytest.raises(ValueError, match=r"PENSIEVE_SENTIMENT_BACKEND"):
            PipelineSettings(PENSIEVE_SENTIMENT_BACKEND="gpt")

    def test_settings_are_immutable(self) -> None:
        settings = PipelineSettings()

        with pytest.raises(ValueError, match=r"frozen|immutable"):
            settings.sentiment_batch_size = 64  # type: ignore[misc]

    def test_get_pipeline_settings_is_cached(self) -> None:
        get_pipeline_settings.cache_clear()

        assert get_pipeline_settings() is get_pipeline_settings()


class TestLogging:
    def test_json_output_is_machine_readable(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO", fmt="json", force=True)
        log = get_logger("test.pipeline", batch_id="01ABC", stage="ingestion")

        log.info("bronze_written", rows=1234)

        record = json.loads(capsys.readouterr().err.strip())
        assert record["event"] == "bronze_written"
        assert record["rows"] == 1234
        assert record["batch_id"] == "01ABC"
        assert record["stage"] == "ingestion"
        assert record["level"] == "info"
        assert record["logger"] == "test.pipeline"
        assert record["timestamp"].endswith("Z")

    def test_bound_context_persists_across_calls(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO", fmt="json", force=True)
        log = get_logger("test.pipeline", run_id="run-1")

        log.info("first")
        log.info("second")

        lines = [json.loads(line) for line in capsys.readouterr().err.strip().splitlines()]
        assert [entry["run_id"] for entry in lines] == ["run-1", "run-1"]

    def test_level_filtering_suppresses_quieter_messages(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(level="WARNING", fmt="json", force=True)
        log = get_logger("test.pipeline")

        log.info("should_not_appear")
        log.warning("should_appear")

        output = capsys.readouterr().err
        assert "should_not_appear" not in output
        assert "should_appear" in output

    def test_logs_go_to_stderr_leaving_stdout_for_data(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI jobs write results to stdout; mixing logs in would corrupt any
        piped output."""
        configure_logging(level="INFO", fmt="json", force=True)

        get_logger("test.pipeline").info("some_event")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "some_event" in captured.err

    def test_exception_info_is_captured_not_swallowed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(level="INFO", fmt="json", force=True)
        log = get_logger("test.pipeline")

        def failing_stage() -> None:
            raise ValueError("bad row")

        try:
            failing_stage()
        except ValueError:
            log.exception("stage_failed", stage="validation")

        record = json.loads(capsys.readouterr().err.strip())
        assert record["event"] == "stage_failed"
        assert "ValueError: bad row" in record["exception"]
