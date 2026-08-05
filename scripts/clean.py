"""Remove generated artefacts: data layers, build output and tool caches.

    python scripts/clean.py             # generated data + caches
    python scripts/clean.py --dry-run   # show what would be removed
    python scripts/clean.py --all       # also remove node_modules and dist

Source files, `.env` and the virtualenv are never touched.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Contents are removed, but the directory and its .gitkeep survive so the
# repository layout stays intact.
EMPTIED_DIRS: tuple[str, ...] = (
    "data/bronze",
    "data/silver",
    "data/gold",
    "data/quarantine",
    "data/samples",
)

REMOVED_DIRS: tuple[str, ...] = (
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "spark-warehouse",
    "metastore_db",
)

HEAVY_DIRS: tuple[str, ...] = (
    "apps/web/node_modules",
    "apps/web/dist",
    "apps/web/coverage",
)

REMOVED_FILES: tuple[str, ...] = (".coverage", "coverage.xml", "derby.log")


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _remove(path: Path, *, dry_run: bool) -> int:
    """Delete a file or directory tree; return the bytes reclaimed."""
    if not path.exists():
        return 0
    size = _dir_size(path) if path.is_dir() else path.stat().st_size
    rel = path.relative_to(REPO_ROOT)
    if dry_run:
        print(f"  would remove  {rel}  ({_human(size)})")
        return size
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
    print(f"  removed  {rel}  ({_human(size)})")
    return size


def _empty_directory(path: Path, *, dry_run: bool) -> int:
    """Delete everything inside a directory except `.gitkeep`."""
    if not path.exists():
        return 0
    freed = 0
    for child in path.iterdir():
        if child.name == ".gitkeep":
            continue
        freed += _remove(child, dry_run=dry_run)
    return freed


def _remove_pycache(*, dry_run: bool) -> int:
    freed = 0
    for cache in REPO_ROOT.rglob("__pycache__"):
        if ".venv" in cache.parts or "node_modules" in cache.parts:
            continue
        freed += _remove(cache, dry_run=dry_run)
    return freed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove generated Pensieve artefacts.")
    parser.add_argument("--dry-run", action="store_true", help="show what would be removed")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_heavy",
        help="also remove node_modules, dist and frontend coverage",
    )
    args = parser.parse_args(argv)

    print("Cleaning generated artefacts" + (" (dry run)" if args.dry_run else ""))
    freed = 0

    print("\nData layers:")
    for rel in EMPTIED_DIRS:
        freed += _empty_directory(REPO_ROOT / rel, dry_run=args.dry_run)

    print("\nCaches and build output:")
    for rel in REMOVED_DIRS:
        freed += _remove(REPO_ROOT / rel, dry_run=args.dry_run)
    for rel in REMOVED_FILES:
        freed += _remove(REPO_ROOT / rel, dry_run=args.dry_run)
    freed += _remove_pycache(dry_run=args.dry_run)

    if args.include_heavy:
        print("\nDependencies and bundles:")
        for rel in HEAVY_DIRS:
            freed += _remove(REPO_ROOT / rel, dry_run=args.dry_run)

    verb = "Would reclaim" if args.dry_run else "Reclaimed"
    print(f"\n{verb} {_human(freed)}.")
    if not args.include_heavy:
        print("Pass --all to also remove node_modules and the frontend build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
