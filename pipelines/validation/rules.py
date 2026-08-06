"""Validation rules and the quarantine decision.

Follows the validation flow: required columns, data types, rating range,
timestamp, review text, duplicate id. A record failing any check is not
dropped — it is written to quarantine carrying its original values, the field
that failed, the rule that failed it and a human-readable reason.

Two design decisions worth stating:

**Every rule runs on every row.** We do not stop at the first failure. A record
with both an invalid rating and a broken date should report both, because the
person fixing the upstream feed needs the full list, not the first item.

**Rules are data, not control flow.** Each is a `ValidationRule` with an id, a
severity and a predicate, so the API can describe the rule set to users and the
dashboard can group quarantine reasons by `rule_id` without string-matching
error messages.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

import pandas as pd

from pipelines.common.domain import (
    EARLIEST_VALID_DATE,
    MAX_RATING,
    MAX_TEXT_LENGTH,
    MIN_RATING,
    MIN_TEXT_LENGTH,
    REQUIRED_INPUT_COLUMNS,
)
from pipelines.transformation.text import is_effectively_empty, normalize_text

# ISO 3166-1 alpha-2 shape. We check the format, not membership of the real
# list: rejecting a valid-looking code because our copy of the list is stale
# would be worse than accepting an occasional typo.
_COUNTRY_CODE = re.compile(r"^[A-Za-z]{2}$")

_EARLIEST = datetime.fromisoformat(EARLIEST_VALID_DATE).replace(tzinfo=UTC)


class RuleSeverity(StrEnum):
    """Whether breaking a rule quarantines the record or only annotates it."""

    #: The record cannot be trusted; it goes to quarantine.
    ERROR = "error"
    #: The record is usable but imperfect; it proceeds with a note.
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationRule:
    """One check applied to one field."""

    rule_id: str
    field: str
    description: str
    severity: RuleSeverity
    #: Returns an error message when the value is invalid, else None.
    check: Callable[[pd.Series], pd.Series]


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    """A single rule failing on a single row."""

    row_index: int
    rule_id: str
    field: str
    reason: str
    severity: RuleSeverity
    failed_value: str


# --- Vectorised checks ------------------------------------------------------
# Each returns a boolean Series that is True where the row is INVALID. They are
# vectorised rather than row-wise because validation runs over every ingested
# record, and `.apply()` on a million rows is roughly two orders of magnitude
# slower than the equivalent pandas operation.


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype("string").str.strip().isin(["", "None", "nan"]))


def _invalid_rating(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    # Non-integers such as "4.5" are invalid: a rating is a discrete choice.
    is_integral = numeric.notna() & (numeric % 1 == 0)
    return numeric.isna() | ~is_integral | (numeric < MIN_RATING) | (numeric > MAX_RATING)


def parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse a column of timestamps, returning NaT where unparseable.

    `format="mixed"` handles the several shapes real exports contain without
    silently accepting nonsense — anything genuinely unparseable becomes NaT
    and is caught by the rule below.
    """
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _invalid_timestamp(series: pd.Series) -> pd.Series:
    parsed = parse_timestamps(series)
    now = pd.Timestamp.now(tz=UTC)
    return parsed.isna() | (parsed < pd.Timestamp(_EARLIEST)) | (parsed > now)


def _invalid_text(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").map(normalize_text)
    too_short = normalized.str.len() < MIN_TEXT_LENGTH
    too_long = normalized.str.len() > MAX_TEXT_LENGTH
    empty = series.map(is_effectively_empty)
    return empty | too_short | too_long


def _invalid_country(series: pd.Series) -> pd.Series:
    # Missing country is acceptable; a malformed one is not.
    present = series.notna() & (series.astype("string").str.strip() != "")
    malformed = ~series.fillna("").astype("string").str.match(_COUNTRY_CODE.pattern, na=False)
    return present & malformed


RULES: Final[tuple[ValidationRule, ...]] = (
    ValidationRule(
        rule_id="review_id_missing",
        field="review_id",
        description="review_id must be present and non-empty",
        severity=RuleSeverity.ERROR,
        check=_is_blank,
    ),
    ValidationRule(
        rule_id="brand_missing",
        field="brand",
        description="brand must be present and non-empty",
        severity=RuleSeverity.ERROR,
        check=_is_blank,
    ),
    ValidationRule(
        rule_id="text_invalid",
        field="text",
        description=(
            f"text must be non-empty and between {MIN_TEXT_LENGTH} and "
            f"{MAX_TEXT_LENGTH} characters after normalisation"
        ),
        severity=RuleSeverity.ERROR,
        check=_invalid_text,
    ),
    ValidationRule(
        rule_id="rating_out_of_range",
        field="rating",
        description=f"rating must be a whole number between {MIN_RATING} and {MAX_RATING}",
        severity=RuleSeverity.ERROR,
        check=_invalid_rating,
    ),
    ValidationRule(
        rule_id="created_at_invalid",
        field="created_at",
        description=(
            f"created_at must be a parseable timestamp between {EARLIEST_VALID_DATE} and now"
        ),
        severity=RuleSeverity.ERROR,
        check=_invalid_timestamp,
    ),
    ValidationRule(
        rule_id="country_malformed",
        field="country",
        description="country, when present, must be a two-letter ISO 3166-1 alpha-2 code",
        severity=RuleSeverity.WARNING,
        check=_invalid_country,
    ),
)


def missing_required_columns(frame: pd.DataFrame) -> list[str]:
    """Return required columns absent from the frame.

    A missing *column* is a schema failure affecting the whole batch, not a
    per-row problem, so it is reported separately from row-level rules.
    """
    return [column for column in REQUIRED_INPUT_COLUMNS if column not in frame.columns]


def find_duplicate_review_ids(frame: pd.DataFrame) -> pd.Series:
    """Mark rows whose `review_id` already appeared earlier in the batch.

    `keep="first"` is deliberate: the first occurrence is kept as the canonical
    record and later copies are flagged. Marking all occurrences would discard
    the original along with its duplicates.
    """
    if "review_id" not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame["review_id"].duplicated(keep="first")


def _format_value(value: object) -> str:
    """Render the offending value for the quarantine record, truncated."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "<missing>"
    text = str(value)
    return text if len(text) <= 200 else f"{text[:197]}..."


def apply_rules(frame: pd.DataFrame) -> list[ValidationFailure]:
    """Run every rule over the frame and collect each failure.

    Returns one `ValidationFailure` per (row, rule) pair — a row breaking three
    rules produces three failures, so nothing about why it was rejected is
    lost.
    """
    failures: list[ValidationFailure] = []

    for rule in RULES:
        if rule.field not in frame.columns:
            continue
        invalid_mask = rule.check(frame[rule.field]).fillna(True)
        for row_index in frame.index[invalid_mask]:
            failures.append(
                ValidationFailure(
                    row_index=int(row_index),
                    rule_id=rule.rule_id,
                    field=rule.field,
                    reason=rule.description,
                    severity=rule.severity,
                    failed_value=_format_value(frame.at[row_index, rule.field]),
                )
            )

    duplicate_mask = find_duplicate_review_ids(frame)
    for row_index in frame.index[duplicate_mask]:
        failures.append(
            ValidationFailure(
                row_index=int(row_index),
                rule_id="review_id_duplicate",
                field="review_id",
                reason="review_id already appeared earlier in this batch",
                severity=RuleSeverity.ERROR,
                failed_value=_format_value(frame.at[row_index, "review_id"]),
            )
        )

    return failures
