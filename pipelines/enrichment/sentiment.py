"""Sentiment classification.

**No LLM, no paid API.** A multilingual transformer runs locally on CPU.

Two backends behind one protocol:

    TransformersBackend   the real model, loaded once, batched inference
    LexiconBackend        deterministic keyword scorer, no download

The lexicon backend exists because the real model is ~1.1 GB. CI must never
download it, and a unit test suite that loads a transformer takes minutes
instead of seconds. It is **not** pretending to be the real model — every row
records `sentiment_model_version`, so `lexicon-v1` output can never be mistaken
for `cardiffnlp/twitter-xlm-roberta-base-sentiment@transformers` output in a
dashboard or a benchmark.

Model choice is discussed in docs/implementation-plan.md. The short version:
XLM-RoBERTa fine-tuned on ~198M multilingual tweets, so it is trained on short
informal text — which is what reviews are — and it emits three classes
directly rather than 1-5 stars that would partly duplicate our `rating` column.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pipelines.common.domain import Sentiment
from pipelines.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

log = get_logger(__name__)

#: Truncation limit for model input. XLM-R's positional limit is 512 tokens;
#: characters are a cheap proxy that avoids tokenising twice just to measure.
MAX_MODEL_CHARS = 1200


@dataclass(frozen=True, slots=True)
class SentimentResult:
    """One review's sentiment."""

    sentiment: Sentiment
    score: float
    model_version: str

    @property
    def is_confident(self) -> bool:
        return self.score >= 0.6


class SentimentBackend(Protocol):
    """What any sentiment implementation must provide."""

    @property
    def model_version(self) -> str:
        """Identifies exactly what produced a score. Stored on every row."""
        ...

    def score_batch(self, texts: Sequence[str]) -> list[SentimentResult]:
        """Score many texts at once."""
        ...


# ---------------------------------------------------------------------------
# Lexicon backend
# ---------------------------------------------------------------------------

# Deliberately small and multilingual. This is not trying to be a good
# sentiment model — it is trying to be a *deterministic* one that needs no
# download, so tests assert on pipeline behaviour rather than model behaviour.
_POSITIVE_TERMS: frozenset[str] = frozenset(
    {
        # en
        "great",
        "excellent",
        "delicious",
        "fantastic",
        "love",
        "perfect",
        "good",
        "helpful",
        "fast",
        "quick",
        "sturdy",
        "outstanding",
        "lovely",
        "easy",
        "recommend",
        "durable",
        "recyclable",
        "sustainable",
        # pl
        "świetna",
        "wyśmienity",
        "doskonała",
        "solidne",
        "szybka",
        "dobra",
        # hi
        "बढ़िया",
        "अच्छी",
        "शानदार",
        "तेज़",
        "स्वादिष्ट",
        "मजबूत",
        # fr
        "délicieux",
        "solide",
        "rapide",
        "bon",
        "remarquable",
        # de
        "hervorragend",
        "stabile",
        "schnell",
        "gut",
        "sehr",
        # es
        "excelente",
        "delicioso",
        "resistente",
        "rapidísimo",
        "buena",
        "bien",
    }
)

_NEGATIVE_TERMS: frozenset[str] = frozenset(
    {
        # en
        # "never" is deliberately absent: a bag-of-words scorer cannot see
        # negation, and "never had a problem" / "never disappointed" are
        # positive. It was misclassifying "Always in stock, I have never had
        # trouble finding it" as negative. Handling negation properly is the
        # transformer's job, which is why the transformer is the default.
        "terrible",
        "awful",
        "poor",
        "broke",
        "broken",
        "late",
        "slow",
        "expensive",
        "overpriced",
        "bitter",
        "bland",
        "crushed",
        "waste",
        "refused",
        "crashed",
        "worst",
        "disappointed",
        # pl
        "okropny",
        "kiepska",
        "drogo",
        "spóźniona",
        "zgniecione",
        "gorzki",
        # hi
        "खराब",
        "महँगा",
        "टूटी",
        "लेट",
        "कड़वा",
        # fr
        "affreux",
        "mauvaise",
        "cher",
        "retard",
        "amer",
        "cassé",
        "écrasé",
        # de
        "schrecklich",
        "schlechte",
        "teuer",
        "spät",
        "kaputt",
        # es
        "horrible",
        "mala",
        "caro",
        "retrasó",
        "amargo",
        "rompió",
        "aplastado",
    }
)

_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


