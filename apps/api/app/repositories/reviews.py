"""Queries for the Review Explorer.

The only place in the API that reads `reviews` row by row. Everything here is
designed around the indexes declared on the model — the composite
`(brand_id, review_created_at)` for the common filter-and-sort, and the GIN
trigram index for free-text search.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models import Brand, Review, ReviewTopic

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.api.deps import DateRange, Pagination

#: Columns a client may sort by. An allow-list, not a passthrough: interpolating
#: a user-supplied column name into ORDER BY is a SQL injection vector, and
#: sorting by an unindexed column is a performance one.
SORTABLE = {
    "review_created_at": Review.review_created_at,
    "rating": Review.rating,
    "sentiment_score": Review.sentiment_score,
    "brand": Brand.name,
}

#: Below this length a trigram index cannot help, and the query degrades to a
#: full scan. Postgres needs at least three characters to form one trigram.
MIN_SEARCH_LENGTH = 3


class ReviewRepository:
    """Reads individual reviews."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _filtered(
        self,
        *,
        window: DateRange,
        brands: Sequence[str] | None,
        countries: Sequence[str] | None,
        languages: Sequence[str] | None,
        sentiments: Sequence[str] | None,
        sources: Sequence[str] | None,
        topics: Sequence[str] | None,
        ratings: Sequence[int] | None,
        search: str | None,
        include_duplicates: bool,
    ) -> Select[Any]:
        """Build the filtered query shared by the list and count paths.

        One builder for both so a filter can never apply to the rows returned
        but not to the total — which shows a table of 10 items above the words
        "1,284 results".
        """
        statement = select(Review).join(Brand, Brand.id == Review.brand_id)

        if window.date_from is not None:
            statement = statement.where(Review.review_created_at >= window.date_from)
        if window.date_to is not None:
            statement = statement.where(Review.review_created_at <= window.date_to)
        if brands:
            statement = statement.where(Brand.name.in_(brands))
        if countries:
            statement = statement.where(Review.country.in_(countries))
        if languages:
            statement = statement.where(Review.language.in_(languages))
        if sentiments:
            statement = statement.where(Review.sentiment.in_(sentiments))
        if sources:
            statement = statement.where(Review.source.in_(sources))
        if ratings:
            statement = statement.where(Review.rating.in_(ratings))
        if not include_duplicates:
            statement = statement.where(Review.is_duplicate_of.is_(None))

        if topics:
            # EXISTS rather than a join: a review with three matching topics
            # would otherwise appear three times, and the total would be wrong
            # in a way that only shows up with multi-topic filters.
            statement = statement.where(
                select(ReviewTopic.id)
                .where(ReviewTopic.review_id == Review.id, ReviewTopic.topic.in_(topics))
                .exists()
            )

        if search and len(search.strip()) >= MIN_SEARCH_LENGTH:
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(Review.original_text.ilike(pattern), Review.product.ilike(pattern))
            )

        return statement

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
    ) -> tuple[list[dict[str, Any]], int]:
        """One page of reviews plus the total matching the same filters."""
        base = self._filtered(
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
        )

        total = self._session.scalar(select(func.count()).select_from(base.subquery())) or 0

        column = SORTABLE.get(sort, Review.review_created_at)
        ordering = column.desc() if order == "desc" else column.asc()

        statement = (
            base.add_columns(Brand.name)
            .options(selectinload(Review.topics))
            # A stable tiebreaker. Without one, two reviews sharing a timestamp
            # can swap places between page 1 and page 2, so a row is shown
            # twice and another never appears.
            .order_by(ordering, Review.id)
            .limit(pagination.limit)
            .offset(pagination.offset)
        )

        items = [
            _to_item(review, brand_name) for review, brand_name in self._session.execute(statement)
        ]
        return items, total

    def by_id(self, review_id: uuid.UUID) -> dict[str, Any] | None:
        statement = (
            select(Review, Brand.name)
            .join(Brand, Brand.id == Review.brand_id)
            .options(selectinload(Review.topics))
            .where(Review.id == review_id)
        )
        row = self._session.execute(statement).first()
        if row is None:
            return None

        review, brand_name = row
        detail = _to_item(review, brand_name)
        detail.update(
            {
                "normalized_text": review.normalized_text,
                "language_confidence": review.language_confidence,
                "sentiment_model_version": review.sentiment_model_version,
                "word_count": review.word_count,
                "is_duplicate_of": review.is_duplicate_of,
                "processed_at": review.processed_at,
                "topics": sorted(
                    review.topics, key=lambda topic: (not topic.is_primary, topic.topic)
                ),
            }
        )
        return detail

    def facets(self) -> dict[str, list[str]]:
        """Distinct values for the filter dropdowns.

        Read from the data so a filter cannot offer an option that matches
        nothing. Cheap because every column involved is indexed and the
        cardinalities are tiny — five brands, eight languages.
        """

        def distinct(column: Any) -> list[str]:
            rows = self._session.scalars(
                select(column).where(column.is_not(None)).distinct().order_by(column)
            )
            return [str(value) for value in rows]

        return {
            "brands": distinct(Brand.name),
            "countries": distinct(Review.country),
            "languages": distinct(Review.language),
            "sentiments": distinct(Review.sentiment),
            "sources": distinct(Review.source),
            "topics": distinct(ReviewTopic.topic),
        }


def _to_item(review: Review, brand_name: str) -> dict[str, Any]:
    """Flatten a Review row into the shape the API returns."""
    primary = next((topic.topic for topic in review.topics if topic.is_primary), None)
    return {
        "id": review.id,
        "external_review_id": review.external_review_id,
        "brand": brand_name,
        "product": review.product,
        "country": review.country,
        "source": review.source,
        "rating": review.rating,
        "original_text": review.original_text,
        "language": review.language,
        "sentiment": review.sentiment,
        "sentiment_score": review.sentiment_score,
        "primary_topic": primary,
        "review_created_at": review.review_created_at,
        "is_duplicate": review.is_duplicate_of is not None,
    }
