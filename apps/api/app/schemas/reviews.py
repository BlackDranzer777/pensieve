"""Response models for the Review Explorer."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

ORM = ConfigDict(from_attributes=True)


class ReviewTopicOut(BaseModel):
    """A topic assigned to a review, with the words that triggered it."""

    model_config = ORM

    topic: str
    is_primary: bool
    score: float | None = None
    matched_keywords: str | None = None


class ReviewListItem(BaseModel):
    """A review as it appears in the table.

    `original_text` is included but `normalized_text` is not: the table shows
    what the customer wrote, and the cleaned form is only interesting when
    inspecting one review in detail.
    """

    model_config = ORM

    id: uuid.UUID
    external_review_id: str
    brand: str
    product: str | None
    country: str | None
    source: str | None
    rating: int | None
    original_text: str
    language: str | None
    sentiment: str | None
    sentiment_score: float | None
    primary_topic: str | None
    review_created_at: datetime
    is_duplicate: bool


class ReviewDetail(ReviewListItem):
    """One review in full, including how it was processed.

    The processing fields are part of the contract rather than debug output.
    "Why is this review marked negative?" is a question the dashboard must be
    able to answer, and `sentiment_model_version` plus the matched keywords are
    the answer.
    """

    model_config = ORM

    normalized_text: str | None
    language_confidence: float | None
    sentiment_model_version: str | None
    word_count: int | None
    is_duplicate_of: str | None
    processed_at: datetime | None
    topics: list[ReviewTopicOut] = []


class ReviewFacets(BaseModel):
    """The values the filter dropdowns should offer.

    Derived from the data rather than hardcoded, so a filter can never offer an
    option that matches nothing — or omit one that exists.
    """

    brands: list[str]
    countries: list[str]
    languages: list[str]
    sentiments: list[str]
    topics: list[str]
    sources: list[str]
