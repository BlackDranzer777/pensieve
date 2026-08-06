"""Tests for language detection, sentiment, topics and the Silver layer.

The real transformer is exercised in exactly one test, marked `model`, which
CI skips. Everything else uses the lexicon backend so the suite runs in
seconds and needs no 1.1 GB download.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipelines.common.config import PipelineSettings
from pipelines.common.domain import PROCESSING_VERSION, Language, Sentiment, Topic
from pipelines.enrichment.language import (
    MAX_TEXT_LENGTH_FOR_DETECTION,
    detect_language,
    detect_languages,
)
from pipelines.enrichment.sentiment import (
    LexiconBackend,
    SentimentModelError,
    TransformersBackend,
    get_backend,
    score_sentiments,
)
from pipelines.enrichment.service import enrich_batch, enrich_records
from pipelines.enrichment.silver import SILVER_COLUMNS, read_silver, write_silver
from pipelines.enrichment.topic_rules import TOPIC_KEYWORDS
from pipelines.enrichment.topics import classify_many, classify_topics


class TestLanguageDetection:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("The delivery was incredibly fast and the packaging was perfect.", Language.ENGLISH),
            ("Świetna cena, produkt jest tańszy niż u konkurencji.", Language.POLISH),
            ("स्वाद बहुत बढ़िया है, बहुत पसंद आया और फिर से ऑर्डर करूँगा।", Language.HINDI),
            ("Le service client a résolu mon problème en une heure seulement.", Language.FRENCH),
            ("Die Lieferung war sehr schnell und das Paket kam früher an.", Language.GERMAN),
            ("El envío fue rapidísimo y llegó un día antes de lo previsto.", Language.SPANISH),
        ],
    )
    def test_detects_each_supported_language(self, text: str, expected: Language) -> None:
        result = detect_language(text)

        assert result.language is expected
        assert result.confidence > 0.5
        assert result.is_supported

    def test_recognises_an_unsupported_language_rather_than_guessing(self) -> None:
        """Without other languages in the candidate set, Lingua would be forced
        to pick one of our six and would confidently return the wrong one."""
        result = detect_language(
            "Il prodotto è arrivato in ritardo e la confezione era danneggiata."
        )

        assert result.language is Language.UNSUPPORTED
        assert not result.is_supported
        assert result.detected_name == "italian"

    def test_unsupported_is_distinct_from_unknown(self) -> None:
        """They mean different things: one says "consider supporting Italian",
        the other says "this text is too short to call"."""
        unsupported = detect_language("Het product kwam te laat aan en de verpakking was kapot.")
        unknown = detect_language("ok")

        assert unsupported.language is Language.UNSUPPORTED
        assert unknown.language is Language.UNKNOWN

    @pytest.mark.parametrize("text", ["", "  ", "ok", "!!"])
    def test_text_too_short_is_unknown(self, text: str) -> None:
        result = detect_language(text)

        assert result.language is Language.UNKNOWN
        assert result.confidence == 0.0

    def test_low_confidence_becomes_unknown(self) -> None:
        result = detect_language(
            "The delivery was incredibly fast and the packaging was perfect.",
            min_confidence=0.999,
        )

        assert result.language is Language.UNKNOWN

    def test_long_text_is_truncated_without_changing_the_answer(self) -> None:
        """Truncation is a performance optimisation; it must not alter results."""
        sentence = "Die Lieferung war sehr schnell und das Paket kam früher an. "
        short = detect_language(sentence)
        long = detect_language(sentence * 40)

        assert len(sentence * 40) > MAX_TEXT_LENGTH_FOR_DETECTION
        assert long.language is short.language

    def test_batch_detection_matches_single_detection(self) -> None:
        texts = [
            "The delivery was incredibly fast and the packaging was perfect.",
            "Świetna cena, produkt jest tańszy niż u konkurencji.",
        ]

        batch = detect_languages(texts)

        assert [item.language for item in batch] == [detect_language(t).language for t in texts]

    def test_empty_batch_returns_empty(self) -> None:
        assert detect_languages([]) == []


class TestLexiconSentiment:
    def test_is_deterministic(self) -> None:
        backend = LexiconBackend()
        text = "Terrible quality, it broke immediately."

        assert backend.score_one(text) == backend.score_one(text)

    def test_identifies_clear_positive_and_negative(self) -> None:
        backend = LexiconBackend()

        assert backend.score_one("Excellent, delicious and fast").sentiment is Sentiment.POSITIVE
        assert backend.score_one("Terrible, awful and broken").sentiment is Sentiment.NEGATIVE

    def test_text_with_no_cues_is_neutral(self) -> None:
        assert LexiconBackend().score_one("The item is a box.").sentiment is Sentiment.NEUTRAL

    def test_empty_text_is_unknown_not_neutral(self) -> None:
        """ "We could not score this" and "this is neutral" are different facts."""
        assert LexiconBackend().score_one("").sentiment is Sentiment.UNKNOWN

    def test_never_is_not_treated_as_negative(self) -> None:
        """Regression: "never" appears constantly in positive sentences
        ("never had a problem"), and a bag-of-words scorer cannot see the
        negation. It was misclassifying this exact sentence as negative."""
        result = LexiconBackend().score_one("Always in stock, I have never had trouble finding it.")

        assert result.sentiment is not Sentiment.NEGATIVE

    def test_model_version_identifies_the_backend(self) -> None:
        """So lexicon output can never be mistaken for real model output."""
        assert LexiconBackend().model_version == "lexicon-v1"

    def test_scores_a_batch(self) -> None:
        results = score_sentiments(["Excellent product", "Terrible product"], backend="lexicon")

        assert [r.sentiment for r in results] == [Sentiment.POSITIVE, Sentiment.NEGATIVE]

    def test_empty_batch_returns_empty(self) -> None:
        assert score_sentiments([], backend="lexicon") == []


class TestBackendSelection:
    def test_lexicon_backend_is_selectable(self) -> None:
        assert isinstance(get_backend("lexicon"), LexiconBackend)

    def test_transformers_backend_is_selectable(self) -> None:
        assert isinstance(get_backend("transformers", "some/model"), TransformersBackend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown sentiment backend"):
            get_backend("gpt-5")

    def test_backend_is_cached_so_the_model_loads_once(self) -> None:
        assert get_backend("lexicon") is get_backend("lexicon")

    def test_model_version_includes_the_model_name(self) -> None:
        backend = TransformersBackend("cardiffnlp/twitter-xlm-roberta-base-sentiment")

        assert "cardiffnlp" in backend.model_version
        assert backend.model_version.endswith("@transformers")

    def test_a_nonexistent_model_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A silent failure would mark every review `unknown`, which looks like
        a data problem rather than a configuration one.

        `HF_HUB_OFFLINE` makes this fail immediately and deterministically.
        Without it the test reaches the network and spends ~30 seconds
        retrying — which made it slower than the entire rest of the suite and
        would behave differently on a machine with no connection.
        """
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        backend = TransformersBackend("pensieve/definitely-not-a-real-model")

        with pytest.raises(SentimentModelError):
            backend.score_batch(["hello"])


