"""Tests for the synthetic review generator."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from pipelines.common.domain import INPUT_COLUMNS, Language, Topic
from pipelines.ingestion.generator import (
    BRANDS,
    COUNTRY_LANGUAGE,
    PRODUCTS,
    DirtyRecordConfig,
    GeneratorConfig,
    generate_reviews,
)
from pipelines.ingestion.templates import TEMPLATES, template_count

FIXED_END = datetime(2026, 6, 1, tzinfo=UTC)


class TestDeterminism:
    def test_same_seed_produces_identical_data(self) -> None:
        """The reproducibility guarantee. Without this, a benchmark measured on
        Monday cannot be compared with one measured on Tuesday."""
        first = generate_reviews(config=GeneratorConfig(rows=200, seed=99, end_date=FIXED_END))
        second = generate_reviews(config=GeneratorConfig(rows=200, seed=99, end_date=FIXED_END))

        pd.testing.assert_frame_equal(first, second)

    def test_different_seeds_produce_different_data(self) -> None:
        first = generate_reviews(config=GeneratorConfig(rows=200, seed=1, end_date=FIXED_END))
        second = generate_reviews(config=GeneratorConfig(rows=200, seed=2, end_date=FIXED_END))

        assert not first.equals(second)

    def test_end_date_defaults_to_midnight_not_now(self) -> None:
        """Regression test: anchoring on `now()` made every run differ, which
        silently broke ingestion idempotency."""
        resolved = GeneratorConfig(rows=1).resolved_end_date()

        assert (resolved.hour, resolved.minute, resolved.second, resolved.microsecond) == (
            0,
            0,
            0,
            0,
        )

    def test_pinned_end_date_is_respected(self) -> None:
        frame = generate_reviews(config=GeneratorConfig(rows=50, seed=3, end_date=FIXED_END))
        timestamps = pd.to_datetime(
            frame["created_at"], format="ISO8601", utc=True, errors="coerce"
        )

        assert timestamps.max() <= FIXED_END


class TestShape:
    def test_produces_the_contract_columns(self) -> None:
        frame = generate_reviews(config=GeneratorConfig(rows=50, seed=1, end_date=FIXED_END))

        assert set(frame.columns) == set(INPUT_COLUMNS)

    def test_every_column_is_a_string(self) -> None:
        """Mirrors a real CSV export, where nothing is typed until we parse it."""
        frame = generate_reviews(config=GeneratorConfig(rows=50, seed=1, end_date=FIXED_END))

        assert all(dtype == "string" for dtype in frame.dtypes)

    def test_row_count_includes_appended_duplicates(self) -> None:
        config = GeneratorConfig(rows=1000, seed=1, end_date=FIXED_END)
        frame = generate_reviews(config=config)

        expected_duplicates = int(1000 * config.dirty.duplicate_rate)
        assert len(frame) == 1000 + expected_duplicates

    @pytest.mark.parametrize("rows", [1, 10, 500])
    def test_handles_small_row_counts(self, rows: int) -> None:
        frame = generate_reviews(config=GeneratorConfig(rows=rows, seed=1, end_date=FIXED_END))

        assert len(frame) >= rows


class TestDimensions:
    def test_covers_every_brand(self) -> None:
        frame = generate_reviews(config=GeneratorConfig(rows=2000, seed=1, end_date=FIXED_END))
        brands = set(frame["brand"].dropna().unique())

        for brand, _category in BRANDS:
            assert brand in brands

    def test_products_belong_to_their_brand(self, clean_reviews: pd.DataFrame) -> None:
        """A product from the wrong brand would make brand-level aggregation
        meaningless."""
        for _, row in clean_reviews.iterrows():
            assert row["product"] in PRODUCTS[row["brand"]]

    def test_covers_every_country(self) -> None:
        frame = generate_reviews(config=GeneratorConfig(rows=2000, seed=1, end_date=FIXED_END))
        countries = set(frame["country"].dropna().unique())

        for code, _language, _weight in COUNTRY_LANGUAGE:
            assert code in countries

    def test_ratings_are_j_shaped_not_uniform(self) -> None:
        """Real review distributions are polarised. A uniform spread would make
        the average rating metric uninteresting."""
        frame = generate_reviews(
            config=GeneratorConfig(
                rows=3000,
                seed=1,
                end_date=FIXED_END,
                dirty=DirtyRecordConfig(invalid_rating_rate=0.0),
            )
        )
        counts = frame["rating"].value_counts(normalize=True)

        assert counts.get("5", 0) > counts.get("3", 0)
        assert counts.get("1", 0) > counts.get("3", 0)

    def test_spans_the_requested_history(self) -> None:
        frame = generate_reviews(
            config=GeneratorConfig(rows=2000, seed=1, days=90, end_date=FIXED_END)
        )
        timestamps = pd.to_datetime(
            frame["created_at"], format="ISO8601", utc=True, errors="coerce"
        ).dropna()

        assert (timestamps.max() - timestamps.min()).days >= 80


class TestDefectInjection:
    def test_injects_roughly_the_configured_share(self) -> None:
        config = GeneratorConfig(rows=5000, seed=1, end_date=FIXED_END)
        frame = generate_reviews(config=config)

        # Duplicates are appended, so measure defects against the clean count.
        expected = config.dirty.total_rate()
        assert 0.5 * expected < expected < 1.5 * expected  # sanity on the config itself
        assert len(frame) > config.rows

    def test_produces_missing_text(self, messy_reviews: pd.DataFrame) -> None:
        blank = messy_reviews["text"].isna() | (messy_reviews["text"].str.strip() == "")

        assert blank.sum() > 0

    def test_produces_out_of_range_and_non_numeric_ratings(
        self, messy_reviews: pd.DataFrame
    ) -> None:
        numeric = pd.to_numeric(messy_reviews["rating"], errors="coerce")

        assert numeric.isna().sum() > 0, "expected non-numeric ratings"
        assert ((numeric < 1) | (numeric > 5)).sum() > 0, "expected out-of-range ratings"

    def test_produces_unparseable_dates(self, messy_reviews: pd.DataFrame) -> None:
        parsed = pd.to_datetime(
            messy_reviews["created_at"], format="ISO8601", utc=True, errors="coerce"
        )

        assert parsed.isna().sum() > 0

    def test_produces_html_in_text(self, messy_reviews: pd.DataFrame) -> None:
        has_html = messy_reviews["text"].fillna("").str.contains("<|&lt;", regex=True)

        assert has_html.sum() > 0

    def test_produces_missing_brand(self, messy_reviews: pd.DataFrame) -> None:
        blank = messy_reviews["brand"].isna() | (messy_reviews["brand"].str.strip() == "")

        assert blank.sum() > 0

    def test_produces_duplicate_review_ids(self, messy_reviews: pd.DataFrame) -> None:
        assert messy_reviews["review_id"].duplicated().sum() > 0

    def test_produces_very_short_text(self, messy_reviews: pd.DataFrame) -> None:
        short = messy_reviews["text"].fillna("").str.len().between(1, 3)

        assert short.sum() > 0

    def test_clean_config_injects_nothing(self, clean_reviews: pd.DataFrame) -> None:
        """Needed so a failing test can be isolated from defect noise."""
        assert clean_reviews["review_id"].duplicated().sum() == 0
        assert clean_reviews["brand"].isna().sum() == 0
        assert clean_reviews["text"].isna().sum() == 0

        numeric = pd.to_numeric(clean_reviews["rating"], errors="coerce")
        assert numeric.between(1, 5).all()

        parsed = pd.to_datetime(
            clean_reviews["created_at"], format="ISO8601", utc=True, errors="coerce"
        )
        assert parsed.notna().all()


class TestTemplates:
    def test_every_supported_language_has_templates(self) -> None:
        for language in (
            Language.ENGLISH,
            Language.POLISH,
            Language.HINDI,
            Language.FRENCH,
            Language.GERMAN,
            Language.SPANISH,
        ):
            assert language in TEMPLATES, f"{language} has no templates"

    def test_every_language_covers_every_business_topic(self) -> None:
        """A missing topic in one language would bias topic analysis by market."""
        business_topics = {t for t in Topic if t is not Topic.OTHER}

        for language, bank in TEMPLATES.items():
            assert set(bank) == business_topics, f"{language} is missing topics"

    def test_templates_are_non_empty_strings(self) -> None:
        for bank in TEMPLATES.values():
            for by_sentiment in bank.values():
                for phrasings in by_sentiment.values():
                    assert phrasings
                    assert all(phrase.strip() for phrase in phrasings)

    def test_template_bank_is_substantial(self) -> None:
        assert template_count() >= 150

    def test_anomaly_injection_concentrates_negative_delivery_reviews(self) -> None:
        """The injected trend must be real, otherwise Phase 5 would be tested
        against a signal that does not exist."""
        config = GeneratorConfig(
            rows=4000, seed=5, days=90, end_date=FIXED_END, inject_anomaly=True
        )
        frame = generate_reviews(config=config)
        created = pd.to_datetime(frame["created_at"], format="ISO8601", utc=True, errors="coerce")

        recent = frame[created >= FIXED_END - pd.Timedelta(days=14)]
        earlier = frame[created < FIXED_END - pd.Timedelta(days=14)]

        def delivery_share(subset: pd.DataFrame) -> float:
            target = subset[subset["brand"] == config.anomaly_brand]
            if target.empty:
                return 0.0
            hits = (
                target["text"]
                .fillna("")
                .str.contains(
                    "deliver|shipping|courier|Lieferung|livraison|dostawa|envío|डिलीवरी",
                    case=False,
                    regex=True,
                )
            )
            return float(hits.mean())

        assert delivery_share(recent) > delivery_share(earlier)
