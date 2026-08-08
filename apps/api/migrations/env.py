"""Alembic environment.

Two things this does that the generated template does not:

1. Reads the database URL from `ApiSettings` rather than `alembic.ini`, so no
   credentials live in source control.
2. Puts both the repository root and `apps/api` on `sys.path`, because `app`
   imports `pipelines.common.domain` for the shared vocabulary and Alembic runs
   with its own working directory.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent.parent
for path in (REPO_ROOT, API_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.config import get_api_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing app.models populates this. Alembic diffs the live database against
# it, so an unimported model is a table autogenerate would try to drop.
target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_api_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — `alembic upgrade head --sql`.

    Useful when a DBA has to review and apply the change by hand.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without this, a column changing from Integer to Float produces an
            # empty migration and the mismatch is only found at runtime.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
