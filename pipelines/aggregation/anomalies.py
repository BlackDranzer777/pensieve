"""Statistical anomaly detection.

**No LLM, no black box.** Rolling baselines, z-scores and percentage change —
methods a business analyst can check by hand in a spreadsheet.

That constraint is the point. An anomaly alert nobody can verify gets ignored
after the second false positive. Every anomaly here carries the numbers that
produced it and a sentence explaining them.

The flow, per the design:

    metric series
      -> rolling baseline (trailing window, never looks ahead)
      -> standard deviation
      -> percentage change
      -> z-score
      -> minimum volume met?      no  -> ignore, it is small-sample noise
      -> threshold exceeded?      no  -> not an anomaly
      -> assign severity
      -> generate deterministic explanation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from pipelines.common.domain import Severity
from pipelines.common.logging import get_logger

log = get_logger(__name__)

#: Days of history used as the baseline. Seven covers a full weekly cycle, so
#: a Monday is compared against a window containing other Mondays rather than
#: against last weekend.
BASELINE_WINDOW_DAYS: Final[int] = 7

#: Below this many reviews in the current period, the signal is ignored.
#: Two negative reviews out of three is 67% negative and means nothing.
#: This single threshold removes most false positives.
MIN_VOLUME: Final[int] = 10

#: A z-score this far from the baseline counts as anomalous.
Z_SCORE_THRESHOLD: Final[float] = 2.0

#: ...and the change must also be this large in relative terms. Requiring both
#: stops a statistically significant but commercially irrelevant move (12.0% to
#: 12.8% on a very steady series) from being reported.
MIN_PERCENTAGE_CHANGE: Final[float] = 25.0

#: Floor for the baseline standard deviation, as a fraction of the baseline
#: mean. Prevents a perfectly flat series from producing an undefined z-score
#: and hiding an obvious step change.
MIN_SPREAD_FRACTION: Final[float] = 0.01

#: Severity bands, by z-score.
SEVERITY_BANDS: Final[tuple[tuple[float, Severity], ...]] = (
    (5.0, Severity.CRITICAL),
    (3.5, Severity.HIGH),
    (2.5, Severity.MEDIUM),
    (Z_SCORE_THRESHOLD, Severity.LOW),
)


@dataclass(frozen=True, slots=True)
class AnomalyRule:
    """One metric to watch."""

    metric: str
    #: Column holding the value being monitored.
    value_column: str
    #: Column holding the volume used for the minimum-volume check.
    volume_column: str
    #: Which direction is a problem. `both` reports either.
    direction: str  # "increase" | "decrease" | "both"
    description: str


ANOMALY_RULES: Final[tuple[AnomalyRule, ...]] = (
    AnomalyRule(
        metric="negative_sentiment_rate",
        value_column="negative_percentage",
        volume_column="review_count",
        direction="increase",
        description="share of negative reviews",
    ),
    AnomalyRule(
        metric="review_volume",
        value_column="review_count",
        volume_column="review_count",
        direction="both",
        description="daily review volume",
    ),
    AnomalyRule(
        metric="average_rating",
        value_column="average_rating",
        volume_column="review_count",
        direction="decrease",
        description="average star rating",
    ),
)


def _anomaly_id(
    metric: str,
    entity: str,
    detected_date: object,
    topic: str | None,
    country: str | None,
) -> str:
    """Build an id that is unique at the grain the dataset is actually stored at.

    A brand-level detection and a topic-level detection can share a metric, a
    brand and a day; only the topic distinguishes them. `-` marks a dimension
    that does not apply, so the two cases stay distinguishable rather than both
    collapsing to an empty string.

    Kept human-readable on purpose — a hash would be unique too, but an
    operator reading a log line could not tell what it referred to.
    """
    date_part = str(detected_date)[:10]
    return f"{metric}:{entity}:{date_part}:{topic or '-'}:{country or '-'}"


def _severity_for(z_score: float) -> Severity:
    """Map a z-score to a severity band."""
    magnitude = abs(z_score)
    for threshold, severity in SEVERITY_BANDS:
        if magnitude >= threshold:
            return severity
    return Severity.LOW


def _explain(
    rule: AnomalyRule,
    entity: str,
    current: float,
    baseline: float,
    percentage_change: float,
    z_score: float,
    volume: int,
) -> str:
    """Build a deterministic, checkable explanation.

    Written so a reader can verify it against the numbers rather than trust it.
    Deliberately avoids implying more confidence than a 7-day window supports —
    no "significant", no "confirmed".
    """
    direction = "rose" if percentage_change > 0 else "fell"
    return (
        f"{entity}: {rule.description} {direction} from {baseline:.2f} to "
        f"{current:.2f} ({percentage_change:+.1f}%), which is {abs(z_score):.1f} "
        f"standard deviations from the {BASELINE_WINDOW_DAYS}-day baseline. "
        f"Based on {volume:,} reviews on the day."
    )


def detect_anomalies(
    frame: pd.DataFrame,
    *,
    entity_column: str = "brand",
    date_column: str = "review_date",
    topic: str | None = None,
    country: str | None = None,
    min_volume: int = MIN_VOLUME,
    z_threshold: float = Z_SCORE_THRESHOLD,
) -> pd.DataFrame:
    """Detect anomalies in a daily metric series.

    Args:
        frame: Daily metrics, one row per (date, entity).
        entity_column: What is being monitored — usually `brand`.
        date_column: The date column.
        topic / country: Recorded on each anomaly for context.
        min_volume: Ignore periods with fewer reviews than this.
        z_threshold: How far from the baseline counts as anomalous.

    Returns:
        One row per detected anomaly, with the numbers behind it.
    """
    if frame.empty:
        return pd.DataFrame()

    results: list[dict[str, object]] = []
    working = frame.sort_values([entity_column, date_column]).copy()

    for rule in ANOMALY_RULES:
        if rule.value_column not in working.columns:
            continue

        for entity, group in working.groupby(entity_column, sort=True):
            series = group.reset_index(drop=True)
            if len(series) < BASELINE_WINDOW_DAYS + 1:
                continue  # not enough history to have a baseline

            values = pd.to_numeric(series[rule.value_column], errors="coerce")
            volumes = pd.to_numeric(series[rule.volume_column], errors="coerce").fillna(0)

            # Trailing window, shifted by one so the current day is compared
            # against history that excludes it. Including today in its own
            # baseline drags the mean toward the value being tested and hides
            # exactly the spikes we are looking for.
            baseline = values.rolling(BASELINE_WINDOW_DAYS, min_periods=3).mean().shift(1)
            deviation = values.rolling(BASELINE_WINDOW_DAYS, min_periods=3).std().shift(1)

            for index in range(len(series)):
                current = values.iloc[index]
                mean = baseline.iloc[index]
                spread = deviation.iloc[index]
                volume = int(volumes.iloc[index])

                if pd.isna(current) or pd.isna(mean) or pd.isna(spread):
                    continue
                if volume < min_volume:
                    continue  # small-sample noise

                # A perfectly flat baseline has zero standard deviation, which
                # makes the z-score undefined — and would silently hide the
                # most obvious anomaly there is: a stable series that suddenly
                # jumps. Flooring the spread at 1% of the baseline keeps the
                # arithmetic defined and reports such a jump as a large
                # deviation, which is what it is. The MIN_PERCENTAGE_CHANGE
                # gate below still stops trivial moves being reported.
                spread = max(float(spread), abs(float(mean)) * MIN_SPREAD_FRACTION)
                if spread == 0:
                    continue  # baseline is zero and flat; nothing to compare against

                z_score = float((current - mean) / spread)
                percentage_change = float((current - mean) / mean * 100.0) if mean != 0 else 0.0

                if abs(z_score) < z_threshold:
                    continue
                if abs(percentage_change) < MIN_PERCENTAGE_CHANGE:
                    continue
                if rule.direction == "increase" and z_score < 0:
                    continue
                if rule.direction == "decrease" and z_score > 0:
                    continue

                entity_name = str(entity)
                results.append(
                    {
                        # Every dimension that varies within this dataset has
                        # to be in the id, or it does not identify a row.
                        # `topic` and `country` were originally omitted, which
                        # gave a brand-level anomaly and a topic-level one on
                        # the same brand, metric and day the same id — 160 rows
                        # sharing 146 ids. Nothing noticed until a loader used
                        # the id as a primary key and 14 anomalies collided.
                        "anomaly_id": _anomaly_id(
                            rule.metric,
                            entity_name,
                            series.iloc[index][date_column],
                            topic,
                            country,
                        ),
                        "detected_date": series.iloc[index][date_column],
                        "brand": entity_name,
                        "metric": rule.metric,
                        "topic": topic,
                        "country": country,
                        "current_value": round(float(current), 4),
                        "baseline_value": round(float(mean), 4),
                        "percentage_change": round(percentage_change, 2),
                        "z_score": round(z_score, 3),
                        "review_count": volume,
                        "severity": _severity_for(z_score).value,
                        "explanation": _explain(
                            rule,
                            entity_name,
                            float(current),
                            float(mean),
                            percentage_change,
                            z_score,
                            volume,
                        ),
                    }
                )

    if not results:
        log.info("no_anomalies_detected", rows_examined=len(frame))
        return pd.DataFrame()

    anomalies = pd.DataFrame(results).sort_values(
        ["detected_date", "severity", "brand"], ascending=[False, True, True]
    )
    log.info(
        "anomalies_detected",
        count=len(anomalies),
        by_severity=anomalies["severity"].value_counts().to_dict(),
        by_metric=anomalies["metric"].value_counts().to_dict(),
    )
    return anomalies.reset_index(drop=True)


def detect_topic_anomalies(
    topic_metrics: pd.DataFrame,
    *,
    min_volume: int = MIN_VOLUME,
) -> pd.DataFrame:
    """Detect anomalies per (brand, topic).

    Run separately from brand-level detection because a spike confined to one
    topic is invisible at brand level: delivery complaints tripling while
    everything else improves can leave the overall negative rate flat.

    This is what surfaces "delivery complaints are up 300% for one brand"
    rather than "something is slightly off somewhere".
    """
    if topic_metrics.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for topic, group in topic_metrics.groupby("topic", sort=True):
        detected = detect_anomalies(group, topic=str(topic), min_volume=min_volume)
        if not detected.empty:
            frames.append(detected)

    if not frames:
        log.info("no_topic_anomalies_detected", topics=topic_metrics["topic"].nunique())
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(["detected_date", "severity"], ascending=[False, True]).reset_index(
        drop=True
    )
