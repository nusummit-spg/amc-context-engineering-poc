"""Alembic environment configuration.

W22-03 / A04 fix: reads AMC_MIGRATION_DATABASE_URL (preferred) or DATABASE_URL
from the environment, falling back to alembic.ini.  Works with both SQLite
and PostgreSQL depending on the configured URL.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve database URL: environment variable takes precedence over alembic.ini
_db_url = (
    os.environ.get("AMC_MIGRATION_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url", "")
)

if not _db_url:
    import sys
    sys.exit(
        "FATAL: No database URL configured for Alembic. "
        "Set AMC_MIGRATION_DATABASE_URL or DATABASE_URL."
    )

config.set_main_option("sqlalchemy.url", _db_url)

# target_metadata is intentionally None — autogenerate is not used.
target_metadata = None

def run_migrations_offline() -> None:
    """Run migrations in offline mode (no live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()