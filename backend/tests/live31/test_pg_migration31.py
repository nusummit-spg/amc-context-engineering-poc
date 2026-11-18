"""WP02 / gate G2: the migration chain, schema accuracy and the startup guard on a REAL PostgreSQL."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from tests.live31 import support

HEAD = "015_app_schema_alignment_v31"
BACKEND = Path(__file__).resolve().parents[2]

# Tables that exist only in migrations (legacy, no ORM model) - not a defect.
DB_ONLY_TABLES = {"alembic_version", "active_versions", "outbox_events", "publication_effects",
                  "publication_intents", "publication_receipts", "reindex_jobs"}

# Known ORM-vs-DB differences that are OUT OF PILOT SCOPE (their routes are denied by the pilot
# perimeter). The list is pinned in both directions: new drift fails the test, and so does
# fixing drift without updating this list.
KNOWN_DRIFT = {
    "audit_metadata": "compliance audit model differs from the legacy 001 table",
    "chat_sessions": "DB-only legacy columns metadata_json/status (status has a server default)",
    "graph_mutations": "success: model NOT NULL, DB nullable with server default",
    "query_evidence": "archived/has_feedback: model NOT NULL, DB nullable with server default",
    "repair_proposals": "reindex_required: model NOT NULL, DB nullable with server default",
}
# Tables the pilot path touches. For these, a model column missing in the DB is a hard failure.
PILOT_TABLES = {"auth_users", "revoked_tokens", "invitation_tokens", "chat_sessions", "query_evidence",
                "response_feedback",       # the query path selects it on every request

                "publication_work_v2", "publication_effect_v2", "publication_receipt_v2",
                "publication_pointer_v2", "publication_fence_v2", "feedback_publication_link_v2",
                "publication_active_authority_v28", "publication_authority_preimage_v28",
                "publication_scope_claim_v31"}


def _models() -> dict:
    from app.core.database import Base as AppBase
    from app import schemas  # noqa: F401
    import amc_publication.journal  # noqa: F401
    from amc_publication.models import Base as PubBase
    out = {}
    for base in (AppBase, PubBase):
        for name, table in base.metadata.tables.items():
            out.setdefault(name, table)
    return out


def _drift(engine) -> dict:
    insp = inspect(engine)
    models = _models()
    db_tables = set(insp.get_table_names())
    result = {"missing_tables": sorted(set(models) - db_tables),
              "extra_tables": sorted(db_tables - set(models) - DB_ONLY_TABLES),
              "columns": {}}
    for name in sorted(set(models) & db_tables):
        db_cols = {c["name"]: c for c in insp.get_columns(name)}
        m_cols = {c.name: c for c in models[name].columns}
        diff = {"model_only": sorted(set(m_cols) - set(db_cols)),
                "db_only": sorted(set(db_cols) - set(m_cols)),
                "nullability": sorted(c for c in set(m_cols) & set(db_cols)
                                      if bool(m_cols[c].nullable) != bool(db_cols[c]["nullable"]))}
        if any(diff.values()):
            result["columns"][name] = diff
    return result


def _version(engine):
    with engine.connect() as c:
        return c.execute(text("select version_num from alembic_version")).scalars().all()


def test_fresh_database_is_at_exactly_the_head_revision(live_pg):
    assert _version(live_pg.engine) == [HEAD]


def test_second_upgrade_is_idempotent(live_pg):
    before = {t: sorted(c["name"] for c in inspect(live_pg.engine).get_columns(t))
              for t in inspect(live_pg.engine).get_table_names()}
    support.alembic_cmd(live_pg.url, "upgrade", "head")
    after = {t: sorted(c["name"] for c in inspect(live_pg.engine).get_columns(t))
             for t in inspect(live_pg.engine).get_table_names()}
    assert _version(live_pg.engine) == [HEAD] and before == after


def test_every_model_table_has_a_migration_and_no_unknown_tables(live_pg):
    d = _drift(live_pg.engine)
    assert d["missing_tables"] == [], "model tables without a migration"
    assert d["extra_tables"] == [], "DB tables without a model that are not listed as legacy"


def test_pilot_tables_have_every_column_the_models_use(live_pg):
    d = _drift(live_pg.engine)["columns"]
    for table in PILOT_TABLES:
        assert not d.get(table, {}).get("model_only"), (table, d.get(table))


def test_remaining_schema_drift_is_exactly_the_documented_out_of_scope_list(live_pg):
    assert set(_drift(live_pg.engine)["columns"]) == set(KNOWN_DRIFT)


def test_publication_check_constraint_names_match_the_models(live_pg):
    insp = inspect(live_pg.engine)
    models = _models()
    for name in PILOT_TABLES & set(models):
        want = {c.name for c in models[name].constraints if c.__class__.__name__ == "CheckConstraint" and c.name}
        have = {c["name"] for c in insp.get_check_constraints(name) if c.get("name")}
        assert want == have, (name, want ^ have)


def _work(live_pg, tenant="t_mig", key=None):
    from amc_publication.journal import Journal
    return Journal(live_pg.sessions).submit(
        tenant=tenant, key=key or uuid.uuid4().hex, proposal_id="P", revision=1,
        payload={"entity": "E", "attribute": "ter", "corrected_value": "1",
                 "full_vector_snapshot": [{"chunk_id": "c", "tenant_id": tenant, "text": "x"}]})


def test_scope_claim_primary_key_denies_a_second_first_publisher(live_pg):
    w1, w2 = _work(live_pg), _work(live_pg)
    ins = text("insert into publication_scope_claim_v31 (tenant,namespace,owner_work_id,status,claim_epoch,updated_at) "
               "values ('t_mig','vector_faiss',:w,'HELD',1,now())")
    with live_pg.engine.begin() as c:
        c.execute(ins, {"w": w1})
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(ins, {"w": w2})


def test_scope_claim_status_check_and_foreign_key(live_pg):
    w = _work(live_pg)
    bad_status = text("insert into publication_scope_claim_v31 values ('t','ns',:w,'OPEN',1,now())")
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(bad_status, {"w": w})
    no_work = text("insert into publication_scope_claim_v31 values ('t','ns','no_such_work','HELD',1,now())")
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(no_work)


def test_authority_requires_real_work_and_receipt_and_valid_status(live_pg):
    ins = text("insert into publication_active_authority_v28 (tenant,namespace,generation_id,digest,pointer_epoch,"
               "work_id,receipt_id,status,updated_at) values ('t','ns','g','d',1,:w,:r,:s,now())")
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(ins, {"w": "nope", "r": "nope", "s": "ACTIVE"})
    w = _work(live_pg)
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(ins, {"w": w, "r": "nope", "s": "ACTIVE"})


def test_revoked_tokens_table_works_for_jwt_revocation(live_pg):
    with live_pg.engine.begin() as c:
        c.execute(text("insert into revoked_tokens (jti,username,revoked_at,expires_at,reason) "
                       "values ('j1','alpha_analyst',now(),now() + interval '1 hour','logout')"))
    with pytest.raises(IntegrityError):
        with live_pg.engine.begin() as c:
            c.execute(text("insert into revoked_tokens (jti,username,revoked_at,expires_at,reason) "
                           "values ('j1','alpha_analyst',now(),now() + interval '1 hour','dup')"))


def test_chat_sessions_accepts_the_columns_the_orm_writes(live_pg):
    from sqlalchemy.orm import sessionmaker
    from app.schemas.chat_sessions_table import ChatSession
    S = sessionmaker(bind=live_pg.engine)
    with S.begin() as s:
        s.add(ChatSession(session_id="s1", user_id="alpha_analyst", tenant_id="tenant_alpha"))
    with S() as s:
        row = s.get(ChatSession, "s1")
        assert row.tenant_id == "tenant_alpha" and row.ended_at is None and row.audit_id is None


def test_downgrade_to_014_then_upgrade_again_on_a_disposable_database(live_pg):
    support.alembic_cmd(live_pg.url, "downgrade", "014_publication_scope_claim_v31")
    assert _version(live_pg.engine) == ["014_publication_scope_claim_v31"]
    assert "revoked_tokens" not in inspect(live_pg.engine).get_table_names()
    support.alembic_cmd(live_pg.url, "upgrade", "head")
    assert _version(live_pg.engine) == [HEAD]
    assert "revoked_tokens" in inspect(live_pg.engine).get_table_names()


@pytest.mark.xfail(strict=True, raises=NotImplementedError,
                   reason="PRE-EXISTING: migration 008 calls drop_constraint, which SQLite cannot ALTER. "
                          "The Alembic chain is PostgreSQL-only; SQLite stays on init_db()/create_all in off mode. "
                          "If this starts passing, remove the xfail and assert the 015 columns.")
def test_whole_chain_on_sqlite_is_not_supported_today(tmp_path):
    support.alembic_cmd(f"sqlite:///{(tmp_path / 'chain.db').as_posix()}", "upgrade", "head")


# ---- startup guard against the real database (gate: engine and Alembic are the same DB) ------

def test_startup_guard_passes_on_the_migrated_database(live_pg):
    from app.core.db_runtime31 import verify_migrated_postgresql
    verify_migrated_postgresql(live_pg.engine)


def test_startup_guard_blocks_a_database_left_at_014(live_pg):
    from app.core.db_runtime31 import verify_migrated_postgresql
    support.alembic_cmd(live_pg.url, "downgrade", "014_publication_scope_claim_v31")
    with pytest.raises(RuntimeError, match="revision 015"):
        verify_migrated_postgresql(live_pg.engine)


def test_startup_guard_does_not_pass_an_unmigrated_database(live_pg):
    from app.core.db_runtime31 import verify_migrated_postgresql
    support.alembic_cmd(live_pg.url, "downgrade", "base")
    with pytest.raises(Exception):
        verify_migrated_postgresql(live_pg.engine)


def _runtime_engine_url_masked(database_url: str, mode: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url, "AMC_VERIFIED_SERVING_MODE": mode,
           "PYTHONPATH": str(BACKEND), "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("AMC_MIGRATION_DATABASE_URL", None)
    code = ("import app.core.database as d; "
            "print(d.engine.url.render_as_string(hide_password=True))")
    return subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND), env=env,
                          capture_output=True, text=True, timeout=120)


def test_app_runtime_engine_targets_the_same_database_alembic_migrated(live_pg):
    r = _runtime_engine_url_masked(live_pg.url, "enforce")
    assert r.returncode == 0, r.stderr[-500:]
    want = make_url(live_pg.url).render_as_string(hide_password=True)
    assert r.stdout.strip().splitlines()[-1] == want


def test_enforce_mode_refuses_a_non_psycopg_or_missing_database_url(live_pg):
    sqlite = _runtime_engine_url_masked("sqlite:///x.db", "enforce")
    assert sqlite.returncode != 0 and "postgresql+psycopg" in sqlite.stderr
    bad_mode = _runtime_engine_url_masked(live_pg.url, "enforc")
    assert bad_mode.returncode != 0 and "Invalid AMC_VERIFIED_SERVING_MODE" in bad_mode.stderr
