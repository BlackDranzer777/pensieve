"""Tests for text normalisation and feature extraction."""

from __future__ import annotations

import pytest

from pipelines.transformation.text import (
    collapse_repeated_punctuation,
    count_characters,
    count_emoji,
    count_exclamations,
    count_words,
    extract_features,
    has_mention,
    has_url,
    is_effectively_empty,
    normalize_text,
    normalize_unicode,
    normalize_whitespace,
    replace_emails,
    replace_mentions,
    replace_urls,
    strip_html,
    uppercase_ratio,
)


class TestUnicodeNormalisation:
    def test_folds_full_width_characters(self) -> None:
        """NFKC makes visually identical strings compare equal, which is what
        lets deduplication see them as the same review."""
        assert normalize_unicode("Ｔｈｉｓ　ｉｓ　ｗｉｄｅ") == "This is wide"

    def test_removes_zero_width_characters(self) -> None:
        assert normalize_unicode("he​llo​") == "hello"

    def test_removes_byte_order_mark(self) -> None:
        assert normalize_unicode("﻿hello") == "hello"

    def test_removes_soft_hyphen(self) -> None:
        assert normalize_unicode("co­operate") == "cooperate"

    def test_preserves_accents_and_non_latin_scripts(self) -> None:
        """Normalisation must not damage the languages we support."""
        assert normalize_unicode("café") == "café"
        assert normalize_unicode("Świetna cena") == "Świetna cena"
        assert normalize_unicode("स्वाद बहुत बढ़िया") == "स्वाद बहुत बढ़िया"

    def test_handles_empty_input(self) -> None:
        assert normalize_unicode("") == ""


class TestHtmlStripping:
    def test_removes_tags_but_keeps_inner_text(self) -> None:
        """Deleting `<b>great</b>` wholesale would delete a real word."""
        assert strip_html("<p>Great <b>product</b></p>").strip() == "Great  product"

    def test_removes_script_content_entirely(self) -> None:
        result = strip_html("Good<script>alert('x')</script>product")

        assert "alert" not in result
        assert "Good" in result

    def test_decodes_common_entities(self) -> None:
        assert strip_html("Tom &amp; Jerry").strip() == "Tom & Jerry"
        assert strip_html("&lt;b&gt;bold&lt;/b&gt;").strip() == "<b>bold</b>"

    def test_decodes_numeric_entities(self) -> None:
        assert strip_html("it&#39;s").strip() == "it's"

    def test_leaves_plain_text_untouched(self) -> None:
        assert strip_html("no markup here") == "no markup here"

    def test_does_not_treat_a_lone_less_than_as_a_tag(self) -> None:
        assert "5" in strip_html("price < 5 euros")


class TestWhitespace:
    def test_collapses_runs_of_spaces(self) -> None:
        assert normalize_whitespace("a     b") == "a b"

    def test_collapses_newlines_and_tabs(self) -> None:
        assert normalize_whitespace("a\n\n\tb") == "a b"

    def test_collapses_non_breaking_spaces(self) -> None:
        assert normalize_whitespace("a  b") == "a b"

    def test_trims_the_ends(self) -> None:
        assert normalize_whitespace("   hello   ") == "hello"


class TestRepeatedPunctuation:
    def test_shortens_long_runs_but_keeps_emphasis(self) -> None:
        """Collapsing to a single "!" would erase intensity the sentiment model
        relies on."""
        assert collapse_repeated_punctuation("Terrible!!!!!!!") == "Terrible!!"

    def test_leaves_short_runs_alone(self) -> None:
        assert collapse_repeated_punctuation("Wow!!") == "Wow!!"
        assert collapse_repeated_punctuation("Really?") == "Really?"

    def test_handles_ellipsis(self) -> None:
        assert collapse_repeated_punctuation("Hmm.......") == "Hmm.."


class TestPlaceholders:
    @pytest.mark.parametrize(
        "text", ["visit https://spam.example.com now", "see www.example.com/page"]
    )
    def test_replaces_urls(self, text: str) -> None:
        result = replace_urls(text)

        assert "<url>" in result
        assert "example.com" not in result

    def test_replaces_mentions(self) -> None:
        assert "<mention>" in replace_mentions("thanks @support_team")

    def test_replaces_emails(self) -> None:
        """Also keeps an address typed into a review out of the analytics layer."""
        result = replace_emails("contact me at jane.doe@example.com")

        assert "<email>" in result
        assert "jane.doe@example.com" not in result

    def test_does_not_mangle_ordinary_text(self) -> None:
        assert replace_urls("no links here") == "no links here"


