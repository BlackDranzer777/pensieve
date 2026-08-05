"""Response schemas shared across endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PageMeta(BaseModel):
    """Pagination metadata returned alongside every paginated collection."""

    page: int = Field(description="Current page, 1-indexed")
    page_size: int = Field(description="Items requested per page")
    total_items: int = Field(description="Total items matching the filters")
    total_pages: int = Field(description="Total pages available")
    has_next: bool
    has_previous: bool

    @classmethod
    def build(cls, page: int, page_size: int, total_items: int) -> PageMeta:
        total_pages = max(1, -(-total_items // page_size))  # ceiling division
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class Page[T](BaseModel):
    """A single page of results.

    Every list endpoint returns this envelope so the frontend has one shape to
    handle rather than a bespoke response per resource.
    """

    items: list[T]
    meta: PageMeta


class HealthCheck(BaseModel):
    """Status of one dependency."""

    name: str
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    """Service health.

    Returns HTTP 200 whenever the process is alive, with per-dependency detail
    in `checks`. A degraded database therefore shows up as `status="degraded"`
    rather than an opaque 503 — the dashboard can then render a banner instead
    of a blank page.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: Literal["ok", "degraded"]
    version: str
    environment: str
    processing_version: str
    timestamp: datetime
    checks: list[HealthCheck]
