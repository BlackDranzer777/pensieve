"""Tests for validation rules, quarantine, deduplication and quality scoring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipelines.common.config import PipelineSettings
from pipelines.common.domain import QUALITY_SCORE_VERSION
from pipelines.transformation.dedup import (
    content_fingerprint,
    drop_duplicates,
    mark_duplicates,
)
from pipelines.validation.quality import (
    WEIGHT_DUPLICATE,
    WEIGHT_INVALID,
    calculate_quality,
)
from pipelines.validation.quarantine import read_quarantine, write_quarantine
from pipelines.validation.rules import (
    RULES,
    RuleSeverity,
    apply_rules,
    find_duplicate_review_ids,
    missing_required_columns,
)
from pipelines.validation.service import SchemaError, validate_batch


def make_frame(**overrides: list[object]) -> pd.DataFrame:
    """Build a small valid frame, overriding individual columns."""
    base: dict[str, list[object]] = {
        "review_id": ["r1", "r2"],
        "brand": ["Aurora Foods", "Nimbus Drinks"],
        "product": ["Oat Crunch Cereal", "Cold Brew Coffee"],
        "text": ["Great product, really enjoyed it.", "Delivery was very slow."],
        "country": ["GB", "DE"],
        "rating": ["5", "2"],
        "source": ["web", "app"],
        "created_at": ["2026-01-15T10:00:00", "2026-02-20T14:30:00"],
    }
    base.update(overrides)
    return pd.DataFrame(base).astype("string")


class TestRuleDefinitions:
    def test_rule_ids_are_unique(self) -> None:
        ids = [rule.rule_id for rule in RULES]

        assert len(ids) == len(set(ids))

    def test_every_rule_has_a_description(self) -> None:
        """The description becomes the quarantine reason a human reads."""
        for rule in RULES:
            assert rule.description.strip()


class TestRequiredColumns:
    def test_detects_missing_columns(self) -> None:
        frame = make_frame().drop(columns=["text", "rating"])

        assert set(missing_required_columns(frame)) == {"text", "rating"}

    def test_passes_a_complete_frame(self) -> None:
        assert missing_required_columns(make_frame()) == []

    def test_missing_column_aborts_the_batch(self, settings: PipelineSettings) -> None:
        """No amount of quarantining fixes a file with no text column, so this
        fails loudly rather than rejecting every row with the same reason."""
        frame = make_frame().drop(columns=["text"])

        with pytest.raises(SchemaError, match="text"):
            validate_batch(frame, "batch-1", settings=settings)


class TestRatingRule:
    @pytest.mark.parametrize("value", ["1", "3", "5"])
    def test_accepts_valid_ratings(self, value: str) -> None:
        failures = apply_rules(make_frame(rating=[value, "4"]))

        assert not [f for f in failures if f.rule_id == "rating_out_of_range"]

    @pytest.mark.parametrize("value", ["0", "6", "-1", "99", "five", "", "4.5"])
    def test_rejects_invalid_ratings(self, value: str) -> None:
        failures = apply_rules(make_frame(rating=[value, "4"]))
        offending = [f for f in failures if f.rule_id == "rating_out_of_range"]

        assert len(offending) == 1
        assert offending[0].failed_value in {value, "<missing>"}

    def test_rejects_fractional_ratings(self) -> None:
        """A rating is a discrete choice; 4.5 means the feed is wrong."""
        failures = apply_rules(make_frame(rating=["4.5", "4"]))

        assert any(f.rule_id == "rating_out_of_range" for f in failures)


class TestTimestampRule:
    @pytest.mark.parametrize(
        "value", ["not-a-date", "2026-13-45", "", "0000-00-00", "2099-01-01T00:00:00"]
    )
    def test_rejects_unparseable_and_impossible_dates(self, value: str) -> None:
        failures = apply_rules(make_frame(created_at=[value, "2026-01-01T00:00:00"]))

        assert any(f.rule_id == "created_at_invalid" for f in failures)

    def test_rejects_dates_before_the_platform_epoch(self) -> None:
        failures = apply_rules(
            make_frame(created_at=["1999-01-01T00:00:00", "2026-01-01T00:00:00"])
        )

        assert any(f.rule_id == "created_at_invalid" for f in failures)

    def test_accepts_a_normal_timestamp(self) -> None:
        failures = apply_rules(
            make_frame(created_at=["2026-03-01T09:00:00", "2026-03-02T09:00:00"])
        )

        assert not [f for f in failures if f.rule_id == "created_at_invalid"]


class TestTextRule:
    @pytest.mark.parametrize("value", ["", "   ", "ok", "!", "<p></p>"])
    def test_rejects_empty_and_too_short_text(self, value: str) -> None:
        failures = apply_rules(make_frame(text=[value, "A perfectly fine review."]))

        assert any(f.rule_id == "text_invalid" for f in failures)

    def test_rejects_absurdly_long_text(self) -> None:
        failures = apply_rules(make_frame(text=["x" * 6000, "fine review here"]))

        assert any(f.rule_id == "text_invalid" for f in failures)

    def test_accepts_html_wrapped_text_with_real_content(self) -> None:
        """Formatting is not a reason to reject — cleaning handles it."""
        failures = apply_rules(make_frame(text=["<p>Genuinely good product</p>", "also fine here"]))

        assert not [f for f in failures if f.rule_id == "text_invalid"]


class TestBrandRule:
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_rejects_missing_brand(self, value: str | None) -> None:
        failures = apply_rules(make_frame(brand=[value, "Nimbus Drinks"]))

        assert any(f.rule_id == "brand_missing" for f in failures)


class TestCountryRule:
    def test_malformed_country_is_a_warning_not_an_error(self) -> None:
        """A typo'd country should not throw away an otherwise good review."""
        failures = apply_rules(make_frame(country=["GBR", "DE"]))
        country_failures = [f for f in failures if f.rule_id == "country_malformed"]

        assert len(country_failures) == 1
        assert country_failures[0].severity is RuleSeverity.WARNING

    def test_missing_country_is_acceptable(self) -> None:
        failures = apply_rules(make_frame(country=["", "DE"]))

        assert not [f for f in failures if f.rule_id == "country_malformed"]