class TestTopicClassification:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("The delivery was three weeks late and the courier lost it", Topic.DELIVERY),
            ("Far too expensive, the price has doubled", Topic.PRICE),
            ("Customer service never replied to my emails", Topic.CUSTOMER_SUPPORT),
            ("Still waiting for a refund six weeks later", Topic.REFUNDS),
            ("The packaging was crushed and the seal was broken", Topic.PACKAGING),
            ("Out of stock for months with no restock date", Topic.AVAILABILITY),
            ("The website crashed twice during checkout", Topic.WEBSITE_EXPERIENCE),
            ("Love that the packaging is recyclable and plastic free", Topic.SUSTAINABILITY),
        ],
    )
    def test_classifies_english_topics(self, text: str, expected: Topic) -> None:
        assert classify_topics(text).primary_topic is expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Dostawa spóźniona o trzy tygodnie", Topic.DELIVERY),
            ("डिलीवरी तीन हफ्ते लेट थी", Topic.DELIVERY),
            ("La livraison est en retard de trois semaines", Topic.DELIVERY),
            ("Die Lieferung war drei Wochen zu spät", Topic.DELIVERY),
            ("La entrega se retrasó tres semanas", Topic.DELIVERY),
        ],
    )
    def test_classifies_across_languages(self, text: str, expected: Topic) -> None:
        """Topic analysis must not be biased by which market a review came from."""
        assert classify_topics(text).primary_topic is expected

    def test_unmatched_text_is_other_not_a_wrong_guess(self) -> None:
        result = classify_topics("Lorem ipsum dolor sit amet consectetur")

        assert result.primary_topic is Topic.OTHER
        assert not result.is_classified

    def test_records_multiple_topics(self) -> None:
        result = classify_topics("The delivery was late and customer service never replied")

        assert len(result.topics) >= 2
        assert Topic.DELIVERY in result.topics
        assert Topic.CUSTOMER_SUPPORT in result.topics

    def test_caps_the_number_of_topics(self) -> None:
        text = "delivery price packaging refund website quality taste stock support recycling"
        result = classify_topics(text, max_topics=3)

        assert len(result.topics) <= 3

    def test_explains_itself(self) -> None:
        """The explanation is most of why this is rules and not a model."""
        result = classify_topics("The courier lost my parcel")

        assert result.reason().startswith("matched:")
        assert "courier" in result.reason() or "parcel" in result.reason()

    def test_other_explains_why_it_matched_nothing(self) -> None:
        assert "no topic keywords" in classify_topics("qwerty asdfgh").reason()

    def test_longer_phrases_win_over_substrings(self) -> None:
        """Regex alternation is first-match-wins, so "customer service" must be
        tried before "service" or it would never match."""
        result = classify_topics("The customer service was excellent")

        assert result.primary_topic is Topic.CUSTOMER_SUPPORT

    def test_keywords_match_whole_words_only(self) -> None:
        """ "priceless" is not about price."""
        assert classify_topics("This is priceless and unmatched").primary_topic is Topic.OTHER

    def test_is_case_insensitive(self) -> None:
        assert classify_topics("THE DELIVERY WAS LATE").primary_topic is Topic.DELIVERY

    def test_empty_text_is_other(self) -> None:
        assert classify_topics("").primary_topic is Topic.OTHER

    def test_every_business_topic_has_keywords(self) -> None:
        business_topics = {t for t in Topic if t is not Topic.OTHER}

        assert set(TOPIC_KEYWORDS) == business_topics

    def test_classify_many_matches_classify_one(self) -> None:
        texts = ["The courier was late", "The price is too high"]

        assert [r.primary_topic for r in classify_many(texts)] == [
            classify_topics(t).primary_topic for t in texts
        ]


