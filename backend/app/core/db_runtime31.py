"""Wave 3.1 runtime DB selection and fail-closed PostgreSQL startup proof.

Export DATABASE_URL into the app process, not merely AMC_MIGRATION_DATABASE_URL.
Alembic can point to PostgreSQL while legacy runtime otherwise uses SQLite.
"""
from __future__ import annotations
import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import make_url

_EXPECTED_REVISION = "014_publication_scope_claim_v31"

def resolve_database_url(base_dir: Path) -> str:
    """Verified serving requires explicit psycopg-backed PostgreSQL."""
    value = os.environ.get("DATABASE_URL") or f"sqlite:///{base_dir / 'data.db'}"
    mode = os.environ.get("AMC_VERIFIED_SERVING_MODE", "off")
    if mode not in ("off", "enforce"):
        raise RuntimeError("Invalid AMC_VERIFIED_SERVING_MODE")
    url = make_url(value)
    if mode == "enforce" and url.drivername != "postgresql+psycopg":
        raise RuntimeError("Verified AMC requires DATABASE_URL=postgresql+psycopg://...")
    return value

def verify_migrated_postgresql(engine) -> None:
    """Read-only exact migration proof before any verified-mode schema writes."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Verified AMC cannot serve from non-PostgreSQL journal")
    with engine.connect() as connection:
        versions = connection.execute(
            text("SELECT version_num FROM alembic_version")).scalars().all()
    if versions != [_EXPECTED_REVISION]:
        raise RuntimeError("Verified AMC database is not at exact Alembic revision 014")
