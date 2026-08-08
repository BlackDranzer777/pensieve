"""Load the Parquet layers into PostgreSQL.

    python -m pipelines.jobs.load_postgres           # load
    python -m pipelines.jobs.load_postgres --counts  # just report what is there

Requires the schema to exist. Run the migrations first:

    cd apps/api && alembic upgrade head
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT, REPO_ROOT / "apps" / "api"):
    if str(path) not in sys.path:  # pragma: no cover - direct execution convenience
        sys.path.insert(0, str(path))

from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402

from app.core.config import get_api_settings  # noqa: E402
from pipelines.common.config import get_pipeline_settings  # noqa: E402
from pipelines.common.logging import configure_logging  # noqa: E402
from pipelines.loading.postgres_loader import (  # noqa: E402
    LoaderError,
    load_to_postgres,
    table_counts,
)


def _print_counts(counts: dict[str, int]) -> None:
    print("\n  table                       rows")
    print("  " + "-" * 34)
    for table, rows in counts.items():
        print(f"  {table:<24} {rows:>8,}")
    print(f"\n  total: {sum(counts.values()):,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load Silver and Gold Parquet into PostgreSQL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--counts",
        action="store_true",
        help="report current row counts without loading anything",
    )
    args = parser.parse_args(argv)

    settings = get_pipeline_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    database_url = get_api_settings().database_url

    try:
        if args.counts:
            _print_counts(table_counts(database_url))
            return 0

        result = load_to_postgres(settings, database_url)
    except LoaderError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    except ProgrammingError as exc:
        # Almost always a missing table, which means the migrations have not
        # run. Naming that beats re-printing SQLAlchemy's wrapped traceback.
        print(
            f"\nDatabase schema is not ready: {exc.orig}\n\n"
            "Apply the migrations first:\n"
            "  cd apps/api && alembic upgrade head",
            file=sys.stderr,
        )
        return 2
    except OperationalError as exc:
        print(
            f"\nCannot reach PostgreSQL: {exc.orig}\n\n"
            "Start it with:\n"
            "  docker compose up -d postgres",
            file=sys.stderr,
        )
        return 2

    print(f"\nLoad complete in {result.duration_seconds:.2f}s")
    _print_counts(result.rows_by_table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
