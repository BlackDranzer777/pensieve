"""Overview, brands, trends and anomaly endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DateRangeDep, PaginationDep
from app.database.session import get_db_session
from app.schemas.analytics import (
    AnomalyOut,
    BrandComparison,
    BrandSummary,
    CountryPoint,
    LanguagePoint,
    Overview,
    SentimentTrends,
    TopicTrends,
)
from app.schemas.common import Page, PageMeta
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_db_session)]


def _service(session: SessionDep) -> AnalyticsService:
    return AnalyticsService(session)


ServiceDep = Annotated[AnalyticsService, Depends(_service)]


@router.get("/overview", response_model=Overview, summary="Executive overview")
def get_overview(service: ServiceDep, window: DateRangeDep) -> Overview:
    """Every number on the landing page, in one request.

    One endpoint rather than six so the page has a single loading state
    instead of six independent chances to stall.
    """
    return service.overview(window)


@router.get("/brands", response_model=list[BrandSummary], summary="Brand totals")
def list_brands(service: ServiceDep, window: DateRangeDep) -> list[BrandSummary]:
    return service.brands(window)


@router.get(
    "/brands/comparison",
    response_model=BrandComparison,
    summary="Brand comparison with the window echoed back",
)
def compare_brands(service: ServiceDep, window: DateRangeDep) -> BrandComparison:
    return service.brand_comparison(window)


@router.get("/countries", response_model=list[CountryPoint], summary="Totals by country")
def list_countries(service: ServiceDep, window: DateRangeDep) -> list[CountryPoint]:
    return service.countries(window)


@router.get("/languages", response_model=list[LanguagePoint], summary="Language mix")
def list_languages(service: ServiceDep, window: DateRangeDep) -> list[LanguagePoint]:
    return service.languages(window)


@router.get(
    "/trends/sentiment",
    response_model=SentimentTrends,
    summary="Sentiment over time, per brand, with trailing baselines",
)
def sentiment_trends(service: ServiceDep, window: DateRangeDep) -> SentimentTrends:
    return service.sentiment_trends(window)


@router.get(
    "/trends/topics",
    response_model=TopicTrends,
    summary="Topic volume over time, with the fastest-growing topic",
)
def topic_trends(service: ServiceDep, window: DateRangeDep) -> TopicTrends:
    return service.topic_trends(window)


@router.get(
    "/anomalies",
    response_model=Page[AnomalyOut],
    summary="Detected anomalies, strongest first",
)
def list_anomalies(
    service: ServiceDep,
    window: DateRangeDep,
    pagination: PaginationDep,
    severity: Annotated[
        list[str] | None, Query(description="Filter by severity; repeatable")
    ] = None,
    metric: Annotated[str | None, Query(description="Filter to one metric")] = None,
) -> Page[AnomalyOut]:
    items, total = service.anomalies(
        window,
        severity=severity,
        metric=metric,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[AnomalyOut](
        items=items,
        meta=PageMeta.build(pagination.page, pagination.page_size, total),
    )
