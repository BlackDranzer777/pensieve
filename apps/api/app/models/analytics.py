"""Pre-aggregated tables loaded from the Gold layer, plus detected anomalies.

Every table here is a direct load of a Gold Parquet dataset. Nothing is
computed in Postgres — the aggregation happened once, in `analytics/sql/`, and
these tables exist so the dashboard reads a few hundred indexed rows instead of
scanning 37,800.

That is also why they are safe to truncate and reload: Parquet is the source of
truth, and these are a derived serving copy.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, LoadedAt, UUIDPrimaryKey


class DailyBrandMetric(Base, UUIDPrimaryKey, LoadedAt):
    """One brand's numbers for one day. From `gold/daily_brand_metrics`."""

    __tablename__ = "daily_brand_metrics"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_rating: Mapped[float | None] = mapped_column(Float)
    positive_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    neutral_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    negative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    positive_percentage: Mapped[float | None] = mapped_column(Float)
    negative_percentage: Mapped[float | None] = mapped_column(Float)
    average_sentiment_score: Mapped[float | None] = mapped_column(Float)
    country_count: Mapped[int | None] = mapped_column(Integer)
    language_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        # The grain of the dataset, enforced. A loader bug that double-inserts
        # a day would otherwise double every number on the dashboard, which is
        # the kind of error nobody notices until a meeting.
        UniqueConstraint("brand_id", "metric_date", name="uq_daily_brand_metrics_grain"),
        Index("ix_daily_brand_metrics_metric_date", "metric_date"),
    )


class DailyTopicMetric(Base, UUIDPrimaryKey, LoadedAt):
    """One topic, for one brand, on one day. From `gold/daily_topic_metrics`.

    The dataset behind "which complaint is growing fastest" — the question the
    whole platform exists to answer.
    """

    __tablename__ = "daily_topic_metrics"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    topic: Mapped[str] = mapped_column(String(50), nullable=False)

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_rating: Mapped[float | None] = mapped_column(Float)
    negative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    negative_percentage: Mapped[float | None] = mapped_column(Float)
    average_sentiment_score: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("brand_id", "metric_date", "topic", name="uq_daily_topic_metrics_grain"),
        Index("ix_daily_topic_metrics_topic_metric_date", "topic", "metric_date"),
    )


class CountryMetric(Base, UUIDPrimaryKey, LoadedAt):
    """Daily totals per country. From `gold/country_metrics`.

    Not in the original ERD. Added because the Brand Comparison page shows a
    country split, and deriving it live would mean scanning `reviews` on every
    page load to recompute something Gold already calculated.
    """

    __tablename__ = "country_metrics"

    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_rating: Mapped[float | None] = mapped_column(Float)
    negative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    negative_percentage: Mapped[float | None] = mapped_column(Float)
    brand_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("metric_date", "country", name="uq_country_metrics_grain"),
        Index("ix_country_metrics_metric_date", "metric_date"),
    )


class LanguageDistribution(Base, UUIDPrimaryKey, LoadedAt):
    """Daily language mix. From `gold/language_distribution`.

    Carries `average_confidence` so the Overview can distinguish "12% Spanish"
    from "12% guessed as Spanish, weakly" — the second is a data-quality signal
    rather than a market insight.

    There is no `percentage` column: the share of a day is a ratio between rows
    of this table, and storing it would create a second place for it to be
    wrong. The API computes it at read time from `review_count`.
    """

    __tablename__ = "language_distribution"

    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_confidence: Mapped[float | None] = mapped_column(Float)
    negative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    average_rating: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("metric_date", "language", name="uq_language_distribution_grain"),
        Index("ix_language_distribution_metric_date", "metric_date"),
    )


class SentimentTrend(Base, UUIDPrimaryKey, LoadedAt):
    """Daily sentiment with its trailing baseline. From `gold/sentiment_trends`.

    The rolling averages are computed in the Gold SQL over a **trailing**
    window, never a centred one. Recomputing them here would risk quietly
    reintroducing the centred version, which leaks future data into today's
    baseline and makes anomaly detection circular.
    """

    __tablename__ = "sentiment_trends"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    negative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    negative_percentage: Mapped[float | None] = mapped_column(Float)
    average_rating: Mapped[float | None] = mapped_column(Float)
    average_sentiment_score: Mapped[float | None] = mapped_column(Float)
    # The trailing 7-day windows, exactly as `sentiment_trends.sql` computed
    # them. Named `_7d` rather than `rolling_` so the window length stays
    # visible at the point of use.
    negative_percentage_7d: Mapped[float | None] = mapped_column(Float)
    review_count_7d: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("brand_id", "metric_date", name="uq_sentiment_trends_grain"),
        Index("ix_sentiment_trends_metric_date", "metric_date"),
    )


class Anomaly(Base, UUIDPrimaryKey, LoadedAt):
    """One detected anomaly. From `gold/anomalies`.

    `explanation` is stored rather than generated in the API because it must
    match the numbers that were true when detection ran. Regenerating it later
    from current data would produce a sentence that no longer describes the
    event it is attached to.
    """

    __tablename__ = "anomalies"

    # Deterministic id from the detector. Carried so a reload replaces an
    # anomaly rather than creating a second copy of it.
    anomaly_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(2))

    current_value: Mapped[float | None] = mapped_column(Float)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    percentage_change: Mapped[float | None] = mapped_column(Float)
    z_score: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)

    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    explanation: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_anomalies_detected_date_severity", "detected_date", "severity"),)
