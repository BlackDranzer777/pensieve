"""Shared FastAPI dependencies.

Pagination and date filtering are declared once here rather than repeated as
query parameters on a dozen endpoints. Beyond saving typing, it means the
limits are enforced in one place: an endpoint cannot accidentally allow
`page_size=100000` because someone copied the wrong default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from app.core.errors import ValidationFailedError

#: Hard ceiling on page size. Present so a single request cannot ask for the
#: whole table and turn a dashboard into a denial of service.
MAX_PAGE_SIZE = 200

#: How far back a range query may reach without an explicit `date_from`.
DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True, slots=True)
class Pagination:
    """One page of results, already converted to LIMIT/OFFSET."""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def get_pagination(
    page: Annotated[int, Query(ge=1, description="1-indexed page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Items per page")] = 25,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive date window. Either end may be open."""

    date_from: date | None
    date_to: date | None


def get_date_range(
    date_from: Annotated[date | None, Query(description="Inclusive start date")] = None,
    date_to: Annotated[date | None, Query(description="Inclusive end date")] = None,
) -> DateRange:
    """Validate the window before it reaches SQL.

    An inverted range is silently empty in SQL, which looks identical to "there
    is no data" on a dashboard. Rejecting it here turns a confusing empty chart
    into a message that says what is wrong.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValidationFailedError(
            "date_from must not be after date_to",
            details={"date_from": str(date_from), "date_to": str(date_to)},
        )
    return DateRange(date_from=date_from, date_to=date_to)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
DateRangeDep = Annotated[DateRange, Depends(get_date_range)]