class LexiconBackend:
    """Deterministic keyword scorer. No model, no download, no network.

    Used by tests and CI. Accurate enough to be sane on the synthetic data
    (whose templates contain these very words) and fast enough to be free.
    """

    @property
    def model_version(self) -> str:
        return "lexicon-v1"

    def score_one(self, text: str) -> SentimentResult:
        if not text:
            return SentimentResult(Sentiment.UNKNOWN, 0.0, self.model_version)

        tokens = {token.casefold() for token in _TOKEN.findall(text)}
        positives = len(tokens & _POSITIVE_TERMS)
        negatives = len(tokens & _NEGATIVE_TERMS)
        total = positives + negatives

        if total == 0:
            return SentimentResult(Sentiment.NEUTRAL, 0.5, self.model_version)

        if positives > negatives:
            return SentimentResult(
                Sentiment.POSITIVE, round(0.5 + 0.5 * positives / total, 4), self.model_version
            )
        if negatives > positives:
            return SentimentResult(
                Sentiment.NEGATIVE, round(0.5 + 0.5 * negatives / total, 4), self.model_version
            )
        return SentimentResult(Sentiment.NEUTRAL, 0.5, self.model_version)

    def score_batch(self, texts: Sequence[str]) -> list[SentimentResult]:
        return [self.score_one(text) for text in texts]


# ---------------------------------------------------------------------------
# Transformers backend
# ---------------------------------------------------------------------------

# Cardiff models expose labels as LABEL_0/1/2 rather than readable names, and
# the ordering is a property of the checkpoint, not a convention. Mapping it
# explicitly — and asserting at load time — means a model swap that changes the
# order fails loudly instead of silently inverting every sentiment in the
# dashboard.
_CARDIFF_LABEL_MAP: dict[str, Sentiment] = {
    "label_0": Sentiment.NEGATIVE,
    "label_1": Sentiment.NEUTRAL,
    "label_2": Sentiment.POSITIVE,
    "negative": Sentiment.NEGATIVE,
    "neutral": Sentiment.NEUTRAL,
    "positive": Sentiment.POSITIVE,
}


class SentimentModelError(RuntimeError):
    """Raised when the model cannot be loaded at all."""


