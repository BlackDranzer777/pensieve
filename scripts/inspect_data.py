"""Show what is actually sitting in each layer of the pipeline.

    python scripts/inspect_data.py             # every layer, summary
    python scripts/inspect_data.py --layer silver
    python scripts/inspect_data.py --rows 10   # more sample rows

Read-only. It opens Parquet through DuckDB and prints what it finds, so the
numbers here are whatever is on disk right now — not values recorded when a
pipeline last ran.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - direct execution convenience
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from pipelines.common.config import get_pipeline_settings  # noqa: E402

LAYERS = ("samples", "bronze", "quarantine", "silver", "gold")

#: The eight Gold datasets, in the order the Gold job builds them.
GOLD_DATASETS = (
    "daily_brand_metrics",
    "daily_topic_metrics",
    "country_metrics",
    "language_distribution",
    "sentiment_trends",
    "anomalies",
    "data_quality_metrics",
    "pipeline_run_metrics",
)


def heading(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def show(frame: pd.DataFrame) -> None:
    """Print a frame without pandas truncating it into uselessness."""
    if frame.empty:
        print("  (no rows)")
        return
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print("  " + frame.to_string(index=False).replace("\n", "\n  "))


def query(sql: str) -> pd.DataFrame:
    return duckdb.sql(sql).to_df()


def glob_for(root: Path) -> str:
    """DuckDB-friendly recursive glob. Forward slashes work on Windows too."""
    return f"{root.as_posix()}/**/*.parquet"


def parquet_exists(root: Path) -> bool:
    return root.exists() and any(root.rglob("*.parquet"))


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------


def inspect_samples(root: Path, rows: int) -> None:
    heading("RAW INPUT  —  what the generator produced (CSV)")
    files = sorted(root.glob("reviews_*"))
    if not files:
        print("  No generated files. Run:  python scripts/seed_demo_data.py")
        return

    for path in files:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"\n  {path.name}   {size_mb:.1f} MB")

    latest = files[-1]
    print(f"\n  First {rows} rows of {latest.name}:")
    frame = pd.read_csv(latest, nrows=rows, keep_default_na=False, dtype=str)
    frame["text"] = frame["text"].str.slice(0, 60) + "..."
    show(frame)
    print("\n  This is the messy input. Everything below is derived from it.")


def inspect_bronze(root: Path, rows: int) -> None:
    heading("BRONZE  —  raw landed as Parquet, nothing changed")
    if not parquet_exists(root):
        print("  Empty. Run:  python scripts/seed_demo_data.py")
        return

    source = glob_for(root)
    total = query(f"SELECT count(*) AS rows FROM read_parquet('{source}')")
    print(f"\n  rows: {int(total['rows'][0]):,}")

    print("\n  Batches (Bronze is append-only, so re-ingesting is a no-op):")
    show(
        query(
            f"""
            SELECT ingestion_batch_id, source_file, source_format, count(*) AS rows,
                   min(ingestion_timestamp) AS ingested_at
            FROM read_parquet('{source}', hive_partitioning = true)
            GROUP BY ingestion_batch_id, source_file, source_format
            ORDER BY ingested_at
            """
        )
    )

    print(f"\n  {rows} rows, with the lineage columns ingestion added:")
    show(
        query(
            f"""
            SELECT review_id, brand, country, rating,
                   ingestion_batch_id, source_row_number, ingestion_timestamp
            FROM read_parquet('{source}') LIMIT {rows}
            """
        )
    )


def inspect_quarantine(root: Path, rows: int) -> None:
    heading("QUARANTINE  —  records rejected, and why")
    if not parquet_exists(root):
        print("  Empty. Either nothing was rejected, or the pipeline has not run.")
        return

    source = glob_for(root)
    total = query(f"SELECT count(*) AS rows FROM read_parquet('{source}')")
    print(f"\n  rows: {int(total['rows'][0]):,}   (nothing is silently dropped)")

    print("\n  Why each one failed:")
    show(
        query(
            f"""
            SELECT rule_id, severity, failed_field, count(*) AS rows,
                   any_value(failure_reason) AS example_reason
            FROM read_parquet('{source}')
            GROUP BY rule_id, severity, failed_field ORDER BY rows DESC
            """
        )
    )

    print(f"\n  {rows} rejected records, original values kept intact:")
    show(
        query(
            f"""
            SELECT review_id, rule_id, failed_field,
                   substr(coalesce(failed_value, '<null>'), 1, 30) AS failed_value
            FROM read_parquet('{source}') LIMIT {rows}
            """
        )
    )


def inspect_silver(root: Path, rows: int) -> None:
    heading("SILVER  —  cleaned and enriched, one row per review")
    if not parquet_exists(root):
        print("  Empty. Run:  python -m pipelines.jobs.run_pipeline")
        return

    source = glob_for(root)
    summary = query(
        f"""
        SELECT count(*) AS rows,
               count(DISTINCT brand) AS brands,
               min(review_date) AS first_day,
               max(review_date) AS last_day,
               count(DISTINCT content_fingerprint) AS unique_texts,
               cast(sum(CASE WHEN is_duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS int)
                   AS marked_duplicate
        FROM read_parquet('{source}', hive_partitioning = true)
        """
    )
    show(summary)

    print("\n  Language detection (Lingua):")
    show(
        query(
            f"""
            SELECT language, count(*) AS rows,
                   round(avg(language_confidence), 3) AS avg_confidence
            FROM read_parquet('{source}')
            GROUP BY language ORDER BY rows DESC
            """
        )
    )

    print("\n  Sentiment — and which model produced it:")
    show(
        query(
            f"""
            SELECT sentiment_model_version, sentiment, count(*) AS rows,
                   round(avg(sentiment_score), 3) AS avg_score
            FROM read_parquet('{source}')
            GROUP BY sentiment_model_version, sentiment ORDER BY rows DESC
            """
        )
    )

    print("\n  Topics (keyword rules, not a model):")
    show(
        query(
            f"""
            SELECT primary_topic, count(*) AS rows
            FROM read_parquet('{source}')
            GROUP BY primary_topic ORDER BY rows DESC
            """
        )
    )

    print(f"\n  {rows} enriched rows:")
    show(
        query(
            f"""
            SELECT brand, country, rating, language, sentiment,
                   round(sentiment_score, 3) AS score, primary_topic
            FROM read_parquet('{source}') LIMIT {rows}
            """
        )
    )


def inspect_gold(root: Path, rows: int) -> None:
    heading("GOLD  —  eight business-ready datasets")
    if not root.exists():
        print("  Empty. Run:  python -m pipelines.jobs.run_gold")
        return

    counts: list[dict[str, object]] = []
    for name in GOLD_DATASETS:
        path = root / name
        if not parquet_exists(path):
            counts.append({"dataset": name, "rows": "-", "engine": "not built"})
            continue
        source = glob_for(path)
        # The two telemetry datasets are appended by the pipeline runner rather
        # than produced by a Gold engine, so they carry no `engine` column.
        columns = duckdb.sql(f"SELECT * FROM read_parquet('{source}') LIMIT 0").columns
        has_engine = "engine" in columns
        engine_expr = "any_value(engine)" if has_engine else "'-- telemetry --'"
        result = query(
            f"SELECT count(*) AS rows, {engine_expr} AS engine FROM read_parquet('{source}')"
        )
        counts.append(
            {
                "dataset": name,
                "rows": f"{int(result['rows'][0]):,}",
                "engine": str(result["engine"][0]),
            }
        )
    show(pd.DataFrame(counts))
    print("\n  The `engine` column is why a DuckDB run can never be mistaken for Spark.")

    brand_path = root / "daily_brand_metrics"
    if parquet_exists(brand_path):
        print("\n  daily_brand_metrics — most recent day:")
        show(
            query(
                f"""
                SELECT brand, review_count, round(average_rating, 2) AS avg_rating,
                       negative_count, round(negative_percentage, 1) AS negative_pct
                FROM read_parquet('{glob_for(brand_path)}')
                WHERE review_date = (
                    SELECT max(review_date) FROM read_parquet('{glob_for(brand_path)}')
                )
                ORDER BY review_count DESC
                """
            )
        )

    anomaly_path = root / "anomalies"
    if parquet_exists(anomaly_path):
        source = glob_for(anomaly_path)
        print("\n  anomalies — by severity:")
        show(
            query(
                f"""
                SELECT severity, count(*) AS count
                FROM read_parquet('{source}')
                GROUP BY severity
                ORDER BY count DESC
                """
            )
        )

        print(f"\n  The {rows} strongest, each explaining itself:")
        explanations = query(
            f"""
            SELECT severity, round(z_score, 2) AS z, explanation
            FROM read_parquet('{source}')
            ORDER BY abs(z_score) DESC LIMIT {rows}
            """
        )
        for row in explanations.itertuples(index=False):
            print(f"\n    [{row.severity.upper()}]  z = {row.z}")
            print(f"    {row.explanation}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect what is on disk in each pipeline layer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--layer", choices=[*LAYERS, "all"], default="all")
    parser.add_argument("--rows", type=int, default=5, help="sample rows to print")
    args = parser.parse_args(argv)

    settings = get_pipeline_settings()
    wanted = LAYERS if args.layer == "all" else (args.layer,)

    inspectors = {
        "samples": (settings.samples_path, inspect_samples),
        "bronze": (settings.bronze_path, inspect_bronze),
        "quarantine": (settings.quarantine_path, inspect_quarantine),
        "silver": (settings.silver_path, inspect_silver),
        "gold": (settings.gold_path, inspect_gold),
    }

    for layer in wanted:
        root, inspector = inspectors[layer]
        inspector(root, args.rows)

    print(f"\n{'=' * 78}\ndata root: {settings.data_root}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
