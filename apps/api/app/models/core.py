"""Brands, reviews and their topic assignments.

These are the review-level tables the Review Explorer reads. Everything here
comes from the Silver layer; the aggregate tables in `analytics.py` come from
Gold.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, LoadedAt, UUIDPrimaryKey
from pipelines.common.domain import MAX_RATING, MIN_RATING


class Brand(Base, UUIDPrimaryKey, LoadedAt):
    """A brand. Referenced by reviews and every aggregate table.

    Brands arrive as free text in the source data, so the loader upserts them
    by name. That makes `name` the real natural key and the uniqueness
    constraint below the thing that stops two spellings becoming two brands.
    """

    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reviews: Mapped[list[Review]] = relationship(back_populates="brand")


class Review(Base, UUIDPrimaryKey, LoadedAt):
    """One enriched review, loaded from Silver.

    `external_review_id` is the id the source system gave us (`rev-00000123`).
    It is kept separate from the uuid primary key because it is *their*
    identifier, not ours: it is not guaranteed unique across sources, it can be
    reused, and letting it become the PK would mean a second data source could
    silently overwrite rows from the first.
    """

    __tablename__ = "reviews"

    external_review_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )

    # --- Source fields ----------------------------------------------------
    product: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    review_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Enrichment -------------------------------------------------------
    language: Mapped[str | None] = mapped_column(String(20), index=True)
    language_confidence: Mapped[float | None] = mapped_column(Float)
    sentiment: Mapped[str | None] = mapped_column(String(20), index=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    # Which model produced `sentiment`. Without this a lexicon-scored row and a
    # transformer-scored row are indistinguishable once they are in the same
    # table, and any comparison across them is silently meaningless.
    sentiment_model_version: Mapped[str | None] = mapped_column(String(120))
    word_count: Mapped[int | None] = mapped_column(Integer)

    # --- Deduplication ----------------------------------------------------
    # Duplicates are *marked*, never deleted: the review genuinely arrived and
    # still belongs in the Review Explorer. Aggregates exclude it by filtering
    # on this column, exactly as the Gold SQL does.
    is_duplicate_of: Mapped[str | None] = mapped_column(String(100))

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    brand: Mapped[Brand] = relationship(back_populates="reviews")
    topics: Mapped[list[ReviewTopic]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"rating IS NULL OR (rating >= {MIN_RATING} AND rating <= {MAX_RATING})",
            name="rating_range",
        ),
        # The Review Explorer filters on brand and sorts by date, so the
        # composite index matches the actual query rather than forcing Postgres
        # to combine two single-column indexes.
        Index("ix_reviews_brand_id_review_created_at", "brand_id", "review_created_at"),
        Index("ix_reviews_review_created_at", "review_created_at"),
        # Partial index: aggregate queries always want non-duplicates, and this
        # keeps the index to the ~58% of rows they actually read.
        Index(
            "ix_reviews_not_duplicate",
            "brand_id",
            "review_created_at",
            postgresql_where=(is_duplicate_of.is_(None)),
        ),
        # Trigram index for the Review Explorer's free-text search. Without it
        # `original_text ILIKE '%late%'` cannot use an index at all and becomes
        # a sequential scan of every review.
        #
        # Declared here rather than as a raw `op.execute` in the migration:
        # `alembic check` compares the database against this metadata, so an
        # index it cannot see is one it generates a migration to **drop**.
        # The `pg_trgm` extension itself still has to be created by hand — that
        # part autogenerate genuinely cannot model.
        Index(
            "ix_reviews_text_trgm",
            "original_text",
            postgresql_using="gin",
            postgresql_ops={"original_text": "gin_trgm_ops"},
        ),
    )


class ReviewTopic(Base, UUIDPrimaryKey):
    """A topic assigned to a review, with the evidence for the assignment.

    A row per topic rather than a column on `reviews` because a review can be
    about several things at once — "arrived late and the box was crushed" is
    delivery *and* packaging. Collapsing that to one column loses half of every
    such complaint.

    `matched_keywords` is what makes the classification auditable: anyone can
    see precisely which words triggered it and disagree with a specific rule
    rather than distrusting the whole feature.
    """

    __tablename__ = "review_topics"

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    score: Mapped[float | None] = mapped_column(Float)
    matched_keywords: Mapped[str | None] = mapped_column(Text)

    review: Mapped[Review] = relationship(back_populates="topics")

    __table_args__ = (Index("ix_review_topics_topic_is_primary", "topic", "is_primary"),)


class ReviewDateBounds(Base):
    """Cached min/max review dates, refreshed by the loader.

    A single row. The Overview page needs the data's date range on every load,
    and `SELECT min(review_created_at), max(...) FROM reviews` scans the table
    to produce two values that only change when a load runs.
    """

    __tablename__ = "review_date_bounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    earliest: Mapped[date | None] = mapped_column(Date)
    latest: Mapped[date | None] = mapped_column(Date)
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)
