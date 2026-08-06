"""Compute engines for the Gold layer.

Two engines, one set of SQL. The aggregation logic lives in
`analytics/sql/*.sql` and is executed by whichever engine you choose:

    SparkEngine    distributed, needs Java 17+, ~1-2 GB RAM
    DuckDBEngine   in-process, no JVM, ~50 MB RAM

Both read the same Silver Parquet and write the same Gold Parquet. Keeping the
logic in SQL rather than in engine-specific DataFrame code is what stops the
two paths drifting apart — there is one definition of
`daily_brand_metrics`, not two.

The engine is never chosen silently. Every Gold row records which one produced
it, so a benchmark or a CV claim can always be traced back to what actually
ran.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from pipelines.common.config import PipelineSettings
from pipelines.common.logging import get_logger

log = get_logger(__name__)

SQL_DIR = Path(__file__).resolve().parents[2] / "analytics" / "sql"

#: The view name every Gold query selects from.
SILVER_VIEW = "silver"


class EngineUnavailableError(RuntimeError):
    """Raised when an engine cannot start, with a remedy in the message.

    Deliberately verbose: the alternative is a Java stack trace forty lines
    deep that never mentions the actual problem is an old JDK.
    """


def load_query(name: str) -> str:
    """Read a Gold query from `analytics/sql/`."""
    path = SQL_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"No SQL file for Gold dataset {name!r} at {path}")
    return path.read_text(encoding="utf-8")


class GoldEngine(ABC):
    """What any Gold compute engine must provide."""

    name: str

    @abstractmethod
    def register_silver(self, silver_root: Path) -> int:
        """Expose the Silver layer as the `silver` view. Returns the row count."""

    @abstractmethod
    def run_query(self, sql: str) -> pd.DataFrame:
        """Execute SQL and return the result as a pandas DataFrame.

        Returning pandas keeps the writing path identical for both engines.
        Gold datasets are aggregates — hundreds or thousands of rows, not
        millions — so collecting them is cheap regardless of engine.
        """

    def close(self) -> None:  # noqa: B027 - optional hook, not every engine holds resources
        """Release resources. Safe to call twice, and safe not to override."""

    def __enter__(self) -> GoldEngine:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class DuckDBEngine(GoldEngine):
    """In-process OLAP. No JVM, no cluster, ~50 MB.

    DuckDB reads Parquet directly with no copy step, which is why it is the
    right tool for local analytics over a Parquet lake — and why it also backs
    the `analytics/sql/` query library and the notebooks.
    """

    name = "duckdb"

    def __init__(self) -> None:
        import duckdb

        self._connection = duckdb.connect(database=":memory:")

    def register_silver(self, silver_root: Path) -> int:
        pattern = str(silver_root / "review_date=*" / "*.parquet").replace("\\", "/")
        # `hive_partitioning=1` recovers `review_date` from the directory name;
        # it is in the path, not inside the files.
        #
        # S608 is suppressed deliberately: `pattern` is a filesystem path built
        # from settings, never user input, and `SILVER_VIEW` is a module
        # constant. SQL has no parameter binding for table or path positions,
        # so interpolation is the only available form here.
        create_view = (
            f"CREATE OR REPLACE VIEW {SILVER_VIEW} AS "
            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning=1)"
        )
        self._connection.execute(create_view)
        count = self._connection.execute(f"SELECT count(*) FROM {SILVER_VIEW}").fetchone()
        rows = int(count[0]) if count else 0
        log.info("silver_registered", engine=self.name, rows=rows)
        return rows

    def run_query(self, sql: str) -> pd.DataFrame:
        return self._connection.execute(sql).fetch_df()

    def close(self) -> None:
        self._connection.close()


class SparkEngine(GoldEngine):
    """Distributed compute via PySpark.

    Overkill for a demo-sized dataset and entirely deliberate: the Gold layer
    exists partly to demonstrate distributed-style aggregation. The same SQL
    that runs here would run unchanged against a cluster and a thousand times
    the data.
    """

    name = "spark"

    def __init__(self, settings: PipelineSettings) -> None:
        self._settings = settings
        self._spark = self._build_session()

    def _build_session(self) -> Any:
        try:
            from pyspark.sql import SparkSession
        except ImportError as exc:
            raise EngineUnavailableError(
                "PySpark is not installed.\n"
                "  Install it:  pip install -e '.[spark]'   (requires Java 17+)\n"
                "  Or use:      python -m pipelines.jobs.run_gold --engine duckdb"
            ) from exc

        log.info(
            "spark_session_starting",
            master=self._settings.spark_master,
            driver_memory=self._settings.spark_driver_memory,
        )
        try:
            return (
                SparkSession.builder.appName("pensieve-gold")
                .master(self._settings.spark_master)
                .config("spark.driver.memory", self._settings.spark_driver_memory)
                .config("spark.sql.shuffle.partitions", self._settings.spark_shuffle_partitions)
                # Local runs have no cluster to spread over; a smaller default
                # avoids hundreds of near-empty output files.
                .config("spark.sql.adaptive.enabled", "true")
                .config("spark.ui.showConsoleProgress", "false")
                .getOrCreate()
            )
        except Exception as exc:
            raise EngineUnavailableError(
                f"Could not start Spark: {exc}\n"
                "  Most likely cause: PySpark 4 requires Java 17+.\n"
                "  Check with:  python scripts/check_env.py\n"
                "  In Docker:   docker compose --profile spark run --rm spark-job\n"
                "  Or use:      python -m pipelines.jobs.run_gold --engine duckdb"
            ) from exc

    def register_silver(self, silver_root: Path) -> int:
        pattern = str(silver_root).replace("\\", "/")
        frame = self._spark.read.option("basePath", pattern).parquet(f"{pattern}/review_date=*")
        frame.createOrReplaceTempView(SILVER_VIEW)
        rows = int(frame.count())
        log.info("silver_registered", engine=self.name, rows=rows)
        return rows

    def run_query(self, sql: str) -> pd.DataFrame:
        # PySpark is untyped from mypy's perspective, so the result needs an
        # explicit annotation rather than flowing through as `Any`.
        result: pd.DataFrame = self._spark.sql(sql).toPandas()
        return result

    def close(self) -> None:
        if getattr(self, "_spark", None) is not None:
            self._spark.stop()


def create_engine(name: str, settings: PipelineSettings) -> GoldEngine:
    """Build the requested engine.

    Never falls back silently. A DuckDB run that you believed was Spark would
    make every benchmark number and CV claim wrong, with nothing to reveal it.
    """
    if name == "duckdb":
        return DuckDBEngine()
    if name == "spark":
        return SparkEngine(settings)
    raise ValueError(f"Unknown engine {name!r}. Use 'spark' or 'duckdb'.")


def write_gold_dataset(frame: pd.DataFrame, name: str, gold_root: Path, engine: str) -> Path:
    """Write one Gold dataset, replacing any previous version.

    Gold is derived and fully reproducible from Silver, so a rerun should
    correct it rather than accumulate contradictory copies.
    """
    target_dir = gold_root / name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    result = frame.copy()
    # Stamped on every row: which engine produced this, and when.
    result["engine"] = engine
    result["generated_at"] = pd.Timestamp.now(tz="UTC").isoformat()

    target = target_dir / "part-0000.parquet"
    result.to_parquet(target, engine="pyarrow", compression="snappy", index=False)
    log.info(
        "gold_dataset_written",
        dataset=name,
        rows=len(result),
        engine=engine,
        bytes=target.stat().st_size,
    )
    return target


def read_gold_dataset(gold_root: Path, name: str) -> pd.DataFrame:
    """Read one Gold dataset back."""
    paths = sorted((gold_root / name).glob("*.parquet"))
    if not paths:
        return pd.DataFrame()
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
