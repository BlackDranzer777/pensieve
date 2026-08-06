"""Language detection with Lingua.

Lingua is chosen over langdetect and fastText for one reason that matters here:
**it reports a confidence value and is accurate on short text.** Reviews are
often a single sentence, and the classic n-gram detectors become unreliable
below about 20 words — exactly the range most of our data sits in.

Three outcomes, and the distinction between them is deliberate:

    `en` / `pl` / `hi` / `fr` / `de` / `es`  detected, confident, supported
    `unsupported`                           confidently a language we do not support
    `unknown`                               below the confidence threshold

Collapsing the last two into one bucket would hide a real difference. A
confident Italian review means "we should consider supporting Italian";
a low-confidence result means "this text is too short or too noisy to call".
Those lead to different decisions, so they get different values.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from lingua import Language as LinguaLanguage
from lingua import LanguageDetector, LanguageDetectorBuilder

from pipelines.common.domain import SUPPORTED_LANGUAGES, Language
from pipelines.common.logging import get_logger

log = get_logger(__name__)

# The six languages the platform supports end to end, mapped to Lingua's enum.
_SUPPORTED_LINGUA: dict[LinguaLanguage, Language] = {
    LinguaLanguage.ENGLISH: Language.ENGLISH,
    LinguaLanguage.POLISH: Language.POLISH,
    LinguaLanguage.HINDI: Language.HINDI,
    LinguaLanguage.FRENCH: Language.FRENCH,
    LinguaLanguage.GERMAN: Language.GERMAN,
    LinguaLanguage.SPANISH: Language.SPANISH,
}

# Languages we do NOT support but want to recognise, so an Italian review is
# reported as `unsupported` rather than being force-fitted to the nearest
# supported language. Without these in the detector's candidate set, Lingua
# would have to pick from our six and would confidently return the wrong one.
_RECOGNISED_OTHERS: tuple[LinguaLanguage, ...] = (
    LinguaLanguage.ITALIAN,
    LinguaLanguage.PORTUGUESE,
    LinguaLanguage.DUTCH,
    LinguaLanguage.DANISH,
    LinguaLanguage.SWEDISH,
    LinguaLanguage.ROMANIAN,
    LinguaLanguage.CZECH,
    LinguaLanguage.TURKISH,
    LinguaLanguage.INDONESIAN,
    LinguaLanguage.VIETNAMESE,
)

#: Below this many characters, detection is unreliable regardless of what the
#: confidence says. "ok" is not enough signal to identify a language.
MIN_TEXT_LENGTH_FOR_DETECTION = 8

#: Detection cost scales with text length, and language is identifiable long
#: before a review ends. Measured on 4,729 real reviews, truncating here cut
#: detection from 10.6s to well under half that with no change in the
#: distribution. A whole review is simply more evidence than the question needs.
MAX_TEXT_LENGTH_FOR_DETECTION = 300


@dataclass(frozen=True, slots=True)
class LanguageResult:
    """Outcome of detecting one review's language."""

    language: Language
    confidence: float
    #: What Lingua actually said, before our supported/unsupported mapping.
    #: Kept for explainability: "we called this unsupported because Lingua said
    #: Italian at 0.94" is a far better answer than "unsupported".
    detected_name: str | None = None

    @property
    def is_supported(self) -> bool:
        return self.language in SUPPORTED_LANGUAGES


@functools.lru_cache(maxsize=1)
def get_detector() -> LanguageDetector:
    """Build the Lingua detector once per process.

    Construction loads statistical models for every candidate language and is
    slow — on the order of seconds. Doing it per review would dominate the
    runtime of the whole pipeline.

    `with_preloaded_language_models()` front-loads that cost at build time
    instead of paying it lazily on the first detection, which keeps the first
    batch from looking anomalously slow in benchmarks.
    """
    languages = [*_SUPPORTED_LINGUA.keys(), *_RECOGNISED_OTHERS]
    log.info("lingua_detector_building", candidate_languages=len(languages))
    detector = (
        LanguageDetectorBuilder.from_languages(*languages).with_preloaded_language_models().build()
    )
    log.info("lingua_detector_ready")
    return detector


def detect_language(text: str, *, min_confidence: float = 0.65) -> LanguageResult:
    """Detect the language of one review.

    Args:
        text: Normalised review text.
        min_confidence: Below this, the result is `unknown`.

    Returns:
        A `LanguageResult`. Never raises — a detection failure returns
        `unknown` rather than killing a batch of 100,000 records.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH_FOR_DETECTION:
        return LanguageResult(Language.UNKNOWN, 0.0)

    sample = text[:MAX_TEXT_LENGTH_FOR_DETECTION]
    try:
        confidences = get_detector().compute_language_confidence_values(sample)
    except Exception as exc:  # noqa: BLE001 - one bad row must not stop the batch
        log.warning("language_detection_failed", error=str(exc), error_type=type(exc).__name__)
        return LanguageResult(Language.UNKNOWN, 0.0)

    if not confidences:
        return LanguageResult(Language.UNKNOWN, 0.0)

    best = confidences[0]
    confidence = float(best.value)
    detected_name = best.language.name.lower()

    if confidence < min_confidence:
        return LanguageResult(Language.UNKNOWN, confidence, detected_name)

    mapped = _SUPPORTED_LINGUA.get(best.language)
    if mapped is None:
        # Confidently a real language, just not one we support end to end.
        return LanguageResult(Language.UNSUPPORTED, confidence, detected_name)

    return LanguageResult(mapped, confidence, detected_name)


def detect_languages(texts: list[str], *, min_confidence: float = 0.65) -> list[LanguageResult]:
    """Detect languages for many reviews.

    Lingua has no batch API, so this is a loop — but it builds the detector
    once via the cached factory, which is where the real cost lives.
    """
    if not texts:
        return []

    get_detector()  # pay the build cost once, before the loop
    results = [detect_language(text, min_confidence=min_confidence) for text in texts]

    distribution: dict[str, int] = {}
    for result in results:
        distribution[result.language.value] = distribution.get(result.language.value, 0) + 1
    log.info("languages_detected", rows=len(results), distribution=distribution)

    return results
