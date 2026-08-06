"""Text normalisation and feature extraction.

Small, pure, individually testable functions. Each does one thing, so a bug in
whitespace handling cannot hide inside a 200-line "clean_text" monolith.

**The original text is never modified.** `normalized_text` is an additional
column; the raw `text` travels alongside it all the way to the dashboard, where
the review drawer shows both.

A deliberate restraint runs through this module: we clean *structure*, not
*expression*. HTML, zero-width characters and broken whitespace are noise and
get removed. Emoji, capitals, exclamation marks and repeated letters are
sentiment signal and are preserved — normalising "TERRIBLE!!!" into "terrible."
would delete the very intensity the sentiment model exists to detect.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

# --- Patterns ---------------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]{1,200}>")
_HTML_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,10}|#\d{1,6}|#x[0-9a-fA-F]{1,6});")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"']{2,2000}", re.IGNORECASE)
_MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9_]{2,30})\b")
_EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,4}")

# Characters that carry no meaning but break tokenisation and comparison:
# zero-width spaces, byte-order marks, soft hyphens, directional marks.
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")

# Any run of whitespace, including non-breaking and ideographic spaces.
_WHITESPACE = re.compile(r"[\s   -     　]+")

# Three or more of the same punctuation mark in a row.
_REPEATED_PUNCTUATION = re.compile(r"([!?.,;:—-])\1{2,}")

# Word counting is done by whitespace tokenisation, not a `\b`-anchored regex.
# `\w` does not match Unicode combining marks (category Mn), so a pattern like
# `\b\w[\w'-]*\b` splits Devanagari words in two at the virama or nukta —
# "स्वाद बहुत बढ़िया है" counts as 8 words instead of 4. Splitting on whitespace
# and keeping tokens that contain at least one alphanumeric character is
# correct across every script we support.
_HAS_ALNUM = re.compile(r"\w", re.UNICODE)

# Emoji and pictographic ranges. Matched by codepoint rather than by a library
# so the pipeline gains no dependency for a feature this narrow.
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f700-\U0001f77f"
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000027bf"  # misc symbols & dingbats
    "\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "]",
    flags=re.UNICODE,
)

URL_PLACEHOLDER: Final[str] = " <url> "
MENTION_PLACEHOLDER: Final[str] = " <mention> "
EMAIL_PLACEHOLDER: Final[str] = " <email> "


def _as_text(value: object) -> str:
    """Coerce any input to a string, treating every missing marker as empty.

    This module is called through `Series.map()`, which hands over **`pd.NA`**
    for missing values — not `None`. `pd.NA` raises `TypeError` on truth
    testing, so a plain `if not text:` guard blows up on real data while
    passing every test that only feeds it `None`.

    Checking `isinstance(value, str)` covers `None`, `pd.NA`, `float('nan')`
    and anything else non-textual in one go, and keeps this module free of a
    pandas import.
    """
    return value if isinstance(value, str) else ""


# --- Individual cleaning steps ----------------------------------------------


def normalize_unicode(text: object) -> str:
    """Apply NFKC normalisation and strip invisible characters.

    NFKC folds compatibility forms — full-width "Ｔｈｉｓ" becomes "This",
    ligatures decompose — so two visually identical strings compare equal. That
    matters for deduplication, which would otherwise treat them as distinct.
    """
    source = _as_text(text)
    if not source:
        return ""
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", source))


def strip_html(text: object) -> str:
    """Remove HTML tags and decode common entities.

    Script and style blocks are removed *with their contents*; other tags are
    unwrapped so the text inside survives. Removing `<b>great</b>` entirely
    would delete a real word.
    """
    source = _as_text(text)
    if not source:
        return ""
    cleaned = _SCRIPT_OR_STYLE.sub(" ", source)
    cleaned = _HTML_TAG.sub(" ", cleaned)
    return _HTML_ENTITY.sub(_decode_entity, cleaned)


_ENTITIES: Final[dict[str, str]] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": " ",
    "&#39;": "'",
    "&#34;": '"',
}


def _decode_entity(match: re.Match[str]) -> str:
    entity = match.group(0)
    if entity in _ENTITIES:
        return _ENTITIES[entity]
    if entity.startswith("&#"):
        try:
            code = int(entity[3:-1], 16) if entity[2] in "xX" else int(entity[2:-1])
        except ValueError:
            return " "
        else:
            return chr(code) if 0 < code < 0x110000 else " "
    return " "


def normalize_whitespace(text: object) -> str:
    """Collapse every run of whitespace into a single space and trim."""
    source = _as_text(text)
    if not source:
        return ""
    return _WHITESPACE.sub(" ", source).strip()


def collapse_repeated_punctuation(text: object, keep: int = 2) -> str:
    """Shorten runs of repeated punctuation, keeping some for tone.

    "Terrible!!!!!!!" becomes "Terrible!!" rather than "Terrible!". Collapsing
    to a single mark would erase intensity that both a human reader and the
    sentiment model use.
    """
    source = _as_text(text)
    if not source:
        return ""
    return _REPEATED_PUNCTUATION.sub(lambda m: m.group(1) * keep, source)


def replace_urls(text: object) -> str:
    """Swap URLs for a placeholder token."""
    source = _as_text(text)
    return _URL.sub(URL_PLACEHOLDER, source) if source else ""


def replace_mentions(text: object) -> str:
    """Swap @handles for a placeholder token."""
    source = _as_text(text)
    return _MENTION.sub(MENTION_PLACEHOLDER, source) if source else ""


def replace_emails(text: object) -> str:
    """Swap email addresses for a placeholder token.

    Also a small privacy win: an address typed into a review body does not need
    to persist into the analytics layer.
    """
    source = _as_text(text)
    return _EMAIL.sub(EMAIL_PLACEHOLDER, source) if source else ""


# --- Feature extraction -----------------------------------------------------


def count_words(text: object) -> int:
    """Count word-like tokens, correctly across scripts.

    A token counts when it holds at least one word character, so trailing
    punctuation ("great!") and standalone marks ("—") do not inflate the count.
    """
    source = _as_text(text)
    if not source:
        return 0
    return sum(1 for token in source.split() if _HAS_ALNUM.search(token))


def count_characters(text: object) -> int:
    return len(_as_text(text))


def count_emoji(text: object) -> int:
    """Count emoji, a genuine sentiment signal in short reviews."""
    return len(_EMOJI.findall(_as_text(text)))


def count_exclamations(text: object) -> int:
    return _as_text(text).count("!")


def uppercase_ratio(text: object) -> float:
    """Fraction of cased letters that are uppercase.

    Computed over *cased* characters only, so digits, punctuation and scripts
    without case (Devanagari, for example) do not distort it. A Hindi review
    would otherwise always score 0 and look artificially calm.
    """
    source = _as_text(text)
    if not source:
        return 0.0
    cased = [char for char in source if char.isalpha() and (char.islower() or char.isupper())]
    if not cased:
        return 0.0
    return sum(1 for char in cased if char.isupper()) / len(cased)


def has_url(text: object) -> bool:
    source = _as_text(text)
    return bool(_URL.search(source)) if source else False


def has_mention(text: object) -> bool:
    source = _as_text(text)
    return bool(_MENTION.search(source)) if source else False


def is_effectively_empty(text: object) -> bool:
    """True when the text has no meaningful content.

    Whitespace-only, invisible-character-only and HTML-only strings all count
    as empty — `"<p>   </p>"` contains no review. Missing values in any of
    their forms (`None`, `pd.NA`, `NaN`) count as empty too.
    """
    source = _as_text(text)
    if not source:
        return True
    return not normalize_whitespace(strip_html(normalize_unicode(source)))


# --- Composition ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextFeatures:
    """Derived text metrics, computed on the normalised text."""

    word_count: int
    character_count: int
    emoji_count: int
    exclamation_count: int
    uppercase_ratio: float
    has_url: bool
    has_mention: bool


def normalize_text(text: object) -> str:
    """Run the full cleaning pipeline and return the normalised text.

    Order matters: Unicode first so that later patterns see canonical
    characters; HTML before whitespace so unwrapped tags leave collapsible
    gaps; placeholders before the final whitespace pass so their padding is
    tidied up.
    """
    source = _as_text(text)
    if not source:
        return ""

    cleaned = normalize_unicode(source)
    cleaned = strip_html(cleaned)
    cleaned = replace_urls(cleaned)
    cleaned = replace_emails(cleaned)
    cleaned = replace_mentions(cleaned)
    cleaned = collapse_repeated_punctuation(cleaned)
    return normalize_whitespace(cleaned)


def extract_features(text: object) -> TextFeatures:
    """Compute derived features.

    Deliberately measured on the *original* text, not the normalised one: the
    point of `uppercase_ratio` and `emoji_count` is to describe how the
    customer actually wrote, and normalisation would flatten exactly that.
    """
    source = _as_text(text)
    return TextFeatures(
        word_count=count_words(source),
        character_count=count_characters(source),
        emoji_count=count_emoji(source),
        exclamation_count=count_exclamations(source),
        uppercase_ratio=round(uppercase_ratio(source), 4),
        has_url=has_url(source),
        has_mention=has_mention(source),
    )