class TransformersBackend:
    """The real multilingual transformer, loaded once per process."""

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._pipeline: object | None = None

    @property
    def model_version(self) -> str:
        return f"{self._model_name}@transformers"

    def _ensure_loaded(self) -> object:
        """Load the model on first use and keep it.

        Loading is seconds of work and about 1.1 GB of RAM. Doing it per batch
        — never mind per review — would make the pipeline unusable.
        """
        if self._pipeline is not None:
            return self._pipeline

        # Export HF_HOME before importing transformers — the library reads
        # os.environ at import time, so a value living only in `.env` is
        # silently ignored and the model lands in the default cache.
        from pipelines.common.config import get_pipeline_settings

        get_pipeline_settings().apply_hf_home()

        try:
            from transformers import pipeline as hf_pipeline
        except ImportError as exc:
            raise SentimentModelError(
                "transformers is not installed. Run: pip install -e '.[nlp]', "
                "or set PENSIEVE_SENTIMENT_BACKEND=lexicon."
            ) from exc

        # Let torch use every physical core. It sometimes defaults to a single
        # thread in a fresh process, which silently halves or worse the
        # throughput of CPU inference.
        try:
            import os

            import torch

            cores = os.cpu_count() or 1
            if torch.get_num_threads() < cores:
                torch.set_num_threads(cores)
            log.info("torch_threads_set", threads=torch.get_num_threads(), cpu_count=cores)
        except ImportError:  # pragma: no cover - torch ships with transformers here
            pass

        log.info("sentiment_model_loading", model=self._model_name)
        try:
            classifier = hf_pipeline(
                # "text-classification" is the canonical task name.
                # "sentiment-analysis" is a legacy alias for the same thing and
                # is absent from the typed overloads, so it fails type checking
                # while working perfectly at runtime.
                "text-classification",
                model=self._model_name,
                tokenizer=self._model_name,
                truncation=True,
                max_length=512,
                top_k=None,
                # Essential: without `batch_size`, passing a list to a
                # transformers pipeline processes the items **one at a time**.
                # It looks batched, runs sequentially, and is the difference
                # between ~10 and ~100 reviews per second on CPU.
                batch_size=self._batch_size,
            )
        except Exception as exc:
            raise SentimentModelError(
                f"Could not load sentiment model {self._model_name!r}: {exc}"
            ) from exc

        self._verify_labels(classifier)
        self._pipeline = classifier
        log.info("sentiment_model_ready", model=self._model_name)
        return classifier

    def _verify_labels(self, classifier: object) -> None:
        """Fail loudly if the model's labels are not ones we can map.

        A model whose labels we silently fail to recognise would mark every
        review `unknown`, which looks like a data problem rather than a
        configuration problem and wastes a great deal of debugging time.
        """
        config = getattr(getattr(classifier, "model", None), "config", None)
        id2label = getattr(config, "id2label", None)
        if not id2label:
            log.warning("sentiment_labels_unknown", model=self._model_name)
            return

        unmapped = [label for label in id2label.values() if label.lower() not in _CARDIFF_LABEL_MAP]
        if unmapped:
            raise SentimentModelError(
                f"Model {self._model_name!r} has labels this pipeline cannot map: "
                f"{unmapped}. Known labels: {sorted(_CARDIFF_LABEL_MAP)}."
            )
        log.info("sentiment_labels_verified", labels=list(id2label.values()))

    def score_batch(self, texts: Sequence[str]) -> list[SentimentResult]:
        """Score texts in batches.

        Texts are **sorted by length before batching and restored afterwards**.
        Transformers pad every item in a batch to the longest one in it, so a
        batch mixing a 10-word review with a 200-word review does 20x the
        necessary work on the short one. Grouping similar lengths together
        removes most of that waste, and the sort is O(n log n) against
        inference that costs orders of magnitude more.

        A failure in one batch marks only that batch `unknown` and continues.
        One malformed review must not discard the sentiment of a million
        others.
        """
        if not texts:
            return []

        classifier = self._ensure_loaded()

        prepared = [(text or "")[:MAX_MODEL_CHARS] or " " for text in texts]
        # Keep the original position so results can be put back in order.
        order = sorted(range(len(prepared)), key=lambda index: len(prepared[index]))

        scored: list[SentimentResult | None] = [None] * len(prepared)

        for start in range(0, len(order), self._batch_size):
            positions = order[start : start + self._batch_size]
            chunk = [prepared[position] for position in positions]
            try:
                raw = classifier(chunk)  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001 - degrade, never abort
                log.warning(
                    "sentiment_batch_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    batch_start=start,
                    batch_size=len(chunk),
                )
                for position in positions:
                    scored[position] = SentimentResult(Sentiment.UNKNOWN, 0.0, self.model_version)
                continue

            for position, entry in zip(positions, raw, strict=True):
                scored[position] = self._interpret(entry)

        return [
            result or SentimentResult(Sentiment.UNKNOWN, 0.0, self.model_version)
            for result in scored
        ]

    def _interpret(self, scores: object) -> SentimentResult:
        """Turn one model output into a SentimentResult.

        With `top_k=None` the pipeline returns every class per input, so we
        take the highest — which also gives a meaningful confidence rather
        than a bare label.
        """
        if isinstance(scores, dict):
            scores = [scores]
        if not isinstance(scores, list) or not scores:
            return SentimentResult(Sentiment.UNKNOWN, 0.0, self.model_version)

        best = max(scores, key=lambda item: float(item.get("score", 0.0)))
        label = str(best.get("label", "")).lower()
        sentiment = _CARDIFF_LABEL_MAP.get(label, Sentiment.UNKNOWN)
        return SentimentResult(
            sentiment, round(float(best.get("score", 0.0)), 4), self.model_version
        )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=4)
def get_backend(
    backend: str = "transformers",
    model_name: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment",
    batch_size: int = 32,
) -> SentimentBackend:
    """Return the configured backend, cached so the model loads once."""
    if backend == "lexicon":
        return LexiconBackend()
    if backend == "transformers":
        return TransformersBackend(model_name, batch_size)
    raise ValueError(f"Unknown sentiment backend {backend!r}. Use 'transformers' or 'lexicon'.")


def score_sentiments(
    texts: Sequence[str],
    *,
    backend: str = "transformers",
    model_name: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment",
    batch_size: int = 32,
) -> list[SentimentResult]:
    """Score a list of texts with the configured backend."""
    if not texts:
        return []

    implementation = get_backend(backend, model_name, batch_size)
    results = implementation.score_batch(texts)

    distribution: dict[str, int] = {}
    for result in results:
        distribution[result.sentiment.value] = distribution.get(result.sentiment.value, 0) + 1
    log.info(
        "sentiment_scored",
        rows=len(results),
        model_version=implementation.model_version,
        distribution=distribution,
    )
    return results
