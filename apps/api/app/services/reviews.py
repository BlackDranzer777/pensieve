"""Business logic for the Review Explorer."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import NotFoundError
from app.repositories.reviews import ReviewRepository
from app.schemas.common import Page, PageMeta
from app.schemas.reviews import ReviewDetail, ReviewFacets, ReviewListItem

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.api.deps import DateRange, Pagination


class ReviewService:
    def __init__(self, session: Session) -> None:
        self._repo = ReviewRepository(session)

    def search(
        self,
        pagination: Pagination,
        *,
        window: DateRange,
        brands: Sequence[str] | None = None,
        countries: Sequence[str] | None = None,
        languages: Sequence[str] | None = None,
        sentiments: Sequence[str] | None = None,
        sources: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        ratings: Sequence[int] | None = None,
        search: str | None = None,
        include_duplicates: bool = False,
        sort: str = "review_created_at",
        order: str = "desc",
    ) -> Page[ReviewListItem]:
        items, total = self._repo.search(
            pagination,
            window=window,
            brands=brands,
            countries=countries,
            languages=languages,
            sentiments=sentiments,
            sources=sources,
            topics=topics,
            ratings=ratings,
            search=search,
            include_duplicates=include_duplicates,
            sort=sort,
            order=order,
        )
        return Page[ReviewListItem](
            items=[ReviewListItem(**item) for item in items],
            meta=PageMeta.build(pagination.page, pagination.page_size, total),
        )

    def by_id(self, review_id: uuid.UUID) -> ReviewDetail:
        detail = self._repo.by_id(review_id)
        if detail is None:
            raise NotFoundError(f"Review '{review_id}' was not found.")
        return ReviewDetail(**detail)

    def facets(self) -> ReviewFacets:
        return ReviewFacets(**self._repo.facets())
