"""LIVE31 fixtures: disposable real PostgreSQL databases and a real Neo4j.

Environment (set by ops/validation/local_services31.ps1 or by hand):
  AMC_LIVE_PG_URL   postgresql+psycopg://USER:PASS@127.0.0.1:PORT/postgres   (needs CREATEDB)
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD

When these are not set the tests are SKIPPED with the reason "LIVE31_BLOCKED". That is a
blocked gate, never a pass. When they ARE set but the service is unreachable, tests FAIL.
Each test gets its own database cloned from a migrated template, so tests cannot interfere.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from tests.live31 import support  # noqa: E402


def _blocked(reason: str):
    pytest.skip("LIVE31_BLOCKED: " + reason)


def _render(url) -> str:
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def live_pg_admin_url():
    raw = os.environ.get("AMC_LIVE_PG_URL")
    if not raw:
        _blocked("AMC_LIVE_PG_URL is not set (a real disposable PostgreSQL is required)")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg":
        _blocked("AMC_LIVE_PG_URL must use the postgresql+psycopg driver")
    eng = create_engine(raw, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:           # configured but unreachable must FAIL, not skip
        c.execute(text("select 1"))
    eng.dispose()
    return raw


def _admin(url: str):
    # pre-ping: the outage drills stop PostgreSQL mid-test and teardown must reconnect, not reuse a dead socket
    return create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)


@pytest.fixture(scope="session")
def live_template_db(live_pg_admin_url):
    """One migrated 001..head database; every test clones it."""
    from alembic import command
    from alembic.config import Config

    name = "amc_live_tpl_" + uuid.uuid4().hex[:8]
    admin = _admin(live_pg_admin_url)
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = _render(make_url(live_pg_admin_url).set(database=name))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    old = {k: os.environ.get(k) for k in ("AMC_MIGRATION_DATABASE_URL", "DATABASE_URL")}
    os.environ["AMC_MIGRATION_DATABASE_URL"] = url
    os.environ.pop("DATABASE_URL", None)
    try:
        command.upgrade(cfg, "head")
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    yield name
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def live_pg(live_pg_admin_url, live_template_db):
    """A fresh, migrated, disposable database for one test."""
    name = "amc_live_" + uuid.uuid4().hex[:10]
    admin = _admin(live_pg_admin_url)
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{live_template_db}"'))
    url = _render(make_url(live_pg_admin_url).set(database=name))
    engine = create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)
    ns = type("LivePg", (), {})()
    ns.url, ns.name, ns.engine = url, name, engine
    ns.sessions = sessionmaker(bind=engine)
    ns.admin_url = live_pg_admin_url
    yield ns
    engine.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def live_neo4j_driver():
    uri, user, pw = (os.environ.get(k) for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"))
    if not (uri and user and pw):
        _blocked("NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not set (a real disposable Neo4j is required)")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    driver.verify_connectivity()       # configured but unreachable must FAIL, not skip
    yield driver
    driver.close()


@pytest.fixture
def live_stack(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "faiss")
    stack.pg = live_pg
    yield stack
    support.clean_graph(live_neo4j_driver)
