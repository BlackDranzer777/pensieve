"""Declarative base and the conventions every table follows.

Two decisions apply across the whole schema:

**UUID primary keys.** The ERD specifies them, and they suit a pipeline that
loads rows in bulk: the loader can generate ids client-side without a round
trip to a sequence, and re-running a load against a different database cannot
produce colliding integers that quietly merge two datasets.

**Naming convention for constraints.** Without it, Alembic autogenerate emits
migrations that try to drop unnamed indexes and constraints it cannot identify,
which fails on the second migration rather than the first — an unpleasant
surprise well after you have stopped suspecting the setup.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: PostgreSQL identifiers are capped at 63 characters. These templates stay
#: within that for every table name used here.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    """Mixin providing the `id` column the ERD specifies on every table."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class LoadedAt:
    """Mixin recording when the loader wrote a row.

    Distinct from any business timestamp on the row. When a dashboard number
    looks wrong, the first question is "how old is this?", and answering it
    should not require correlating against pipeline logs.
    """

    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
