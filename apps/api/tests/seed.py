"""A small, fully-specified dataset for the API tests.

Hand-written rather than generated, and deliberately tiny, because every
assertion in the API tests quotes a number from here. Fourteen reviews whose
sentiment split you can verify by reading the file is worth more than ten
thousand whose totals you have to trust.

Two properties matter and are built in on purpose:

- **One review is a duplicate.** Endpoints that exclude duplicates return 13
  where naive ones return 14, so an accidental change is a failing test rather
  than a silently different dashboard.
- **The aggregate tables agree with the review rows.** They are separate tables
  in production, loaded from separate Parquet datasets, so a test fixture where
  they disagree would hide exactly the bug that matters.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from app.models import (
    Anomaly,
    Brand,
    CountryMetric,
    DailyBrandMetric,
    DailyTopicMetric,
    DataQualityResult,
    LanguageDistribution,
    PipelineRun,
    PipelineStageRun,
    Review,
    ReviewDateBounds,
    ReviewTopic,
    SentimentTrend,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: Fixed ids so tests can address rows directly without a lookup query.
AURORA_ID = uuid.UUID("11111111-1111-5111-8111-111111111111")
NIMBUS_ID = uuid.UUID("22222222-2222-5222-8222-222222222222")
RUN_ID = uuid.UUID("33333333-3333-5333-8333-333333333333")

BASE_DATE = date(2026, 6, 1)
BASE_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

#: (brand, offset, rating, sentiment, language, country, topic, duplicate?)
_REVIEWS: tuple[tuple[uuid.UUID, int, int, str, str, str, str, bool], ...] = (
    (AURORA_ID, 0, 5, "positive", "en", "GB", "delivery", False),
    (AURORA_ID, 1, 4, "positive", "en", "GB", "price", False),
    (AURORA_ID, 2, 3, "neutral", "fr", "FR", "packaging", False),
    (AURORA_ID, 3, 2, "negative", "de", "DE", "delivery", False),
    (AURORA_ID, 4, 1, "negative", "en", "US", "delivery", False),
    (AURORA_ID, 5, 5, "positive", "es", "ES", "taste", False),
    (AURORA_ID, 6, 4, "positive", "en", "GB", "price", False),
    # The duplicate. Same text as the first review, marked rather than deleted.
    (AURORA_ID, 7, 5, "positive", "en", "GB", "delivery", True),
    (NIMBUS_ID, 0, 2, "negative", "en", "GB", "delivery", False),
    (NIMBUS_ID, 1, 1, "negative", "en", "US", "delivery", False),
    (NIMBUS_ID, 2, 3, "neutral", "pl", "PL", "refunds", False),
    (NIMBUS_ID, 3, 4, "positive", "en", "GB", "taste", False),
    (NIMBUS_ID, 4, 5, "positive", "hi", "IN", "packaging", False),
    (NIMBUS_ID, 5, 3, "neutral", "en", "GB", "price", False),
)

#: Counts derived from `_REVIEWS`, excluding the duplicate. Tests assert
#: against these rather than re-deriving them, so a change to the fixture
#: cannot silently move the expected values too.
NON_DUPLICATE_REVIEWS = 13
TOTAL_REVIEWS = 14
AURORA_NON_DUPLICATE = 7
NIMBUS_NON_DUPLICATE = 6


def seed_database(session: Session) -> None:
    """Populate every table the API reads."""
    session.add_all(
        [
            Brand(id=AURORA_ID, name="Aurora Foods", category="food"),
            Brand(id=NIMBUS_ID, name="Nimbus Drinks", category="drink"),
        ]
    )
    session.flush()

    _seed_run(session)
    _seed_reviews(session)
    _seed_aggregates(session)
    _seed_anomalies(session)

    session.add(
        ReviewDateBounds(
            id=1,
            earliest=BASE_DATE,
            latest=BASE_DATE + timedelta(days=7),
            review_count=TOTAL_REVIEWS,
            refreshed_at=BASE_TIME,
        )
    )


def _seed_run(session: Session) -> None:
    session.add(
        PipelineRun(
            id=RUN_ID,
            batch_id="01TESTBATCH",
            status="partial",
            started_at=BASE_TIME,
            completed_at=BASE_TIME + timedelta(seconds=30),
            duration_seconds=30.0,
            input_rows=20,
            output_rows=TOTAL_REVIEWS,
            failed_rows=6,
            quarantined_rows=6,
            duplicate_rows=1,
            rows_per_second=0.67,
            quality_score=91.5,
        )
    )
    session.flush()

    session.add_all(
        [
            PipelineStageRun(
                id=uuid.uuid4(),
                pipeline_run_id=RUN_ID,
                stage_name=name,
                status=status,
                started_at=BASE_TIME + timedelta(seconds=offset),
                completed_at=BASE_TIME + timedelta(seconds=offset + 10),
                duration_seconds=10.0,
                rows_in=rows_in,
                rows_out=rows_out,
                retry_count=retries,
            )
            for name, status, offset, rows_in, rows_out, retries in (
                ("ingestion", "success", 0, 20, 20, 0),
                ("validation", "partial", 10, 20, 14, 0),
                # A stage that succeeded on retry — the case that makes
                # `retry_count` worth storing.
                ("enrichment", "success", 20, 14, 14, 2),
            )
        ]
    )
    session.add_all(
        [
            DataQualityResult(
                id=uuid.uuid4(),
                pipeline_run_id=RUN_ID,
                batch_id="01TESTBATCH",
                rule_id=rule,
                check_name=rule.replace("_", " "),
                status="failed" if affected else "passed",
                severity="error",
                affected_rows=affected,
                score=91.5,
                recorded_at=BASE_TIME,
            )
            # `text_invalid` passed. Included on purpose: a report that lists
            # only failures cannot distinguish a clean rule from one that never
            # ran.
            for rule, affected in (
                ("rating_out_of_range", 4),
                ("brand_missing", 2),
                ("text_invalid", 0),
            )
        ]
    )


def _seed_reviews(session: Session) -> None:
    for index, (brand_id, offset, rating, sentiment, language, country, topic, dup) in enumerate(
        _REVIEWS
    ):
        review_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"review-{index}")
        session.add(
            Review(
                id=review_id,
                external_review_id=f"rev-{index:05d}",
                brand_id=brand_id,
                pipeline_run_id=RUN_ID,
                product="Test Product",
                source="web",
                country=country,
                rating=rating,
                original_text=f"Review number {index} about {topic}.",
                normalized_text=f"review number {index} about {topic}.",
                review_created_at=BASE_TIME + timedelta(days=offset),
                language=language,
                language_confidence=0.95,
                sentiment=sentiment,
                sentiment_score=0.8,
                sentiment_model_version="lexicon-v1",
                word_count=5,
                is_duplicate_of="rev-00000" if dup else None,
                processed_at=BASE_TIME,
            )
        )
        session.add(
            ReviewTopic(
                id=uuid.uuid4(),
                review_id=review_id,
                topic=topic,
                is_primary=True,
                score=0.9,
                matched_keywords=topic,
            )
        )
    session.flush()


def _seed_aggregates(session: Session) -> None:
    """Daily rows whose totals match the non-duplicate review counts."""
    for brand_id, total, negatives, positives in (
        (AURORA_ID, AURORA_NON_DUPLICATE, 2, 4),
        (NIMBUS_ID, NIMBUS_NON_DUPLICATE, 2, 2),
    ):
        session.add(
            DailyBrandMetric(
                id=uuid.uuid4(),
                brand_id=brand_id,
                metric_date=BASE_DATE,
                review_count=total,
                average_rating=3.4,
                positive_count=positives,
                neutral_count=total - negatives - positives,
                negative_count=negatives,
                positive_percentage=round(positives / total * 100, 2),
                negative_percentage=round(negatives / total * 100, 2),
                average_sentiment_score=0.6,
                country_count=3,
                language_count=2,
            )
        )
        session.add(
            SentimentTrend(
                id=uuid.uuid4(),
                brand_id=brand_id,
                metric_date=BASE_DATE,
                review_count=total,
                negative_count=negatives,
                negative_percentage=round(negatives / total * 100, 2),
                average_rating=3.4,
                average_sentiment_score=0.6,
                negative_percentage_7d=25.0,
                review_count_7d=6.5,
            )
        )

    # Enough days per topic that the fastest-growing calculation has thirds to
    # compare; it skips any topic with fewer than six points.
    for day in range(9):
        metric_date = BASE_DATE + timedelta(days=day)
        session.add_all(
            [
                DailyTopicMetric(
                    id=uuid.uuid4(),
                    brand_id=AURORA_ID,
                    metric_date=metric_date,
                    topic="delivery",
                    # Rising: 2 -> 10 across the window.
                    review_count=2 + day,
                    average_rating=2.5,
                    negative_count=1 + day,
                    negative_percentage=50.0,
                    average_sentiment_score=-0.2,
                ),
                DailyTopicMetric(
                    id=uuid.uuid4(),
                    brand_id=AURORA_ID,
                    metric_date=metric_date,
                    topic="price",
                    review_count=5,  # flat
                    average_rating=4.0,
                    negative_count=1,
                    negative_percentage=20.0,
                    average_sentiment_score=0.4,
                ),
            ]
        )

    session.add_all(
        [
            CountryMetric(
                id=uuid.uuid4(),
                metric_date=BASE_DATE,
                country=country,
                review_count=count,
                average_rating=3.5,
                negative_count=1,
                negative_percentage=round(100 / count, 2),
                brand_count=2,
            )
            for country, count in (("GB", 6), ("US", 2), ("FR", 1), ("DE", 1))
        ]
    )
    session.add_all(
        [
            LanguageDistribution(
                id=uuid.uuid4(),
                metric_date=BASE_DATE,
                language=language,
                review_count=count,
                average_confidence=0.95,
                negative_count=1,
                average_rating=3.5,
            )
            for language, count in (("en", 8), ("fr", 1), ("de", 1), ("es", 1))
        ]
    )


def _seed_anomalies(session: Session) -> None:
    session.add_all(
        [
            Anomaly(
                id=uuid.uuid4(),
                anomaly_key=key,
                brand_id=AURORA_ID,
                detected_date=BASE_DATE + timedelta(days=2),
                metric=metric,
                topic=topic,
                country=None,
                current_value=current,
                baseline_value=baseline,
                percentage_change=round((current - baseline) / baseline * 100, 2),
                z_score=z_score,
                review_count=12,
                severity=severity,
                explanation=f"Aurora Foods: {metric} rose from {baseline} to {current}.",
                detected_at=BASE_TIME,
            )
            for key, metric, topic, current, baseline, z_score, severity in (
                ("a:1", "review_volume", None, 20.0, 5.0, 4.5, "high"),
                ("a:2", "negative_sentiment_rate", "delivery", 45.0, 15.0, 2.2, "low"),
                ("a:3", "review_volume", "packaging", 14.0, 6.0, 3.1, "medium"),
            )
        ]
    )
