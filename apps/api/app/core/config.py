"""API configuration."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _repo_root() -> Path:
    """`apps/api/app/core/config.py` -> up five levels to the repository root."""
    return Path(__file__).resolve().parents[4]


class ApiSettings(BaseSettings):
    """Settings for the FastAPI service."""

    model_config = SettingsConfigDict(
        env_file=_repo_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    api_env: Literal["development", "test", "production"] = Field(
        default="development", alias="API_ENV"
    )
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")  # noqa: S104
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")

    database_url: str = Field(
        default="postgresql+psycopg://pensieve:pensieve_local_dev@localhost:5433/pensieve",
        alias="DATABASE_URL",
    )
    # Without an explicit timeout, a connection attempt to a host that silently
    # drops packets blocks forever — which would hang the health endpoint, the
    # very thing meant to detect that outage.
    db_connect_timeout: int = Field(default=5, ge=1, le=60, alias="DB_CONNECT_TIMEOUT")

    # `NoDecode` is essential here: without it pydantic-settings tries to
    # `json.loads()` any value destined for a list field *before* validators
    # run, so the comma-separated form that `.env` files naturally use raises
    # a JSONDecodeError at startup rather than reaching the validator below.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string, which is how `.env` files carry lists."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.api_env == "production"


@functools.lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the cached settings singleton (overridable in tests via cache_clear)."""
    return ApiSettings()
