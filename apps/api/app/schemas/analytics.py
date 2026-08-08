"""Response models for the analytics endpoints.

Separate from the ORM models on purpose. The database schema is an internal
detail that will change; the API contract is what the frontend compiles
against. Coupling them means a column rename becomes a breaking API change.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# `from_attributes` lets these be built straight from ORM rows without a manual
# field-by-field copy, while still going through Pydantic validation.
ORM = ConfigDict(from_attributes=True)


class BrandSummary(BaseModel):
    """A brand's totals over the requested window."""

    model_config = ORM

    brand_id: uuid.UUID
    brand: str
    review_count: int
    average_rating: float | None
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_percentage: float | None
    negative_percentage: float | None
    average_sentiment_score: float | None


class BrandComparison(BaseModel):
    """Side-by-side brand totals, plus the window they cover.

    The window is echoed back because a comparison is meaningless without it —
    "Brand A has 400 reviews" invites the immediate question "over what
    period?", and the caller should not have to remember what it asked for.
    """

    brands: list[BrandSummary]
    date_from: date | None
    date_to: date | None
    total_reviews: int


class DailyPoint(BaseModel):
    """One day in a time series."""

    model_config = ORM

    metric_date: date
    review_count: int
    average_rating: float | None = None
    negative_percentage: float | None = None
    average_sentiment_score: float | None = None


class SentimentTrendPoint(DailyPoint):
    """A day of sentiment, with the trailing baseline it is measured against.

    Both the value and its baseline are returned so a chart can draw them
    together. Sending only the value would force the frontend to recompute the
    rolling window, which is precisely the duplication that lets a dashboard
    and its alerts disagree.
    """

    model_config = ORM

    negative_count: int
    negative_percentage_7d: float | None = None
    review_count_7d: float | None = None


class BrandSeries(BaseModel):
    """One brand's time series."""

    brand_id: uuid.UUID
    brand: str
    points: list[SentimentTrendPoint]


class SentimentTrends(BaseModel):
    series: list[BrandSeries]
    date_from: date | None
    date_to: date | None


class TopicPoint(BaseModel):
    model_config = ORM

    metric_date: date
    topic: str
    review_count: int
    negative_count: int
    negative_percentage: float | None = None
    average_sentiment_score: float | None = None


class TopicSeries(BaseModel):
    topic: str
    total_reviews: int
    points: list[TopicPoint]


class TopicTrends(BaseModel):
    """Topic volume over time, ordered by how fast each topic is growing.

    `change_percentage` compares the most recent third of the window with the
    first third. It answers "what is getting worse", which is the question the
    Trends page exists for — a plain total only says what is already known to
    be big.
    """

    series: list[TopicSeries]
    fastest_growing: str | None
    change_percentage: float | None
    date_from: date | None
    date_to: date | None


class CountryPoint(BaseModel):
    model_config = ORM

    country: str
    review_count: int
    average_rating: float | None
    negative_count: int
    negative_percentage: float | None


class LanguagePoint(BaseModel):
    """A language's share of the window.

    `percentage` is computed at read time rather than stored, so it can never
    disagree with `review_count`.
    """

    language: str
    review_count: int
    percentage: float
    average_confidence: float | None


class AnomalyOut(BaseModel):
    model_config = ORM

    id: uuid.UUID
    anomaly_key: str
    brand: str | None
    detected_date: date
    metric: str
    topic: str | None
    country: str | None
    current_value: float | None
    baseline_value: float | None
    percentage_change: float | None
    z_score: float | None
    review_count: int | None
    severity: str
    explanation: str | None
    detected_at: datetime | None


class OverviewKpis(BaseModel):
    """The numbers on the executive overview.

    Every field is nullable or zero-defaulted because an empty database is a
    legitimate state — the dashboard should render "no data yet", not 500.
    """

    total_reviews: int = 0
    non_duplicate_reviews: int = 0
    brands: int = 0
    languages: int = 0
    countries: int = 0
    average_rating: float | None = None
    positive_percentage: float | None = None
    negative_percentage: float | None = None
    earliest_review: date | None = None
    latest_review: date | None = None


class TopicShare(BaseModel):
    topic: str
    review_count: int
    percentage: float


class Overview(BaseModel):
    """Everything the landing page needs, in one request.

    Deliberately one endpoint rather than six. The overview would otherwise
    fire six parallel requests that must all succeed before anything renders,
    which is six chances to show a spinner forever.
    """

    kpis: OverviewKpis
    sentiment_mix: dict[str, int] = Field(default_factory=dict)
    top_topics: list[TopicShare] = Field(default_factory=list)
    languages: list[LanguagePoint] = Field(default_factory=list)
    active_anomalies: list[AnomalyOut] = Field(default_factory=list)
    latest_quality_score: float | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
