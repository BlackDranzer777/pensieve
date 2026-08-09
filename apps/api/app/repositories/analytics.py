"""Queries against the pre-aggregated tables.

Every query here reads a Gold-derived table, never `reviews`. That is the whole
reason the Gold layer exists: the Brand Comparison page sums 450 rows instead
of scanning 37,800, and the difference only grows with the dataset.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, func, select

from app.models import (
    Anomaly,
    Brand,
    CountryMetric,
    DailyBrandMetric,
    DailyTopicMetric,
    LanguageDistribution,
    SentimentTrend,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.api.deps import DateRange


def _within(statement: Select[Any], column: Any, window: DateRange) -> Select[Any]:
    """Apply an inclusive date filter, skipping either end when it is open."""
    if window.date_from is not None:
        statement = statement.where(column >= window.date_from)
    if window.date_to is not None:
        statement = statement.where(column <= window.date_to)
    return statement


class AnalyticsRepository:
    """Reads the aggregate tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- brands ------------------------------------------------------------

    def brand_summaries(self, window: DateRange) -> list[dict[str, Any]]:
        """Totals per brand over the window.

        Percentages are recomputed from the summed counts rather than averaged
        from the daily percentages. Averaging a percentage across days weights
        a day with 3 reviews the same as one with 300, which is simply the
        wrong number — and a subtle enough error that it usually ships.
        """
        statement = (
            select(
                Brand.id.label("brand_id"),
                Brand.name.label("brand"),
                func.coalesce(func.sum(DailyBrandMetric.review_count), 0).label("review_count"),
                func.sum(DailyBrandMetric.positive_count).label("positive_count"),
                func.sum(DailyBrandMetric.neutral_count).label("neutral_count"),
                func.sum(DailyBrandMetric.negative_count).label("negative_count"),
                # A weighted mean: each day's average multiplied by its volume,
                # divided by total volume.
                (
                    func.sum(DailyBrandMetric.average_rating * DailyBrandMetric.review_count)
                    / func.nullif(func.sum(DailyBrandMetric.review_count), 0)
                ).label("average_rating"),
                (
                    func.sum(
                        DailyBrandMetric.average_sentiment_score * DailyBrandMetric.review_count
                    )
                    / func.nullif(func.sum(DailyBrandMetric.review_count), 0)
                ).label("average_sentiment_score"),
            )
            .join(DailyBrandMetric, DailyBrandMetric.brand_id == Brand.id)
            .group_by(Brand.id, Brand.name)
            .order_by(func.sum(DailyBrandMetric.review_count).desc())
        )
        statement = _within(statement, DailyBrandMetric.metric_date, window)

        summaries: list[dict[str, Any]] = []
        for row in self._session.execute(statement).mappings():
            total = row["review_count"] or 0
            summaries.append(
                {
                    **dict(row),
                    "positive_percentage": _share(row["positive_count"], total),
                    "negative_percentage": _share(row["negative_count"], total),
                }
            )
        return summaries

    # -- trends ------------------------------------------------------------

    def brand_ids_for(self, names: Sequence[str]) -> list[uuid.UUID]:
        """Resolve brand names to ids.

        The API filters by name because that is what a client has — a uuid is
        an internal detail nobody types into a URL. Resolving here keeps the
        trend queries filtering on the indexed foreign key rather than joining
        to `brands` and matching strings.
        """
        if not names:
            return []
        return list(self._session.scalars(select(Brand.id).where(Brand.name.in_(names))))

    def sentiment_series(
        self, window: DateRange, brand_ids: Sequence[uuid.UUID] | None = None
    ) -> dict[tuple[uuid.UUID, str], list[SentimentTrend]]:
        """Sentiment trend rows grouped by brand, ordered by date."""
        statement = (
            select(SentimentTrend, Brand.name)
            .join(Brand, Brand.id == SentimentTrend.brand_id)
            .order_by(Brand.name, SentimentTrend.metric_date)
        )
        statement = _within(statement, SentimentTrend.metric_date, window)
        if brand_ids:
            statement = statement.where(SentimentTrend.brand_id.in_(brand_ids))

        grouped: dict[tuple[uuid.UUID, str], list[SentimentTrend]] = {}
        for trend, brand_name in self._session.execute(statement):
            grouped.setdefault((trend.brand_id, brand_name), []).append(trend)
        return grouped

    def topic_series(
        self, window: DateRange, brand_ids: Sequence[uuid.UUID] | None = None
    ) -> list[dict[str, Any]]:
        """Daily topic totals, summed across brands unless one is selected."""
        statement = (
            select(
                DailyTopicMetric.metric_date,
                DailyTopicMetric.topic,
                func.sum(DailyTopicMetric.review_count).label("review_count"),
                func.sum(DailyTopicMetric.negative_count).label("negative_count"),
                (
                    func.sum(
                        DailyTopicMetric.average_sentiment_score * DailyTopicMetric.review_count
                    )
                    / func.nullif(func.sum(DailyTopicMetric.review_count), 0)
                ).label("average_sentiment_score"),
            )
            .group_by(DailyTopicMetric.metric_date, DailyTopicMetric.topic)
            .order_by(DailyTopicMetric.topic, DailyTopicMetric.metric_date)
        )
        statement = _within(statement, DailyTopicMetric.metric_date, window)
        if brand_ids:
            statement = statement.where(DailyTopicMetric.brand_id.in_(brand_ids))

        rows: list[dict[str, Any]] = []
        for row in self._session.execute(statement).mappings():
            total = row["review_count"] or 0
            rows.append({**dict(row), "negative_percentage": _share(row["negative_count"], total)})
        return rows

    # -- dimensions --------------------------------------------------------

    def country_totals(self, window: DateRange) -> list[dict[str, Any]]:
        statement = (
            select(
                CountryMetric.country,
                func.sum(CountryMetric.review_count).label("review_count"),
                func.sum(CountryMetric.negative_count).label("negative_count"),
                (
                    func.sum(CountryMetric.average_rating * CountryMetric.review_count)
                    / func.nullif(func.sum(CountryMetric.review_count), 0)
                ).label("average_rating"),
            )
            .group_by(CountryMetric.country)
            .order_by(func.sum(CountryMetric.review_count).desc())
        )
        statement = _within(statement, CountryMetric.metric_date, window)

        return [
            {
                **dict(row),
                "negative_percentage": _share(row["negative_count"], row["review_count"] or 0),
            }
            for row in self._session.execute(statement).mappings()
        ]

    def language_totals(self, window: DateRange) -> list[dict[str, Any]]:
        """Language mix, with each share computed against the window total."""
        statement = (
            select(
                LanguageDistribution.language,
                func.sum(LanguageDistribution.review_count).label("review_count"),
                (
                    func.sum(
                        LanguageDistribution.average_confidence * LanguageDistribution.review_count
                    )
                    / func.nullif(func.sum(LanguageDistribution.review_count), 0)
                ).label("average_confidence"),
            )
            .group_by(LanguageDistribution.language)
            .order_by(func.sum(LanguageDistribution.review_count).desc())
        )
        statement = _within(statement, LanguageDistribution.metric_date, window)

        rows = [dict(row) for row in self._session.execute(statement).mappings()]
        total = sum(row["review_count"] or 0 for row in rows)
        for row in rows:
            row["percentage"] = _share(row["review_count"], total) or 0.0
        return rows

    # -- anomalies ---------------------------------------------------------

    def anomalies(
        self,
        window: DateRange,
        *,
        severity: Sequence[str] | None = None,
        metric: str | None = None,
        brand_ids: Sequence[uuid.UUID] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Anomalies matching the filters, strongest first, with a total count.

        Ordered by absolute z-score rather than date: an operator opening this
        page wants the biggest deviation, not the most recent one.
        """
        base = select(Anomaly, Brand.name).outerjoin(Brand, Brand.id == Anomaly.brand_id)
        base = _within(base, Anomaly.detected_date, window)
        if severity:
            base = base.where(Anomaly.severity.in_(severity))
        if metric:
            base = base.where(Anomaly.metric == metric)
        if brand_ids:
            base = base.where(Anomaly.brand_id.in_(brand_ids))

        total = self._session.scalar(select(func.count()).select_from(base.subquery())) or 0

        statement = base.order_by(func.abs(Anomaly.z_score).desc(), Anomaly.detected_date.desc())
        if limit is not None:
            statement = statement.limit(limit).offset(offset)

        rows: list[dict[str, Any]] = []
        for anomaly, brand_name in self._session.execute(statement):
            rows.append(
                {
                    **{
                        column.name: getattr(anomaly, column.name)
                        for column in Anomaly.__table__.columns
                    },
                    "brand": brand_name,
                }
            )
        return rows, total

    # -- overview ----------------------------------------------------------

    def sentiment_mix(self, window: DateRange) -> dict[str, int]:
        statement = select(
            func.coalesce(func.sum(DailyBrandMetric.positive_count), 0),
            func.coalesce(func.sum(DailyBrandMetric.neutral_count), 0),
            func.coalesce(func.sum(DailyBrandMetric.negative_count), 0),
        )
        statement = _within(statement, DailyBrandMetric.metric_date, window)
        positive, neutral, negative = self._session.execute(statement).one()
        return {"positive": positive, "neutral": neutral, "negative": negative}

    def top_topics(self, window: DateRange, limit: int = 5) -> list[dict[str, Any]]:
        statement = (
            select(
                DailyTopicMetric.topic,
                func.sum(DailyTopicMetric.review_count).label("review_count"),
            )
            .group_by(DailyTopicMetric.topic)
            .order_by(func.sum(DailyTopicMetric.review_count).desc())
        )
        statement = _within(statement, DailyTopicMetric.metric_date, window)

        rows = [dict(row) for row in self._session.execute(statement).mappings()]
        total = sum(row["review_count"] or 0 for row in rows)
        for row in rows:
            row["percentage"] = _share(row["review_count"], total) or 0.0
        return rows[:limit]

    def metric_date_bounds(self) -> tuple[date | None, date | None]:
        """Earliest and latest day with metrics. Both None on an empty table."""
        row = self._session.execute(
            select(func.min(DailyBrandMetric.metric_date), func.max(DailyBrandMetric.metric_date))
        ).one()
        return row[0], row[1]


def _share(count: int | None, total: int) -> float | None:
    """A percentage, or None when there is nothing to divide by.

    Returning None rather than 0.0 for an empty denominator matters: "0% of no
    reviews were negative" is not a fact, and a chart should show a gap rather
    than a reassuring zero.
    """
    if not total:
        return None
    return round((count or 0) / total * 100, 2)
