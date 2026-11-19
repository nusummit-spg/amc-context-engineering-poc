"""LIVE40 fixtures: reuse the LIVE31 disposable-PostgreSQL harness (same loopback guard, same skip semantics).

Without AMC_LIVE_PG_URL these tests SKIP as LIVE31_BLOCKED; that is a blocked gate, never a pass.
"""
from tests.live31.conftest import live_pg, live_pg_admin_url, live_template_db  # noqa: F401
