"""Readers for the supported source formats.

Every reader returns a DataFrame in which **all columns are strings** and no
value has been coerced, parsed or dropped. That is the whole point of the
Bronze layer: a rating of `"seven"` and a date of `"not-a-date"` must survive
ingestion intact so they can later be quarantined with their original value
attached. Parsing here would destroy the evidence.

pandas is used deliberately — these are single files being read once, which is
exactly the small-file case pandas is good at. PySpark enters at the Gold stage
where the work is genuinely distributed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from pipelines.common.logging import get_logger
from pipelines.ingestion.batch import UnsupportedFormatError, validate_source_format

log = get_logger(__name__)


class EmptySourceError(ValueError):
    """Raised when a source file parses correctly but contains no rows."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Source file {path.name!r} contains no records.")
        self.path = path


class MalformedSourceError(ValueError):
    """Raised when a file cannot be parsed as its extension claims."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Could not parse {path.name!r}: {reason}")
        self.path = path
        self.reason = reason


def _stringify(frame: pd.DataFrame) -> pd.DataFrame:
    """Force every column to a nullable string dtype without altering values.

    `convert_dtypes` is avoided on purpose — it would infer types and silently
    turn `"5"` into an integer, defeating the raw-preservation guarantee.
    """
    return frame.astype("string")


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV with every column kept as text.

    `keep_default_na=False` is essential: without it pandas converts the
    literal strings "NA", "null", "None" and "" into NaN, so a review whose
    text is genuinely the word "None" would become indistinguishable from a
    missing value.
    """
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            on_bad_lines="warn",
        )
    except UnicodeDecodeError:
        # Real-world exports are not always UTF-8. Fall back to latin-1, which
        # cannot fail, and record that we did so.
        log.warning("csv_encoding_fallback", path=str(path), fallback="latin-1")
        frame = pd.read_csv(
            path, dtype=str, keep_default_na=False, na_values=[], encoding="latin-1"
        )
    except pd.errors.ParserError as exc:
        raise MalformedSourceError(path, str(exc)) from exc
    return _stringify(frame)


def read_json(path: Path) -> pd.DataFrame:
    """Read a JSON file containing either an array of objects or a single object."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedSourceError(path, str(exc)) from exc

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise MalformedSourceError(path, "expected a JSON array or object at the top level")

    return _stringify(pd.DataFrame(payload).astype("string"))


def read_jsonl(path: Path) -> pd.DataFrame:
    """Read newline-delimited JSON, one object per line.

    A malformed line is reported with its line number rather than a generic
    parse error — when one line in a million-line export is broken, knowing
    which line saves a great deal of time.
    """
    records: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise MalformedSourceError(path, f"line {line_number}: {exc}") from exc
                if not isinstance(record, dict):
                    raise MalformedSourceError(path, f"line {line_number}: expected an object")
                records.append(record)
    except UnicodeDecodeError as exc:
        raise MalformedSourceError(path, str(exc)) from exc

    return _stringify(pd.DataFrame(records).astype("string"))


def read_parquet(path: Path) -> pd.DataFrame:
    """Read Parquet and cast every column to string for Bronze consistency."""
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        raise MalformedSourceError(path, str(exc)) from exc
    return _stringify(frame)


_READERS: dict[str, Callable[[Path], pd.DataFrame]] = {
    "csv": read_csv,
    "json": read_json,
    "jsonl": read_jsonl,
    "parquet": read_parquet,
}


def read_source(path: Path) -> pd.DataFrame:
    """Read any supported source file into an all-string DataFrame.

    Raises:
        UnsupportedFormatError: the extension is not one we handle.
        MalformedSourceError: the file could not be parsed.
        EmptySourceError: the file parsed but held no rows.
        FileNotFoundError: the path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    source_format = validate_source_format(path)
    reader = _READERS.get(source_format)
    if reader is None:  # pragma: no cover - guarded by validate_source_format
        raise UnsupportedFormatError(path.suffix)

    frame = reader(path)
    if frame.empty:
        raise EmptySourceError(path)

    log.info(
        "source_read",
        path=str(path),
        source_format=source_format,
        rows=len(frame),
        columns=list(frame.columns),
    )
    return frame