class TestDuplicateIds:
    def test_flags_later_occurrences_only(self) -> None:
        """The first occurrence is canonical; flagging all of them would
        discard the original along with its copies."""
        frame = make_frame(review_id=["r1", "r1"])

        flags = find_duplicate_review_ids(frame)

        assert flags.tolist() == [False, True]

    def test_duplicate_ids_are_reported_as_failures(self) -> None:
        failures = apply_rules(make_frame(review_id=["r1", "r1"]))

        assert any(f.rule_id == "review_id_duplicate" for f in failures)


class TestMultipleFailures:
    def test_a_row_breaking_several_rules_reports_all_of_them(self) -> None:
        """The person fixing the upstream feed needs the full list, not the
        first item."""
        frame = make_frame(
            rating=["99", "4"], created_at=["nope", "2026-01-01T00:00:00"], brand=["", "X"]
        )

        failures = [f for f in apply_rules(frame) if f.row_index == 0]

        assert {f.rule_id for f in failures} >= {
            "rating_out_of_range",
            "created_at_invalid",
            "brand_missing",
        }


class TestQuarantine:
    def test_writes_failed_records_with_reasons(self, tmp_path: Path) -> None:
        frame = make_frame(rating=["99", "4"])
        failures = apply_rules(frame)

        partition = write_quarantine(frame, failures, "batch-1", tmp_path)

        assert partition is not None
        stored = read_quarantine(tmp_path)
        assert len(stored) == len(failures)
        for column in ("batch_id", "rule_id", "failed_field", "failed_value", "failure_reason"):
            assert column in stored.columns

    def test_preserves_the_original_values(self, tmp_path: Path) -> None:
        """A quarantined record is only fixable if you can see what arrived."""
        frame = make_frame(rating=["99", "4"])
        write_quarantine(frame, apply_rules(frame), "batch-1", tmp_path)

        stored = read_quarantine(tmp_path)
        row = stored[stored["rule_id"] == "rating_out_of_range"].iloc[0]

        assert row["rating"] == "99"
        assert row["failed_value"] == "99"
        assert row["review_id"] == "r1"

    def test_writes_nothing_when_the_batch_is_clean(self, tmp_path: Path) -> None:
        frame = make_frame()

        assert write_quarantine(frame, [], "batch-1", tmp_path) is None
        assert read_quarantine(tmp_path).empty

    def test_one_row_breaking_two_rules_produces_two_records(self, tmp_path: Path) -> None:
        """So the reasons breakdown on the dashboard adds up honestly."""
        frame = make_frame(rating=["99", "4"], brand=["", "X"])
        write_quarantine(frame, apply_rules(frame), "batch-1", tmp_path)

        stored = read_quarantine(tmp_path)

        assert len(stored[stored["review_id"] == "r1"]) >= 2


