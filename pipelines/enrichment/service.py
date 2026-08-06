"""Enrichment orchestration: clean records in, Silver records out.

    validated records
        -> detect language        Lingua, with a confidence floor
        -> score sentiment        local transformer, batched
        -> classify topics        multilingual keyword rules
        -> attach lineage         processing version, timestamp
        -> write Silver           partitioned by review date

Order matters. Language runs first because it is cheap and its result is
useful context. Sentiment runs on **every** record including unsupported
languages — the XLM-R backbone covers far more languages than we support
end to end, so discarding those scores would throw away real signal. What we
do *not* do is pretend the language was recognised: it stays `unsupported`,
and the dashboard can filter on that.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipelines.common.config import PipelineSettings, get_pipeline_settings
from pipelines.common.logging import get_logger
from pipelines.enrichment.language import detect_languages
from pipelines.enrichment.sentiment import score_sentiments
from pipelines.enrichment.silver import finalise_silver_columns, write_silver
from pipelines.enrichment.topics import classify_many

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    """Outcome of enriching one batch."""

    records: pd.DataFrame
    silver_paths: list[Path]
    duration_seconds: float
    language_distribution: dict[str, int]
    sentiment_distribution: dict[str, int]
    topic_distribution: dict[str, int]
    sentiment_model_version: str

    @property
    def rows(self) -> int:
        return len(self.records)

    @property
    def rows_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.rows / self.duration_seconds

    @property
    def unclassified_topic_share(self) -> float:
        """Share of reviews that matched no topic keyword.

        Worth watching: a rising `other` share means the taxonomy is drifting
        away from what customers actually talk about.
        """
        if self.rows == 0:
            return 0.0
        return self.topic_distribution.get("other", 0) / self.rows


def enrich_records(
    frame: pd.DataFrame, *, settings: PipelineSettings | None = None
) -> pd.DataFrame:
    """Add language, sentiment and topic columns. Pure — writes nothing."""
    settings = settings or get_pipeline_settings()

    if frame.empty:
        return frame

    result = frame.copy()
    # Enrichment reads `normalized_text`: HTML tags and stray whitespace are
    # noise to a language detector and to keyword matching alike. The original
    # `text` stays untouched in its own column.
    texts: list[str] = result["normalized_text"].fillna("").astype(str).tolist()

    languages = detect_languages(texts, min_confidence=settings.language_min_confidence)
    result["language"] = [item.language.value for item in languages]
    result["language_confidence"] = [round(item.confidence, 4) for item in languages]
    result["language_detected_name"] = [item.detected_name for item in languages]

    sentiments = score_sentiments(
        texts,
        backend=settings.sentiment_backend,
        model_name=settings.sentiment_model,
        batch_size=settings.sentiment_batch_size,
    )
    result["sentiment"] = [item.sentiment.value for item in sentiments]
    result["sentiment_score"] = [item.score for item in sentiments]
    result["sentiment_model_version"] = [item.model_version for item in sentiments]

    topics = classify_many(texts)
    result["primary_topic"] = [item.primary_topic.value for item in topics]
    # Stored as a comma-separated string rather than a list: Parquet handles
    # lists fine, but a plain string survives the round trip through CSV
    # export, DuckDB and PostgreSQL without special handling at every step.
    result["topics"] = [",".join(topic.value for topic in item.topics) for item in topics]
    result["topic_match_reason"] = [item.reason() for item in topics]

    return result


def enrich_batch(
    frame: pd.DataFrame,
    *,
    settings: PipelineSettings | None = None,
    write: bool = True,
) -> EnrichmentResult:
    """Enrich validated records and optionally persist them to Silver."""
    settings = settings or get_pipeline_settings()
    started = time.perf_counter()

    if frame.empty:
        return EnrichmentResult(
            records=frame,
            silver_paths=[],
            duration_seconds=0.0,
            language_distribution={},
            sentiment_distribution={},
            topic_distribution={},
            sentiment_model_version="",
        )

    enriched = enrich_records(frame, settings=settings)

    # `review_date` is the partition key: the day the customer wrote it.
    enriched["review_date"] = (
        pd.to_datetime(enriched["created_at"], errors="coerce", utc=True)
        .dt.strftime("%Y-%m-%d")
        .fillna("unknown")
    )

    silver = finalise_silver_columns(enriched)
    silver["review_date"] = enriched["review_date"].to_numpy()

    paths = write_silver(silver, settings.silver_path) if write else []
    duration = time.perf_counter() - started

    def distribution(column: str) -> dict[str, int]:
        counts = enriched[column].value_counts().to_dict()
        return {str(key): int(value) for key, value in counts.items()}

    result = EnrichmentResult(
        records=silver,
        silver_paths=paths,
        duration_seconds=duration,
        language_distribution=distribution("language"),
        sentiment_distribution=distribution("sentiment"),
        topic_distribution=distribution("primary_topic"),
        sentiment_model_version=str(enriched["sentiment_model_version"].iloc[0]),
    )

    log.info(
        "enrichment_complete",
        rows=result.rows,
        duration_seconds=round(duration, 3),
        rows_per_second=round(result.rows_per_second, 1),
        model_version=result.sentiment_model_version,
        languages=len(result.language_distribution),
        other_topic_share=round(result.unclassified_topic_share, 4),
    )
    return result
