"""Shared fixtures for API tests.

These tests deliberately run without a database: the API must degrade cleanly
when Postgres is unavailable, and that behaviour is worth asserting directly.
Endpoints that genuinely need data get database-backed fixtures later, marked
with the `integration` marker.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_api_settings
from app.database.session import get_engine, get_session_factory
from app.main import create_app

# Settings are read lazily (through cached factories that the fixture below
# clears), so setting these at import time is early enough — no import-order
# gymnastics required.
#
# The short connect timeout keeps the failed-connection path fast: without it
# every health check would wait the full production timeout before reporting
# the database as down.
os.environ.setdefault("DB_CONNECT_TIMEOUT", "1")
os.environ.setdefault("API_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session", autouse=True)
def _reset_cached_singletons() -> Iterator[None]:
    """Drop cached settings and engine so the env vars above take effect."""
    for cached in (get_api_settings, get_engine, get_session_factory):
        cached.cache_clear()
    yield
    for cached in (get_api_settings, get_engine, get_session_factory):
        cached.cache_clear()


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Test client that surfaces server errors as real HTTP responses.

    `raise_server_exceptions=False` means an unhandled exception produces an
    actual 500 response, so the global error-shape contract can be asserted
    instead of the exception escaping into the test runner.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
