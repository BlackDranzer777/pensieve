"""The data-quality score.

One number, 0-100, summarising how trustworthy a batch is. Its whole value
depends on being *explainable*, so the formula is a handful of constants in one
place rather than logic scattered across the pipeline, and every component is
returned alongside the score so the dashboard can show the arithmetic.

    quality_score = 100
                  - 40 x invalid_rate
                  - 20 x duplicate_rate
                  - 25 x missing_required_rate
                  - 15 x unparseable_date_rate

clamped to [0, 100].

**Why these weights.** Invalid records are weighted heaviest because they are
data we cannot use at all. Missing required values come next: the record exists
but is incomplete. Duplicates are less severe — the information is present,
merely repeated, and deduplication handles it. Unparseable dates are last
because a review with a broken timestamp still carries usable sentiment; it
just cannot be placed on a trend line.

The weights are a judgement call, not a law. `QUALITY_SCORE_VERSION` is stored
with every score so that changing them does not silently reinterpret history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from pipelines.common.domain import QUALITY_SCORE_VERSION, REQUIRED_INPUT_COLUMNS
from pipelines.validation.rules import (
    RuleSeverity,
    ValidationFailure,
    find_duplicate_review_ids,
    parse_timestamps,
)

WEIGHT_INVALID: Final[float] = 40.0
WEIGHT_DUPLICATE: Final[float] = 20.0
WEIGHT_MISSING_REQUIRED: Final[float] = 25.0
WEIGHT_UNPARSEABLE_DATE: Final[float] = 15.0

MAX_SCORE: Final[float] = 100.0


@dataclass(frozen=True, slots=True)
class QualityComponent:
    """One penalty term, kept intact so the dashboard can show the working."""

    name: str
    affected_records: int
    rate: float
    weight: float

    @property
    def penalty(self) -> float:
        return self.weight * self.rate


@dataclass(frozen=True, slots=True)
class QualityReport:
    """The score plus everything needed to explain it."""

    total_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    missing_required_cells: int
    unparseable_dates: int
    score: float
    version: str = QUALITY_SCORE_VERSION
    components: tuple[QualityComponent, ...] = field(default_factory=tuple)
    #: Failure counts keyed by rule id, for the quarantine-reasons breakdown.
    failures_by_rule: dict[str, int] = field(default_factory=dict)

    @property
    def validity_rate(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.valid_records / self.total_records

    def explain(self) -> str:
        """A human-readable derivation of the score."""
        lines = [
            f"Quality score: {self.score:.1f} / 100  (formula v{self.version})",
            "  100.0  base",
        ]
        lines.extend(
            f"  -{component.penalty:5.1f}  {component.name}: "
            f"{component.affected_records:,} of {self.total_records:,} "
            f"({component.rate:.1%} x weight {component.weight:g})"
            for component in self.components
        )
        lines.append(f"  ={self.score:6.1f}")
        return "\n".join(lines)


def _rate(count: int, total: int) -> float:
    return 0.0 if total == 0 else count / total


def calculate_quality(
    frame: pd.DataFrame,
    failures: list[ValidationFailure],
) -> QualityReport:
    """Compute the quality report for one batch.

    Args:
        frame: The raw records as ingested.
        failures: Every rule failure found by `apply_rules`.

    An empty batch scores 0 rather than 100. A perfect score for a batch
    containing nothing would be actively misleading on a dashboard.
    """
    total = len(frame)
    if total == 0:
        return QualityReport(
            total_records=0,
            valid_records=0,
            invalid_records=0,
            duplicate_records=0,
            missing_required_cells=0,
            unparseable_dates=0,
            score=0.0,
        )

    # A record is invalid if any ERROR-severity rule failed on it. Warnings
    # annotate without disqualifying.
    invalid_rows = {f.row_index for f in failures if f.severity is RuleSeverity.ERROR}
    duplicate_rows = set(frame.index[find_duplicate_review_ids(frame)].tolist())

    # Duplicates are already counted among the invalid rows; the penalty is
    # separate but the "valid" count must not subtract them twice.
    invalid_count = len(invalid_rows)
    duplicate_count = len(duplicate_rows)
    valid_count = total - invalid_count

    missing_cells = 0
    for column in REQUIRED_INPUT_COLUMNS:
        if column not in frame.columns:
            missing_cells += total  # the whole column is absent
            continue
        series = frame[column].astype("string")
        missing_cells += int((series.isna() | (series.str.strip() == "")).sum())
    required_cell_total = total * len(REQUIRED_INPUT_COLUMNS)

    unparseable_dates = (
        int(parse_timestamps(frame["created_at"]).isna().sum())
        if "created_at" in frame.columns
        else total
    )

    components = (
        QualityComponent(
            "invalid records", invalid_count, _rate(invalid_count, total), WEIGHT_INVALID
        ),
        QualityComponent(
            "duplicate records", duplicate_count, _rate(duplicate_count, total), WEIGHT_DUPLICATE
        ),
        QualityComponent(
            "missing required values",
            missing_cells,
            _rate(missing_cells, required_cell_total),
            WEIGHT_MISSING_REQUIRED,
        ),
        QualityComponent(
            "unparseable dates",
            unparseable_dates,
            _rate(unparseable_dates, total),
            WEIGHT_UNPARSEABLE_DATE,
        ),
    )

    score = MAX_SCORE - sum(component.penalty for component in components)
    score = max(0.0, min(MAX_SCORE, score))

    failures_by_rule: dict[str, int] = {}
    for failure in failures:
        failures_by_rule[failure.rule_id] = failures_by_rule.get(failure.rule_id, 0) + 1

    return QualityReport(
        total_records=total,
        valid_records=valid_count,
        invalid_records=invalid_count,
        duplicate_records=duplicate_count,
        missing_required_cells=missing_cells,
        unparseable_dates=unparseable_dates,
        score=round(score, 2),
        components=components,
        failures_by_rule=dict(sorted(failures_by_rule.items(), key=lambda kv: -kv[1])),
    )
