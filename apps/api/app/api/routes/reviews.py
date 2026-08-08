"""Review Explorer endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DateRangeDep, PaginationDep
from app.database.session import get_db_session
from app.repositories.reviews import SORTABLE
from app.schemas.common import Page
from app.schemas.reviews import ReviewDetail, ReviewFacets, ReviewListItem
from app.services.reviews import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])

SessionDep = Annotated[Session, Depends(get_db_session)]


def _service(session: SessionDep) -> ReviewService:
    return ReviewService(session)


ServiceDep = Annotated[ReviewService, Depends(_service)]


@router.get("", response_model=Page[ReviewListItem], summary="Search and filter reviews")
def list_reviews(
    service: ServiceDep,
    window: DateRangeDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(description="Free-text search over review text")] = None,
    brand: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    country: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    language: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    sentiment: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    source: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    topic: Annotated[list[str] | None, Query(description="Repeatable")] = None,
    rating: Annotated[list[int] | None, Query(ge=1, le=5, description="Repeatable")] = None,
    include_duplicates: Annotated[
        bool,
        Query(
            description=(
                "Include reviews marked as duplicates. Excluded by default so "
                "the table agrees with the aggregate pages."
            )
        ),
    ] = False,
    sort: Annotated[str, Query(description=f"One of: {', '.join(SORTABLE)}")] = (
        "review_created_at"
    ),
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Page[ReviewListItem]:
    """One page of reviews.

    Duplicates are hidden by default. Showing them would make this table
    disagree with every aggregate on the site, since Gold excludes them — and
    "the numbers do not add up" is the fastest way to lose trust in a
    dashboard. The flag exists because inspecting them is sometimes the point.
    """
    return service.search(
        pagination,
        window=window,
        brands=brand,
        countries=country,
        languages=language,
        sentiments=sentiment,
        sources=source,
        topics=topic,
        ratings=rating,
        search=q,
        include_duplicates=include_duplicates,
        sort=sort,
        order=order,
    )


@router.get("/facets", response_model=ReviewFacets, summary="Filter options")
def review_facets(service: ServiceDep) -> ReviewFacets:
    """The values the filter dropdowns should offer, read from the data.

    Declared before `/{review_id}` so the literal path wins — otherwise
    "facets" is parsed as a review id and every request 422s.
    """
    return service.facets()


@router.get("/{review_id}", response_model=ReviewDetail, summary="One review in full")
def get_review(service: ServiceDep, review_id: uuid.UUID) -> ReviewDetail:
    return service.by_id(review_id)
