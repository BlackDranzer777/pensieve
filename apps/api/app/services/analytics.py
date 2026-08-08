"""Business logic for the analytics endpoints.

Repositories return rows; this layer turns them into the shapes the dashboard
asks for — grouping series, picking the fastest-growing topic, assembling the
overview from several sources.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.repositories.analytics import AnalyticsRepository
from app.repositories.telemetry import TelemetryRepository
from app.schemas.analytics import (
    AnomalyOut,
    BrandComparison,
    BrandSeries,
    BrandSummary,
    CountryPoint,
    LanguagePoint,
    Overview,
    OverviewKpis,
    SentimentTrendPoint,
    SentimentTrends,
    TopicPoint,
    TopicSeries,
    TopicShare,
    TopicTrends,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.api.deps import DateRange

#: How many of the strongest current anomalies the overview shows. Enough to be
#: useful, few enough that the page is not a wall of alerts nobody reads.
OVERVIEW_ANOMALY_LIMIT = 5


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AnalyticsRepository(session)
        self._telemetry = TelemetryRepository(session)

    def brands(self, window: DateRange) -> list[BrandSummary]:
        return [BrandSummary(**row) for row in self._repo.brand_summaries(window)]

    def brand_comparison(self, window: DateRange) -> BrandComparison:
        summaries = self.brands(window)
        return BrandComparison(
            brands=summaries,
            date_from=window.date_from,
            date_to=window.date_to,
            total_reviews=sum(summary.review_count for summary in summaries),
        )

    def sentiment_trends(
        self, window: DateRange, brand_ids: Sequence[uuid.UUID] | None = None
    ) -> SentimentTrends:
        grouped = self._repo.sentiment_series(window, brand_ids)
        series = [
            BrandSeries(
                brand_id=brand_id,
                brand=brand_name,
                points=[SentimentTrendPoint.model_validate(row) for row in rows],
            )
            for (brand_id, brand_name), rows in grouped.items()
        ]
        return SentimentTrends(series=series, date_from=window.date_from, date_to=window.date_to)

    def topic_trends(
        self, window: DateRange, brand_ids: Sequence[uuid.UUID] | None = None
    ) -> TopicTrends:
        rows = self._repo.topic_series(window, brand_ids)

        by_topic: dict[str, list[TopicPoint]] = {}
        for row in rows:
            by_topic.setdefault(row["topic"], []).append(TopicPoint.model_validate(row))

        series = sorted(
            (
                TopicSeries(
                    topic=topic,
                    total_reviews=sum(point.review_count for point in points),
                    points=points,
                )
                for topic, points in by_topic.items()
            ),
            key=lambda item: item.total_reviews,
            reverse=True,
        )

        fastest, change = _fastest_growing(by_topic)
        return TopicTrends(
            series=series,
            fastest_growing=fastest,
            change_percentage=change,
            date_from=window.date_from,
            date_to=window.date_to,
        )

    def countries(self, window: DateRange) -> list[CountryPoint]:
        return [CountryPoint(**row) for row in self._repo.country_totals(window)]

    def languages(self, window: DateRange) -> list[LanguagePoint]:
        return [LanguagePoint(**row) for row in self._repo.language_totals(window)]

    def anomalies(
        self,
        window: DateRange,
        *,
        severity: Sequence[str] | None = None,
        metric: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[AnomalyOut], int]:
        rows, total = self._repo.anomalies(
            window, severity=severity, metric=metric, limit=limit, offset=offset
        )
        return [AnomalyOut(**row) for row in rows], total

    def overview(self, window: DateRange) -> Overview:
        """Assemble the landing page from every source it needs."""
        summaries = self._repo.brand_summaries(window)
        languages = self._repo.language_totals(window)
        countries = self._repo.country_totals(window)
        mix = self._repo.sentiment_mix(window)
        anomalies, _ = self._repo.anomalies(window, limit=OVERVIEW_ANOMALY_LIMIT)
        earliest, latest = self._repo.metric_date_bounds()
        latest_run = self._telemetry.latest_run()

        total = sum(row["review_count"] or 0 for row in summaries)
        rated = sum((row["average_rating"] or 0) * (row["review_count"] or 0) for row in summaries)

        kpis = OverviewKpis(
            total_reviews=total,
            non_duplicate_reviews=total,
            brands=len(summaries),
            languages=len(languages),
            countries=len(countries),
            average_rating=round(rated / total, 2) if total else None,
            positive_percentage=_percentage(mix["positive"], total),
            negative_percentage=_percentage(mix["negative"], total),
            earliest_review=earliest,
            latest_review=latest,
        )

        return Overview(
            kpis=kpis,
            sentiment_mix=mix,
            top_topics=[TopicShare(**row) for row in self._repo.top_topics(window)],
            languages=[LanguagePoint(**row) for row in languages],
            active_anomalies=[AnomalyOut(**row) for row in anomalies],
            latest_quality_score=latest_run.quality_score if latest_run else None,
            last_run_at=latest_run.started_at if latest_run else None,
            last_run_status=latest_run.status if latest_run else None,
        )


def _percentage(count: int, total: int) -> float | None:
    return round(count / total * 100, 2) if total else None


def _fastest_growing(
    by_topic: dict[str, list[TopicPoint]],
) -> tuple[str | None, float | None]:
    """Compare each topic's last third of the window against its first third.

    Thirds rather than first-day-versus-last-day: a single day is noise, and
    "delivery complaints doubled" should mean a sustained shift, not one bad
    Tuesday. Topics with too few days to split are skipped rather than
    reported with a meaningless number.
    """
    best_topic: str | None = None
    best_change: float | None = None

    for topic, points in by_topic.items():
        if len(points) < 6:
            continue

        ordered = sorted(points, key=lambda point: point.metric_date)
        third = len(ordered) // 3
        if third == 0:
            continue

        early = sum(point.review_count for point in ordered[:third]) / third
        late = sum(point.review_count for point in ordered[-third:]) / third
        if early == 0:
            continue

        change = round((late - early) / early * 100, 2)
        if best_change is None or change > best_change:
            best_topic, best_change = topic, change

    return best_topic, best_change
