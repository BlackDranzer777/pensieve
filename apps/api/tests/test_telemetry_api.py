"""Tests for pipeline-run, data-quality and dataset endpoints."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.telemetry import _datasets
from app.services.datasets import DatasetService, safe_filename
from pipelines.common.config import PipelineSettings
from tests.seed import RUN_ID


@pytest.fixture
def upload_client(app: FastAPI, seeded_client: TestClient, tmp_path: Path) -> Iterator[TestClient]:
    """A client whose uploads land in a temporary directory.

    Without this the upload tests write into the real `data/samples/`, leaving
    files behind in the repository — a test suite that dirties the working tree
    is one people stop trusting.
    """
    settings = PipelineSettings(PENSIEVE_DATA_ROOT=tmp_path)  # type: ignore[call-arg]
    app.dependency_overrides[_datasets] = lambda: DatasetService(settings)
    yield seeded_client
    app.dependency_overrides.pop(_datasets, None)


class TestPipelineRuns:
    def test_lists_runs(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/pipeline-runs").json()

        assert body["meta"]["total_items"] == 1
        assert body["items"][0]["batch_id"] == "01TESTBATCH"

    def test_run_detail_includes_the_stage_timeline(self, seeded_client: TestClient) -> None:
        """A total duration says something is slow; the stages say what."""
        body = seeded_client.get(f"/api/v1/pipeline-runs/{RUN_ID}").json()

        stages = [stage["stage_name"] for stage in body["stages"]]
        assert stages == ["ingestion", "validation", "enrichment"]

    def test_retries_are_visible(self, seeded_client: TestClient) -> None:
        """Succeeding on the third attempt is not the same as succeeding."""
        body = seeded_client.get(f"/api/v1/pipeline-runs/{RUN_ID}").json()

        enrichment = next(s for s in body["stages"] if s["stage_name"] == "enrichment")
        assert enrichment["status"] == "success"
        assert enrichment["retry_count"] == 2

    def test_quarantined_and_duplicate_counts_are_separate(self, seeded_client: TestClient) -> None:
        """Rejected data and double-counted data are different problems."""
        body = seeded_client.get(f"/api/v1/pipeline-runs/{RUN_ID}").json()

        assert body["quarantined_rows"] == 6
        assert body["duplicate_rows"] == 1

    def test_unknown_run_is_a_404(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipeline-runs/00000000-0000-5000-8000-000000000000")

        assert response.status_code == 404


class TestDataQuality:
    def test_defaults_to_the_latest_run(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/data-quality").json()

        assert body["run_id"] == str(RUN_ID)
        assert body["quality_score"] == 91.5

    def test_reports_rules_that_passed(self, seeded_client: TestClient) -> None:
        """Otherwise "no rows failed" and "the rule never ran" look identical."""
        body = seeded_client.get("/api/v1/data-quality").json()

        by_rule = {rule["rule_id"]: rule for rule in body["rules"]}
        assert by_rule["text_invalid"]["status"] == "passed"
        assert by_rule["text_invalid"]["affected_rows"] == 0
        assert by_rule["rating_out_of_range"]["status"] == "failed"

    def test_totals_come_from_the_run_not_the_rule_sum(self, seeded_client: TestClient) -> None:
        """A row failing two rules would otherwise be counted twice.

        The fixture's rules affect 4 + 2 + 0 = 6 rows and the run quarantined
        6, but that agreement is a coincidence of the fixture; the point is
        that the total is read from the run record.
        """
        body = seeded_client.get("/api/v1/data-quality").json()

        assert body["total_records"] == 20
        assert body["valid_records"] == 14
        assert body["quarantined_records"] == 6
        assert body["validity_rate"] == 70.0

    def test_empty_database_returns_an_empty_report(self, seeded_client: TestClient) -> None:
        """Requesting a run that does not exist is a 404; having none is not."""
        response = seeded_client.get(
            "/api/v1/data-quality",
            params={"run_id": "00000000-0000-5000-8000-000000000000"},
        )

        assert response.status_code == 404

    def test_trend_returns_oldest_first(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/data-quality/trend").json()

        assert len(body) == 1
        assert body[0]["quality_score"] == 91.5


class TestDatasetUpload:
    def test_accepts_a_csv(self, upload_client: TestClient) -> None:
        content = b"review_id,brand,text,rating,created_at\nr1,B,Good,5,2026-01-01\n"

        response = upload_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("reviews.csv", io.BytesIO(content), "text/csv")},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "reviews.csv"
        assert body["detected_rows"] == 1

    def test_reports_that_nothing_was_ingested(self, upload_client: TestClient) -> None:
        """Storing a file and processing it are different facts."""
        response = upload_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("reviews.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )

        assert "not been ingested" in response.json()["message"]

    def test_rejects_an_unsupported_format(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("payload.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_format"

    def test_rejects_an_empty_file(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )

        assert response.status_code == 422


class TestFilenameSanitisation:
    """An uploaded filename is attacker-controlled input."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("../../../etc/passwd.csv", "passwd.csv"),
            ("C:\\Windows\\System32\\evil.csv", "evil.csv"),
            ("....//traversal.csv", "traversal.csv"),
            ("normal-file_1.csv", "normal-file_1.csv"),
            ("spaces and;semicolons.csv", "spaces_and_semicolons.csv"),
        ],
    )
    def test_path_components_are_stripped(self, raw: str, expected: str) -> None:
        assert safe_filename(raw) == expected

    def test_result_is_never_a_path(self) -> None:
        for raw in ("../../x.csv", "/etc/x.csv", "..\\..\\x.csv"):
            cleaned = safe_filename(raw)
            assert "/" not in cleaned
            assert "\\" not in cleaned
            assert not cleaned.startswith(".")
