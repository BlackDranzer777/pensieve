"""Pipeline runs, per-stage detail and data-quality results.

These tables answer "can I trust this week's numbers?" — which is a different
question from "what do the numbers say", and needs its own data. They are
append-only: overwriting last week's quality score makes the trend, and
therefore the whole point, unanswerable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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


class PipelineRun(Base, UUIDPrimaryKey, LoadedAt):
    """One end-to-end execution of the pipeline."""

    __tablename__ = "pipeline_runs"

    # The ingestion batch this run processed. Present so a dashboard row can be
    # traced back to the exact Bronze partition on disk.
    batch_id: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    input_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    output_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Quarantined and duplicate rows are counted separately because they are
    # different events: one is data we rejected, the other is data we accepted
    # but must not count twice. Merging them hides which one is growing.
    quarantined_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duplicate_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    rows_per_second: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)

    stages: Mapped[list[PipelineStageRun]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="PipelineStageRun.started_at"
    )
    quality_results: Mapped[list[DataQualityResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_pipeline_runs_started_at", "started_at"),)


class PipelineStageRun(Base, UUIDPrimaryKey):
    """One stage within a run — ingestion, validation, enrichment, and so on.

    Stage-level timing is what turns "the run took 4 minutes" into something
    actionable. Without it, a slow run is a mystery; with it, you can see that
    enrichment took 90% of the time and everything else is noise.
    """

    __tablename__ = "pipeline_stage_runs"

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    rows_in: Mapped[int | None] = mapped_column(Integer)
    rows_out: Mapped[int | None] = mapped_column(Integer)
    processed_rows: Mapped[int | None] = mapped_column(Integer)
    # A stage that succeeded on its third attempt is not the same as one that
    # succeeded first time, and only one of them is a reliability problem.
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    run: Mapped[PipelineRun] = relationship(back_populates="stages")


class DataQualityResult(Base, UUIDPrimaryKey):
    """The outcome of one validation rule within one run.

    A row per rule, not per run. "Quality score 95.89" tells you nothing about
    what to fix; "rating_out_of_range rejected 496 rows" tells you exactly
    where to look.
    """

    __tablename__ = "data_quality_results"

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[str | None] = mapped_column(String(50))
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    check_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    affected_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    score: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[PipelineRun] = relationship(back_populates="quality_results")
