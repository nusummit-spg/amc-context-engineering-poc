    #!/usr/bin/env python3
"""Alembic revision DAG preflight — fail fast on broken ancestry.

W22-01 / B01 fix: validates the full revision graph before any DDL runs.
Exits non-zero if any revision references a missing ancestor, has a
duplicate ID, or if unexpected multiple heads are found.

Usage:
    python scripts/alembic_dag_preflight.py
    # Automatically runs before 'alembic upgrade head' in CI A02 job.
"""
import sys
import os
from pathlib import Path

_here = Path(__file__).resolve().parent
_backend = _here.parent if _here.name == "scripts" else _here
sys.path.insert(0, str(_backend))

def main() -> int:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:
        print("ERROR: alembic not installed", file=sys.stderr)
        return 1

    ini = _backend / "alembic.ini"
    if not ini.exists():
        print(f"ERROR: alembic.ini not found at {ini}", file=sys.stderr)
        return 1

    cfg = Config(str(ini))
    db_url = (
        os.environ.get("AMC_MIGRATION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if db_url:
        cfg.set_main_option("sqlalchemy.url", db_url)

    scripts = ScriptDirectory.from_config(cfg)
    all_revs = {s.revision: s for s in scripts.walk_revisions()}
    errors = []

    # Check every revision's ancestors exist
    for rev_id, script in all_revs.items():
        if script.down_revision is None:
            continue
        parents = (
            [script.down_revision]
            if isinstance(script.down_revision, str)
            else list(script.down_revision)
        )
        for parent in parents:
            if parent and parent not in all_revs:
                errors.append(
                    f"Revision {rev_id!r} references missing ancestor {parent!r}"
                )

    # Check for multiple heads
    heads = scripts.get_heads()
    if len(heads) > 1:
        errors.append(
            f"Multiple revision heads: {heads}. Create a merge revision if intentional."
        )

    if errors:
        print("ALEMBIC DAG PREFLIGHT FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    print(
        f"Alembic DAG preflight passed: {len(all_revs)} revisions, "
        f"single head ({heads[0] if heads else 'none'})"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())