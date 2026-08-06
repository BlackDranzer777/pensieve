"""Build the Gold layer from Silver.

    python -m pipelines.jobs.run_gold                  # DuckDB (default)
    python -m pipelines.jobs.run_gold --engine spark   # PySpark, needs JDK 17+

**DuckDB is the default because it is the right tool at this size.** Both
engines execute the same SQL from `analytics/sql/` and produce byte-identical
Gold output; DuckDB does it in ~1.3s in ~50 MB, where Spark spends ~30s of
which almost all is JVM startup. Spark remains supported and tested — it is the
path that would not have to change if this dataset grew a thousandfold — but
paying 24x the wall time and 1.7 GB of image for that option on every local run
is the wrong default.

A preflight check runs before Spark starts, so an unsuitable machine gets a
clear sentence and a suggested command rather than a Java stack trace.

**There is no automatic fallback.** A DuckDB run you believed was Spark would
invalidate every benchmark number with nothing to reveal it. Every Gold row
records the engine that produced it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - direct execution convenience
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.aggregation.engines import EngineUnavailableError  # noqa: E402
from pipelines.aggregation.gold import ALL_GOLD_DATASETS, build_gold  # noqa: E402
from pipelines.common.config import get_pipeline_settings  # noqa: E402
from pipelines.common.logging import configure_logging  # noqa: E402

MIN_JAVA_FOR_SPARK = 17
#: Spark needs roughly this much to start comfortably: JVM plus driver.
RECOMMENDED_FREE_MB = 1500


def detect_java_version() -> int | None:
    """Return the installed Java major version, or None if absent."""
    java = shutil.which("java")
    if java is None:
        return None
    try:
        # Resolved via `shutil.which` rather than relying on PATH resolution
        # inside the subprocess call.
        proc = subprocess.run(  # noqa: S603
            [java, "-version"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None

    import re

    match = re.search(r'version "(\d+)(?:\.(\d+))?', (proc.stdout or "") + (proc.stderr or ""))
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2) or 0)
    # "1.8.0_432" means Java 8; from 9 onward the first number is the major.
    return minor if major == 1 else major


def _windows_available_mb() -> int | None:
    """Available physical memory on Windows, via GlobalMemoryStatusEx."""
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = (
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        )

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 - windll is Windows-only
    kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return int(status.ullAvailPhys / (1024 * 1024))


def _posix_available_mb() -> int | None:
    """Available memory on Linux, from /proc/meminfo."""
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    for line in meminfo.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return None


def available_memory_mb() -> int | None:
    """Best-effort available memory in MB. None when it cannot be determined.

    Dispatches on `os.name` rather than `sys.platform`. mypy narrows
    `sys.platform` at type-check time and marks the branch for the *other*
    platform as unreachable dead code, which it is not — this runs on Windows,
    Linux and in the Docker image.
    """
    try:
        if os.name == "nt":
            return _windows_available_mb()
        return _posix_available_mb()
    except Exception:  # noqa: BLE001 - a preflight hint must never be fatal
        return None


def preflight_spark() -> list[str]:
    """Return reasons Spark is unlikely to run here. Empty means go ahead."""
    problems: list[str] = []

    java = detect_java_version()
    if java is None:
        problems.append("Java not found on PATH; PySpark 4 requires Java 17+")
    elif java < MIN_JAVA_FOR_SPARK:
        problems.append(f"Java {java} detected; PySpark 4 requires Java {MIN_JAVA_FOR_SPARK}+")

    memory = available_memory_mb()
    if memory is not None and memory < RECOMMENDED_FREE_MB:
        problems.append(
            f"only {memory} MB RAM available; Spark wants about {RECOMMENDED_FREE_MB} MB"
        )

    return problems


def _print_result(result: object, gold_root: Path) -> None:
    from pipelines.aggregation.gold import GoldResult

    assert isinstance(result, GoldResult)  # noqa: S101 - narrowing for the printer
    print(f"\nGold build complete  (engine: {result.engine})")
    print(f"  silver rows : {result.silver_rows:,}")
    print(f"  duration    : {result.duration_seconds:.2f}s")
    print(f"  anomalies   : {result.anomaly_count}")
    print("\n  datasets:")
    for name in ALL_GOLD_DATASETS:
        rows = result.datasets.get(name, 0)
        print(f"    {name:<24} {rows:>8,} rows")
    print(f"\n  written to: {gold_root}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Gold layer from Silver.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--engine",
        choices=["duckdb", "spark"],
        default="duckdb",
        help="compute engine; both produce identical Gold output",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="attempt Spark even if the preflight check objects",
    )
    args = parser.parse_args(argv)

    settings = get_pipeline_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    if args.engine == "spark" and not args.skip_preflight:
        problems = preflight_spark()
        if problems:
            print("Cannot start Spark on this machine:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print(
                "\nOptions:\n"
                "  python -m pipelines.jobs.run_gold          (DuckDB, the default;\n"
                "                                             identical Gold output)\n"
                "  docker compose --profile spark build spark-job\n"
                "  docker compose --profile spark run   --rm spark-job\n"
                "  python -m pipelines.jobs.run_gold --engine spark --skip-preflight",
                file=sys.stderr,
            )
            return 2

    try:
        result = build_gold(engine_name=args.engine, settings=settings)
    except EngineUnavailableError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    _print_result(result, settings.gold_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
