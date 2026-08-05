"""Report whether this machine can run each part of Pensieve.

The goal is that a missing prerequisite produces one clear sentence telling you
what to install, instead of a Java stack trace forty lines deep.

    python scripts/check_env.py

Exit code 0 means the core platform (API, web, pipeline up to Silver) can run.
Exit code 1 means a core prerequisite is missing. Spark and the sentiment model
are reported as optional: their absence degrades features but does not block
the core platform.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIN_JAVA_FOR_SPARK = 17
MIN_PYTHON = (3, 12)
MIN_NODE = 20

OK = "  OK  "
WARN = " WARN "
FAIL = " FAIL "


@dataclass
class Result:
    label: str
    status: str
    detail: str
    remedy: str = ""
    required: bool = True


def _run(cmd: list[str]) -> str:
    """Run a command and return combined output, or an empty string on failure."""
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=25, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def check_python() -> Result:
    v = sys.version_info
    current = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        return Result("Python", OK, current)
    return Result(
        "Python", FAIL, current, f"Pensieve targets Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+."
    )


def check_node() -> Result:
    if shutil.which("node") is None:
        return Result("Node.js", FAIL, "not found", "Install Node 20+ from nodejs.org")
    raw = _run(["node", "--version"]).strip()
    match = re.search(r"v(\d+)", raw)
    if match and int(match.group(1)) >= MIN_NODE:
        return Result("Node.js", OK, raw)
    return Result("Node.js", FAIL, raw or "unknown", f"Node {MIN_NODE}+ is required.")


def check_java() -> Result:
    """Spark 4.x refuses to start on anything older than Java 17."""
    if shutil.which("java") is None:
        return Result(
            "Java (Spark)",
            WARN,
            "not found",
            "Install Temurin 21, or run the Spark stage in Docker: `make gold-docker`",
            required=False,
        )

    raw = _run(["java", "-version"])
    match = re.search(r'version "(\d+)(?:\.(\d+))?', raw)
    if not match:
        return Result("Java (Spark)", WARN, "version unparseable", required=False)

    major, minor = int(match.group(1)), int(match.group(2) or 0)
    # "1.8.0_432" means Java 8; from Java 9 onward the first number is the major.
    version = minor if major == 1 else major
    detail = f"Java {version}"

    if version >= MIN_JAVA_FOR_SPARK:
        return Result("Java (Spark)", OK, detail, required=False)
    return Result(
        "Java (Spark)",
        WARN,
        f"{detail} — PySpark 4 needs {MIN_JAVA_FOR_SPARK}+",
        "Run the Spark stage in Docker (`make gold-docker`), or install a modern JDK: "
        "`winget install EclipseAdoptium.Temurin.21.JDK`",
        required=False,
    )


def check_docker() -> Result:
    if shutil.which("docker") is None:
        return Result(
            "Docker",
            WARN,
            "not found",
            "Needed for Postgres and the Spark stage. Install Docker Desktop.",
            required=False,
        )
    raw = _run(["docker", "--version"]).strip()
    running = "Server:" in _run(["docker", "version"])
    if running:
        return Result("Docker", OK, raw, required=False)
    return Result(
        "Docker", WARN, f"{raw} (daemon not running)", "Start Docker Desktop.", required=False
    )


def check_env_file() -> Result:
    if (REPO_ROOT / ".env").exists():
        return Result(".env", OK, "present", required=False)
    return Result(
        ".env",
        WARN,
        "missing — defaults will be used",
        "Copy-Item .env.example .env   (PowerShell)   |   cp .env.example .env",
        required=False,
    )


def check_onedrive_location() -> Result:
    """Warn when generated data would land inside a synced cloud folder.

    Parquet output, node_modules, .venv and a ~1 GB model cache inside OneDrive
    cause sync churn and intermittent file-lock write failures that look like
    data corruption. Worth one clear warning.
    """
    path = str(REPO_ROOT).replace("\\", "/").lower()
    synced = next((n for n in ("onedrive", "dropbox", "google drive", "icloud") if n in path), None)
    if synced is None:
        return Result("Repo location", OK, "not inside a synced folder", required=False)
    return Result(
        "Repo location",
        WARN,
        f"inside a synced folder ({synced})",
        "Exclude data/, .venv/ and node_modules/ from sync, or move the repo to "
        "a local path such as C:\\dev\\pensieve. Keep HF_HOME outside the synced folder.",
        required=False,
    )


def check_optional_import(module: str, label: str, remedy: str) -> Result:
    try:
        __import__(module)
    except ImportError:
        return Result(label, WARN, "not installed", remedy, required=False)
    return Result(label, OK, "installed", required=False)


def main() -> int:
    print("Pensieve environment check")
    print(f"  platform : {platform.platform()}")
    print(f"  repo     : {REPO_ROOT}")
    print()

    results = [
        check_python(),
        check_node(),
        check_docker(),
        check_java(),
        check_env_file(),
        check_onedrive_location(),
        check_optional_import(
            "pyspark", "PySpark", "pip install -e .[spark]  (needs Java 17+ to run)"
        ),
        check_optional_import(
            "transformers", "Transformers", "pip install -e .[nlp]  (~1.1 GB model on first use)"
        ),
        check_optional_import("pandas", "Pandas/PyArrow", "pip install -e .[pipelines]"),
    ]

    width = max(len(r.label) for r in results)
    for r in results:
        print(f"[{r.status}] {r.label.ljust(width)}  {r.detail}")
        if r.remedy:
            print(f"{'':>{width + 9}}-> {r.remedy}")

    blocking = [r for r in results if r.status == FAIL and r.required]
    print()
    if blocking:
        print(f"{len(blocking)} required prerequisite(s) missing. See the remedies above.")
        return 1
    warnings = [r for r in results if r.status == WARN]
    if warnings:
        print(f"Core platform can run. {len(warnings)} optional item(s) need attention.")
    else:
        print("Everything checks out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
