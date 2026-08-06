"""Generate a synthetic review dataset and ingest it into Bronze.

    python scripts/seed_demo_data.py --rows 10000
    python scripts/seed_demo_data.py --rows 1000000 --seed 7
    python scripts/seed_demo_data.py --rows 5000 --format csv --no-ingest

The seed makes output reproducible: the same `--rows` and `--seed` always
produce an identical dataset, so demos, benchmarks and tests all describe the
same data.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - convenience for direct execution
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from pipelines.common.config import get_pipeline_settings  # noqa: E402
from pipelines.common.logging import configure_logging  # noqa: E402
from pipelines.ingestion.generator import (  # noqa: E402
    DEFAULT_SEED,
    DirtyRecordConfig,
    GeneratorConfig,
    generate_reviews,
)
from pipelines.ingestion.service import ingest_file  # noqa: E402


def _write_dataset(frame: pd.DataFrame, path: Path, file_format: str) -> None:
    """Write the generated frame in the requested format."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if file_format == "csv":
        frame.to_csv(path, index=False, encoding="utf-8")
    elif file_format == "json":
        frame.to_json(path, orient="records", indent=2, force_ascii=False)
    elif file_format == "jsonl":
        frame.to_json(path, orient="records", lines=True, force_ascii=False)
    else:
        frame.to_parquet(path, engine="pyarrow", index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate synthetic reviews and ingest them into the Bronze layer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rows", type=int, default=10_000, help="clean rows to generate")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed")
    parser.add_argument("--days", type=int, default=180, help="days of history to span")
    parser.add_argument(
        "--format",
        choices=["csv", "json", "jsonl", "parquet"],
        default="csv",
        help="output file format",
    )
    parser.add_argument("--output", type=Path, default=None, help="output path (default: samples)")
    parser.add_argument(
        "--no-ingest", action="store_true", help="write the file but do not ingest it"
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="generate without injected defects (useful for isolating a bug)",
    )
    parser.add_argument(
        "--no-anomaly",
        action="store_true",
        help="do not inject the rising delivery-complaint trend",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_pipeline_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    if args.rows < 1:
        print("--rows must be at least 1", file=sys.stderr)
        return 2

    config = GeneratorConfig(
        rows=args.rows,
        seed=args.seed,
        days=args.days,
        dirty=DirtyRecordConfig(
            duplicate_rate=0.0,
            missing_text_rate=0.0,
            invalid_rating_rate=0.0,
            broken_date_rate=0.0,
            html_in_text_rate=0.0,
            odd_unicode_rate=0.0,
            excess_whitespace_rate=0.0,
            unsupported_language_rate=0.0,
            missing_brand_rate=0.0,
            very_short_text_rate=0.0,
        )
        if args.clean_only
        else DirtyRecordConfig(),
        inject_anomaly=not args.no_anomaly,
    )

    print(f"Generating {args.rows:,} reviews (seed={args.seed}, {args.days} days of history)...")
    started = time.perf_counter()
    frame = generate_reviews(config=config)
    generate_seconds = time.perf_counter() - started

    output = args.output or (
        settings.samples_path / f"reviews_{args.rows}_seed{args.seed}.{args.format}"
    )
    _write_dataset(frame, output, args.format)
    size_mb = output.stat().st_size / 1e6

    print(
        f"  {len(frame):,} rows written to {output.relative_to(REPO_ROOT)} "
        f"({size_mb:.1f} MB) in {generate_seconds:.2f}s"
    )

    if args.no_ingest:
        print("Skipping ingestion (--no-ingest).")
        return 0

    print("Ingesting into Bronze...")
    result = ingest_file(output, settings=settings, generator_seed=args.seed)

    if result.was_already_ingested:
        print(
            f"  Identical file already ingested as batch {result.batch.batch_id}. "
            "Nothing written (ingestion is idempotent)."
        )
        return 0

    print(
        f"  batch_id   : {result.batch.batch_id}\n"
        f"  rows       : {result.rows_ingested:,}\n"
        f"  throughput : {result.rows_per_second:,.0f} rows/sec\n"
        f"  checksum   : {result.batch.file_checksum[:16]}...\n"
        f"  partition  : {result.partition_path.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
