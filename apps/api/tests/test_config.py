"""Tests for settings parsing.

These exist because a settings bug does not fail a unit test — it fails at
process startup, which is the worst place to discover it.
"""

from __future__ import annotations

import pytest

from app.core.config import ApiSettings


def test_cors_origins_accepts_a_comma_separated_string() -> None:
    """`.env` files carry lists as comma-separated strings, not JSON.

    Regression test: pydantic-settings JSON-decodes values bound for list
    fields before validators run, so without `NoDecode` this raises a
    JSONDecodeError at import time and the API never starts.
    """
    settings = ApiSettings(CORS_ORIGINS="http://a.test, http://b.test")

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_accepts_a_real_list() -> None:
    settings = ApiSettings(CORS_ORIGINS=["http://a.test"])

    assert settings.cors_origins == ["http://a.test"]


def test_cors_origins_ignores_blank_entries() -> None:
    settings = ApiSettings(CORS_ORIGINS="http://a.test,, ,http://b.test")

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_has_a_working_default() -> None:
    """`_env_file=None` bypasses the developer's local `.env`, so this asserts
    the built-in default rather than whatever happens to be configured."""
    settings = ApiSettings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:5173", "http://localhost:4173"]


@pytest.mark.parametrize("value", [0, 61])
def test_db_connect_timeout_is_bounded(value: int) -> None:
    """An unbounded or zero connect timeout would let health checks hang."""
    with pytest.raises(ValueError, match=r"db_connect_timeout|less than|greater than"):
        ApiSettings(DB_CONNECT_TIMEOUT=value)


def test_is_production_reflects_the_environment() -> None:
    assert ApiSettings(API_ENV="production").is_production is True
    assert ApiSettings(API_ENV="development").is_production is False