class TestDeduplication:
    def test_identical_content_shares_a_fingerprint(self) -> None:
        assert content_fingerprint("Brand", "Great service") == content_fingerprint(
            "Brand", "Great service"
        )

    def test_formatting_differences_do_not_change_the_fingerprint(self) -> None:
        """Normalising first is what makes this useful."""
        assert content_fingerprint("Brand", "  GREAT   service!!! ") == content_fingerprint(
            "Brand", "<p>GREAT service!!</p>"
        )

    def test_different_brands_do_not_collide(self) -> None:
        """Two brands getting the same generic praise are not one review."""
        assert content_fingerprint("A", "Great product") != content_fingerprint(
            "B", "Great product"
        )

    def test_marks_repeats_without_deleting_them(self) -> None:
        frame = make_frame(
            review_id=["r1", "r2"],
            brand=["Aurora Foods", "Aurora Foods"],
            text=["Same text here", "Same text here"],
        )

        result = mark_duplicates(frame)

        assert len(result.frame) == 2, "duplicates must be marked, not removed"
        assert pd.isna(result.frame.iloc[0]["is_duplicate_of"])
        assert result.frame.iloc[1]["is_duplicate_of"] == "r1"
        assert result.content_duplicates == 1

    def test_distinct_reviews_are_not_marked(self) -> None:
        result = mark_duplicates(make_frame())

        assert result.content_duplicates == 0
        assert result.frame["is_duplicate_of"].isna().all()

    def test_drop_duplicates_keeps_only_canonical_rows(self) -> None:
        frame = make_frame(brand=["Aurora Foods", "Aurora Foods"], text=["Same text", "Same text"])
        marked = mark_duplicates(frame).frame

        assert len(drop_duplicates(marked)) == 1

    def test_handles_an_empty_frame(self) -> None:
        result = mark_duplicates(pd.DataFrame())

        assert result.frame.empty
        assert result.content_duplicates == 0