class TestFeatureCounts:
    def test_counts_words_across_scripts(self) -> None:
        assert count_words("hello world") == 2
        assert count_words("bardzo dobra cena") == 3
        assert count_words("स्वाद बहुत बढ़िया है") == 4

    def test_counts_characters_including_spaces(self) -> None:
        assert count_characters("abc def") == 7

    def test_counts_emoji(self) -> None:
        assert count_emoji("great 😀 product 🎉") == 2

    def test_counts_no_emoji_in_plain_text(self) -> None:
        assert count_emoji("plain text") == 0

    def test_counts_exclamations(self) -> None:
        assert count_exclamations("wow!! really!") == 3

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("ALL CAPS", 1.0),
            ("all lower", 0.0),
            # "Half AND half" has 11 cased letters (H a l f A N D h a l f),
            # 4 of them uppercase.
            ("Half AND half", 4 / 11),
        ],
    )
    def test_uppercase_ratio(self, text: str, expected: float) -> None:
        assert uppercase_ratio(text) == pytest.approx(expected, abs=0.01)

    def test_uppercase_ratio_ignores_digits_and_punctuation(self) -> None:
        assert uppercase_ratio("ABC 123 !!!") == 1.0

    def test_uppercase_ratio_is_zero_for_caseless_scripts(self) -> None:
        """Devanagari has no case. Returning 0 rather than dividing by zero
        keeps Hindi reviews from looking artificially calm or crashing."""
        assert uppercase_ratio("स्वाद बहुत बढ़िया") == 0.0

    def test_uppercase_ratio_of_empty_text_is_zero(self) -> None:
        assert uppercase_ratio("") == 0.0

    def test_detects_urls_and_mentions(self) -> None:
        assert has_url("see https://example.com") is True
        assert has_url("no link") is False
        assert has_mention("hi @someone") is True
        assert has_mention("email@domain.com") is False


class TestEmptyDetection:
    @pytest.mark.parametrize("text", [None, "", "   ", "\n\t ", "​​", "<p></p>", "<p>   </p>"])
    def test_recognises_empty_text(self, text: str | None) -> None:
        assert is_effectively_empty(text) is True

    @pytest.mark.parametrize("text", ["ok", "5", "<p>hello</p>", "स्वाद"])
    def test_recognises_real_content(self, text: str) -> None:
        assert is_effectively_empty(text) is False


class TestNormalizeText:
    def test_runs_the_full_pipeline(self) -> None:
        raw = "﻿  <p>GREAT   product!!!!!  visit https://x.com </p>  "
        result = normalize_text(raw)

        assert "<p>" not in result
        assert "﻿" not in result
        assert "https://x.com" not in result
        assert "<url>" in result
        assert "  " not in result
        assert result.startswith("GREAT")

    def test_preserves_case_as_sentiment_signal(self) -> None:
        """Lower-casing would delete the shouting, which is exactly the signal
        an angry review carries."""
        assert "TERRIBLE" in normalize_text("TERRIBLE service")

    def test_preserves_emoji(self) -> None:
        assert "😀" in normalize_text("love it 😀")

    def test_handles_none(self) -> None:
        assert normalize_text(None) == ""

    def test_handles_pandas_missing_values(self) -> None:
        """Regression test: `Series.map()` passes `pd.NA`, not `None`, and
        `pd.NA` raises on truth testing. Guarding only against `None` passed
        every unit test and crashed on the first real batch."""
        import pandas as pd

        for missing in (pd.NA, float("nan"), None):
            assert normalize_text(missing) == ""
            assert is_effectively_empty(missing) is True
            assert extract_features(missing).word_count == 0

    def test_is_idempotent(self) -> None:
        """Running the pipeline twice must not change the result — otherwise
        reprocessing a batch would produce different Silver output."""
        once = normalize_text("  <b>Hello</b>   world!!!!  ")

        assert normalize_text(once) == once


class TestExtractFeatures:
    def test_measures_the_original_not_the_normalised_text(self) -> None:
        """Features describe how the customer actually wrote. Measuring the
        cleaned text would flatten exactly what they express."""
        features = extract_features("GREAT!!!! 😀")

        assert features.uppercase_ratio == 1.0
        assert features.exclamation_count == 4
        assert features.emoji_count == 1

    def test_handles_none_and_empty(self) -> None:
        for value in (None, ""):
            features = extract_features(value)
            assert features.word_count == 0
            assert features.character_count == 0
            assert features.uppercase_ratio == 0.0