class TestEnrichRecords:
    @pytest.fixture
    def validated(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "review_id": ["r1", "r2", "r3"],
                "brand": ["Aurora Foods", "Nimbus Drinks", "Kestrel Home"],
                "product": ["Oat Crunch Cereal", "Cold Brew Coffee", "Ceramic Mug"],
                "country": ["GB", "DE", "PL"],
                "source": ["web", "app", "web"],
                "rating": pd.array([5, 1, 3], dtype="Int8"),
                "created_at": pd.to_datetime(
                    ["2026-05-01T10:00:00Z", "2026-05-02T11:00:00Z", "2026-05-03T12:00:00Z"]
                ),
                "text": [
                    "Delivery was incredibly fast and the packaging was perfect!",
                    "Die Lieferung war schrecklich spät und die Verpackung war kaputt.",
                    "Świetna cena, produkt jest tańszy niż u konkurencji.",
                ],
                "normalized_text": [
                    "Delivery was incredibly fast and the packaging was perfect!",
                    "Die Lieferung war schrecklich spät und die Verpackung war kaputt.",
                    "Świetna cena, produkt jest tańszy niż u konkurencji.",
                ],
            }
        )

    def test_adds_every_enrichment_column(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_records(validated, settings=settings)

        for column in (
            "language",
            "language_confidence",
            "sentiment",
            "sentiment_score",
            "sentiment_model_version",
            "primary_topic",
            "topics",
            "topic_match_reason",
        ):
            assert column in result.columns

    def test_detects_the_right_languages(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_records(validated, settings=settings)

        assert result["language"].tolist() == ["en", "de", "pl"]

    def test_preserves_the_original_text(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_records(validated, settings=settings)

        assert result["text"].tolist() == validated["text"].tolist()

    def test_stamps_the_model_version_on_every_row(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        """Without this, lexicon output and real model output are
        indistinguishable in the warehouse."""
        result = enrich_records(validated, settings=settings)

        assert (result["sentiment_model_version"] == "lexicon-v1").all()

    def test_empty_frame_is_returned_unchanged(self, settings: PipelineSettings) -> None:
        assert enrich_records(pd.DataFrame(), settings=settings).empty


class TestSilverLayer:
    @pytest.fixture
    def validated(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "review_id": ["r1", "r2"],
                "brand": ["Aurora Foods", "Nimbus Drinks"],
                "product": ["Oat Crunch Cereal", "Cold Brew Coffee"],
                "country": ["GB", "DE"],
                "source": ["web", "app"],
                "rating": pd.array([5, 1], dtype="Int8"),
                "created_at": pd.to_datetime(["2026-05-01T10:00:00Z", "2026-05-02T11:00:00Z"]),
                "text": ["Delivery was fast and perfect!", "The courier lost my parcel."],
                "normalized_text": [
                    "Delivery was fast and perfect!",
                    "The courier lost my parcel.",
                ],
                "ingestion_batch_id": ["batch-1", "batch-1"],
            }
        )

    def test_writes_partitioned_by_review_date(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_batch(validated, settings=settings)

        partitions = sorted(p.name for p in settings.silver_path.glob("review_date=*"))
        assert partitions == ["review_date=2026-05-01", "review_date=2026-05-02"]
        assert len(result.silver_paths) == 2

    def test_written_frame_matches_the_silver_contract(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        enrich_batch(validated, settings=settings)
        stored = read_silver(settings.silver_path)

        for column in SILVER_COLUMNS:
            assert column in stored.columns

    def test_stamps_the_processing_version(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        enrich_batch(validated, settings=settings)

        assert (read_silver(settings.silver_path)["processing_version"] == PROCESSING_VERSION).all()

    def test_reads_back_a_date_range(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        """Partition pruning is why Silver is partitioned by review date."""
        enrich_batch(validated, settings=settings)

        subset = read_silver(settings.silver_path, date_from="2026-05-02")

        assert len(subset) == 1
        assert subset.iloc[0]["review_id"] == "r2"

    def test_reading_an_empty_layer_returns_an_empty_frame(
        self, settings: PipelineSettings
    ) -> None:
        assert read_silver(settings.silver_path).empty

    def test_rewrites_a_partition_rather_than_appending(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        """Re-running enrichment after a bug fix must correct Silver, not
        produce two contradictory copies of the same review."""
        enrich_batch(validated, settings=settings)
        enrich_batch(validated, settings=settings)

        assert len(read_silver(settings.silver_path)) == 2

    def test_reports_distributions(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_batch(validated, settings=settings)

        assert sum(result.language_distribution.values()) == 2
        assert sum(result.sentiment_distribution.values()) == 2
        assert result.rows_per_second > 0

    def test_write_can_be_disabled(
        self, validated: pd.DataFrame, settings: PipelineSettings
    ) -> None:
        result = enrich_batch(validated, settings=settings, write=False)

        assert result.silver_paths == []
        assert read_silver(settings.silver_path).empty

    def test_empty_frame_produces_no_partitions(self, settings: PipelineSettings) -> None:
        assert write_silver(pd.DataFrame(), settings.silver_path) == []


@pytest.mark.model
class TestRealModel:
    """Exercises the actual transformer. Skipped in CI via `-m "not model"`."""

    def test_real_model_scores_multilingual_text_correctly(self) -> None:
        results = score_sentiments(
            [
                "Absolutely fantastic, best purchase I have made all year!",
                "Terrible quality, it broke after two days. Very disappointed.",
                "स्वाद बहुत बढ़िया है, बहुत पसंद आया।",
            ],
            backend="transformers",
        )

        assert results[0].sentiment is Sentiment.POSITIVE
        assert results[1].sentiment is Sentiment.NEGATIVE
        assert results[2].sentiment is Sentiment.POSITIVE
        assert all(r.model_version.startswith("cardiffnlp/") for r in results)

    def test_real_model_handles_negation_that_defeats_the_lexicon(self) -> None:
        """The concrete reason the transformer is the default backend."""
        text = "Always in stock, I have never had trouble finding it."

        transformer = score_sentiments([text], backend="transformers")[0]
        lexicon = LexiconBackend().score_one(text)

        assert transformer.sentiment is Sentiment.POSITIVE
        assert lexicon.sentiment is not Sentiment.POSITIVE