class TestQualityScore:
    def test_a_clean_batch_scores_100(self) -> None:
        frame = make_frame()

        assert calculate_quality(frame, apply_rules(frame)).score == 100.0

    def test_an_empty_batch_scores_zero_not_100(self) -> None:
        """A perfect score for a batch containing nothing would be misleading."""
        report = calculate_quality(pd.DataFrame(), [])

        assert report.score == 0.0
        assert report.total_records == 0

    def test_invalid_records_reduce_the_score(self) -> None:
        frame = make_frame(rating=["99", "4"])
        report = calculate_quality(frame, apply_rules(frame))

        assert report.score < 100.0
        assert report.invalid_records == 1

    def test_the_score_never_leaves_the_zero_to_100_range(self) -> None:
        frame = make_frame(
            review_id=["r1", "r1"],
            brand=["", ""],
            text=["", ""],
            rating=["99", "nope"],
            created_at=["bad", "worse"],
        )
        report = calculate_quality(frame, apply_rules(frame))

        assert 0.0 <= report.score <= 100.0

    def test_invalid_records_are_penalised_harder_than_duplicates(self) -> None:
        """Unusable data should cost more than repeated data."""
        assert WEIGHT_INVALID > WEIGHT_DUPLICATE

    def test_components_sum_to_the_deduction(self) -> None:
        frame = make_frame(rating=["99", "4"])
        report = calculate_quality(frame, apply_rules(frame))

        deducted = sum(component.penalty for component in report.components)

        assert report.score == pytest.approx(100.0 - deducted, abs=0.01)

    def test_the_report_explains_itself(self) -> None:
        """A score nobody can derive is a score nobody should trust."""
        frame = make_frame(rating=["99", "4"])
        explanation = calculate_quality(frame, apply_rules(frame)).explain()

        assert "Quality score" in explanation
        assert "invalid records" in explanation
        assert QUALITY_SCORE_VERSION in explanation

    def test_the_score_is_versioned(self) -> None:
        """So changing the weights does not silently reinterpret history."""
        report = calculate_quality(make_frame(), [])

        assert report.version == QUALITY_SCORE_VERSION

    def test_counts_failures_by_rule(self) -> None:
        frame = make_frame(rating=["99", "0"])
        report = calculate_quality(frame, apply_rules(frame))

        assert report.failures_by_rule["rating_out_of_range"] == 2


class TestValidateBatch:
    def test_splits_valid_from_invalid(self, settings: PipelineSettings) -> None:
        frame = make_frame(rating=["99", "4"])

        result = validate_batch(frame, "batch-1", settings=settings)

        assert result.rows_in == 2
        assert result.rows_out == 1
        assert result.rows_quarantined == 1

    def test_writes_quarantine_to_disk(self, settings: PipelineSettings) -> None:
        frame = make_frame(rating=["99", "4"])

        result = validate_batch(frame, "batch-1", settings=settings)

        assert result.quarantine_path is not None
        assert not read_quarantine(settings.quarantine_path).empty

    def test_adds_normalized_text_alongside_the_original(self, settings: PipelineSettings) -> None:
        frame = make_frame(text=["<p>Great   product</p>", "Fine review text"])

        result = validate_batch(frame, "batch-1", settings=settings)
        row = result.valid_records.iloc[0]

        assert row["text"] == "<p>Great   product</p>", "original must survive"
        assert row["normalized_text"] == "Great product"

    def test_adds_derived_features(self, settings: PipelineSettings) -> None:
        result = validate_batch(make_frame(), "batch-1", settings=settings)

        for column in (
            "word_count",
            "character_count",
            "emoji_count",
            "exclamation_count",
            "uppercase_ratio",
            "has_url",
            "has_mention",
        ):
            assert column in result.valid_records.columns

    def test_types_the_valid_records(self, settings: PipelineSettings) -> None:
        """Bronze keeps strings; Silver is where data becomes analysable."""
        result = validate_batch(make_frame(), "batch-1", settings=settings)

        assert str(result.valid_records["rating"].dtype) == "Int8"
        assert "datetime64" in str(result.valid_records["created_at"].dtype)

    def test_marks_duplicates_in_the_valid_set(self, settings: PipelineSettings) -> None:
        frame = make_frame(brand=["Aurora Foods", "Aurora Foods"], text=["Same text", "Same text"])

        result = validate_batch(frame, "batch-1", settings=settings)

        assert "is_duplicate_of" in result.valid_records.columns
        assert result.content_duplicates == 1

    def test_processes_the_full_messy_dataset(
        self, settings: PipelineSettings, messy_reviews: pd.DataFrame
    ) -> None:
        """End-to-end on realistic data: some rows survive, some are
        quarantined, and nothing is silently lost."""
        result = validate_batch(messy_reviews, "batch-1", settings=settings)

        assert result.rows_out > 0
        assert result.rows_quarantined > 0
        assert result.rows_out + result.rows_quarantined == result.rows_in
        assert 0.0 < result.quality.score < 100.0
        assert len(result.quality.failures_by_rule) >= 4
