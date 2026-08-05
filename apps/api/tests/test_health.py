"""Tests for the health endpoint and the global error contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__


def test_health_returns_200_even_without_a_database(client: TestClient) -> None:
    """Health must report a database outage, not fail because of one.

    No Postgres is running during unit tests, so this simultaneously proves
    the endpoint is reachable and that the degraded path works.
    """
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["version"] == __version__
    assert body["processing_version"]
    assert body["timestamp"]


def test_health_reports_database_check(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()

    checks = {check["name"]: check for check in body["checks"]}
    assert "database" in checks
    assert checks["database"]["status"] in {"ok", "unavailable"}
    # When the database is down the reason must be visible, not swallowed.
    if checks["database"]["status"] == "unavailable":
        assert checks["database"]["detail"]
        assert body["status"] == "degraded"


def test_unknown_route_uses_the_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)


def test_openapi_schema_is_generated(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Pensieve API"
    assert "/api/v1/health" in schema["paths"]
