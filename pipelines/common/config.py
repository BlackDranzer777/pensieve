"""Configuration for the data platform.

Settings come from environment variables (optionally via a `.env` file at the
repository root). Every setting has a working default so the pipeline runs
out of the box after `make setup`.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipelines.common.domain import DataLayer


def _repo_root() -> Path:
    """Resolve the repository root from this file's location.

    `pipelines/common/config.py` -> up three levels. Anchoring on the source
    tree rather than the current working directory means the pipeline resolves
    the same paths whether it is launched from the repo root, from `scripts/`,
    or by a test runner.
    """
    return Path(__file__).resolve().parents[2]


class PipelineSettings(BaseSettings):
    """Runtime configuration for ingestion, enrichment and aggregation."""

    model_config = SettingsConfigDict(
        env_file=_repo_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Storage ----------------------------------------------------------
    data_root: Path = Field(default=Path("data"), alias="PENSIEVE_DATA_ROOT")

    # --- Logging ----------------------------------------------------------
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")

    # --- NLP --------------------------------------------------------------
    sentiment_backend: Literal["transformers", "lexicon"] = Field(
        default="transformers", alias="PENSIEVE_SENTIMENT_BACKEND"
    )
    sentiment_model: str = Field(
        default="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        alias="PENSIEVE_SENTIMENT_MODEL",
    )
    sentiment_batch_size: int = Field(
        default=32, ge=1, le=512, alias="PENSIEVE_SENTIMENT_BATCH_SIZE"
    )
    language_min_confidence: float = Field(
        default=0.65, ge=0.0, le=1.0, alias="PENSIEVE_LANGUAGE_MIN_CONFIDENCE"
    )
    #: Where Hugging Face caches the ~1.1 GB model. Empty means use the
    #: library's own default (`~/.cache/huggingface`).
    hf_home: str = Field(default="", alias="HF_HOME")

    # --- Spark ------------------------------------------------------------
    spark_master: str = Field(default="local[*]", alias="SPARK_MASTER")
    spark_driver_memory: str = Field(default="2g", alias="SPARK_DRIVER_MEMORY")
    spark_shuffle_partitions: int = Field(default=8, ge=1, alias="SPARK_SHUFFLE_PARTITIONS")

    @field_validator("data_root")
    @classmethod
    def _absolutise(cls, value: Path) -> Path:
        """Make a relative data root absolute against the repository root."""
        return value if value.is_absolute() else (_repo_root() / value).resolve()

    # --- Derived paths ----------------------------------------------------
    def layer_path(self, layer: DataLayer) -> Path:
        """Return the root directory for a medallion layer."""
        return self.data_root / layer.value

    @property
    def bronze_path(self) -> Path:
        return self.layer_path(DataLayer.BRONZE)

    @property
    def silver_path(self) -> Path:
        return self.layer_path(DataLayer.SILVER)

    @property
    def gold_path(self) -> Path:
        return self.layer_path(DataLayer.GOLD)

    @property
    def quarantine_path(self) -> Path:
        return self.layer_path(DataLayer.QUARANTINE)

    @property
    def samples_path(self) -> Path:
        return self.data_root / "samples"

    @property
    def repo_root(self) -> Path:
        """The repository root.

        Needed as the working directory when a pipeline job is launched as a
        subprocess: `python -m pipelines.jobs...` only resolves if the process
        starts where the packages live, and the API's own working directory is
        `apps/api` under Docker.
        """
        return _repo_root()

    def apply_hf_home(self) -> None:
        """Export `HF_HOME` into the OS environment.

        Reading it into this settings object is not enough: `transformers`
        and `huggingface_hub` read `os.environ` directly, and a value that
        only lives in `.env` is silently ignored. That is how a 1.1 GB model
        ends up somewhere other than the directory you configured — with no
        error to tell you.

        Must run *before* transformers is imported, which is why the
        sentiment backend calls it at load time rather than at module import.
        """
        if not self.hf_home:
            return
        target = Path(self.hf_home).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(target)

    def ensure_directories(self) -> None:
        """Create every data directory that the pipeline writes to."""
        for path in (
            self.bronze_path,
            self.silver_path,
            self.gold_path,
            self.quarantine_path,
            self.samples_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_pipeline_settings() -> PipelineSettings:
    """Return the process-wide settings singleton.

    Cached because settings are immutable and reading `.env` repeatedly during
    a large batch run is pointless overhead. Tests that need different values
    can call `get_pipeline_settings.cache_clear()`.
    """
    return PipelineSettings()
