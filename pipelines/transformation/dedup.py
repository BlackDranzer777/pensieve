"""Deduplication.

Two records can be duplicates in two different senses, and conflating them
loses information:

**Exact id duplicates** — the same `review_id` twice. Almost always a
re-delivered feed or a double-submitted form. Caught during validation and
quarantined, because a repeated primary key means the upstream system has a
problem worth telling someone about.

**Content duplicates** — different ids, identical text from the same brand.
Typically a customer submitting the same review twice, or one review syndicated
across sources. These are *not* an upstream fault, so they are kept in Silver
and marked with `is_duplicate_of` pointing at the record they repeat.

Marking rather than deleting matters: "how many people complained" and "how
many complaints were filed" are different questions, and the dashboard should
be able to answer both.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pandas as pd

from pipelines.common.logging import get_logger
from pipelines.transformation.text import normalize_text

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """Outcome of the deduplication pass."""

    frame: pd.DataFrame
    exact_duplicates: int
    content_duplicates: int

    @property
    def total_duplicates(self) -> int:
        return self.exact_duplicates + self.content_duplicates


def content_fingerprint(brand: str | None, text: str | None) -> str:
    """A stable hash of normalised brand + text.

    Normalising first is what makes this work: `"  GREAT  service!!! "` and
    `"<p>GREAT service!!</p>"` produce the same fingerprint, because the
    difference between them is formatting, not content.

    Brand is included so two brands receiving genuinely similar generic
    feedback ("Great product") are not collapsed into one review.
    """
    normalized_brand = (brand or "").strip().casefold()
    normalized_text = normalize_text(text).casefold()
    payload = f"{normalized_brand}\x1f{normalized_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def add_content_fingerprint(frame: pd.DataFrame) -> pd.DataFrame:
    """Add a `content_fingerprint` column."""
    result = frame.copy()
    brands = result["brand"] if "brand" in result.columns else pd.Series("", index=result.index)
    texts = result["text"] if "text" in result.columns else pd.Series("", index=result.index)
    result["content_fingerprint"] = [
        content_fingerprint(brand, text)
        for brand, text in zip(brands.fillna(""), texts.fillna(""), strict=True)
    ]
    return result


def mark_duplicates(frame: pd.DataFrame) -> DeduplicationResult:
    """Flag content duplicates without removing them.

    Adds two columns:
        `content_fingerprint` - hash of normalised brand + text
        `is_duplicate_of`     - review_id of the first record with that
                                fingerprint, or NA for the first occurrence

    The *first* occurrence by position is treated as canonical, so ordering the
    frame by `created_at` before calling this makes the earliest review the
    original — which is the intuitive reading.
    """
    if frame.empty:
        result = frame.copy()
        result["content_fingerprint"] = pd.Series(dtype="string")
        result["is_duplicate_of"] = pd.Series(dtype="string")
        return DeduplicationResult(frame=result, exact_duplicates=0, content_duplicates=0)

    result = add_content_fingerprint(frame)

    # Map each fingerprint to the review_id of its first occurrence.
    first_occurrence = (
        result.drop_duplicates(subset="content_fingerprint", keep="first")
        .set_index("content_fingerprint")["review_id"]
        .to_dict()
    )
    is_repeat = result.duplicated(subset="content_fingerprint", keep="first")
    result["is_duplicate_of"] = (
        result["content_fingerprint"].map(first_occurrence).where(is_repeat, other=pd.NA)
    ).astype("string")

    exact_duplicates = (
        int(result["review_id"].duplicated(keep="first").sum())
        if "review_id" in result.columns
        else 0
    )
    content_duplicates = int(is_repeat.sum())

    log.info(
        "duplicates_marked",
        rows=len(result),
        exact_id_duplicates=exact_duplicates,
        content_duplicates=content_duplicates,
    )
    return DeduplicationResult(
        frame=result,
        exact_duplicates=exact_duplicates,
        content_duplicates=content_duplicates,
    )


def drop_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only canonical records, dropping marked content duplicates.

    Used by aggregations that must not double-count. Review-level views use
    the marked frame instead so nothing disappears from the explorer.
    """
    if "is_duplicate_of" not in frame.columns:
        return frame
    return frame[frame["is_duplicate_of"].isna()].copy()
