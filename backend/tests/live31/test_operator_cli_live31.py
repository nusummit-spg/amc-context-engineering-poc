"""WP08: the offline operator CLI drives the production worker against real PostgreSQL/Neo4j/FAISS,
and what it publishes is then served by the REAL app over HTTP."""
import json
import os
import subprocess
import sys
import uuid

import pytest

from tests.live31 import support, http_support as hs
from tests.live31.llm_stub import LlmStub
from tests.live31.support import ALPHA, fx, pg_state, read_graph, seed_graph

BACKEND = hs.BACKEND


def _cli(live_pg, root, *args, env_extra=None, expect=0):
    env = {**os.environ, "DATABASE_URL": live_pg.url, "AMC_VERIFIED_FAISS_ROOT": str(root),
           "AMC_PUBLICATION_GRAPH_ATTRIBUTES": "ter,exit_load",
           "AMC_PUBLICATION_EMBEDDER": "tests.live31.support:HashEmbedder",
           "PYTHONPATH": f"{BACKEND}{os.pathsep}{BACKEND.parent}", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("AMC_MIGRATION_DATABASE_URL", None)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, "-m", "amc_publication.operator_cli", *args], cwd=str(BACKEND), env=env,
                       capture_output=True, text=True, timeout=180)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert r.returncode == expect, (args, r.returncode, r.stdout[-400:], r.stderr[-400:])
    return out


def _submit(live_pg, root, tmp_path, tenant, generation, *, proposer="alice", reviewer="bob", attest=True, rev=1):
    entity, attr, value = support.graph_target(tenant, generation)
    corpus = tmp_path / f"corpus_{tenant}_{generation}.json"
    corpus.write_text(json.dumps(support.snapshot(tenant, generation)))
    args = ["submit", "--tenant", tenant, "--entity", entity, "--attribute", attr, "--value", value,
            "--corpus", str(corpus), "--proposal-id", f"P-{generation}", "--revision", str(rev),
            "--proposer", proposer, "--reviewer", reviewer]
    if attest:
        args.append("--attest-independent-approval")
    return args


@pytest.fixture
def ops(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    root = tmp_path / "faiss"
    root.mkdir()
    yield type("Ops", (), {"pg": live_pg, "root": root, "driver": live_neo4j_driver, "tmp": tmp_path})()
    support.clean_graph(live_neo4j_driver)


def test_submit_run_once_status_and_rollback_through_the_cli(ops):
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    out = _cli(ops.pg, ops.root, *_submit(ops.pg, ops.root, ops.tmp, ALPHA, "A"))
    work_a = out["work_id"]
    assert _cli(ops.pg, ops.root, "run-once")["status"] == "published"
    st = _cli(ops.pg, ops.root, "status", "--tenant", ALPHA)
    assert st["authority"]["status"] == "ACTIVE" and st["authority"]["work"] == work_a and st["attention"] == []
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.21"

    work_b = _cli(ops.pg, ops.root, *_submit(ops.pg, ops.root, ops.tmp, ALPHA, "B"))["work_id"]
    assert _cli(ops.pg, ops.root, "run-once")["status"] == "published"
    assert _cli(ops.pg, ops.root, "status", "--tenant", ALPHA)["authority"]["work"] == work_b
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.19"

    out = _cli(ops.pg, ops.root, "rollback", "--tenant", ALPHA, "--work-id", work_b)
    assert "suspended" in out["serving"]
    sus = _cli(ops.pg, ops.root, "status", "--tenant", ALPHA)
    assert sus["authority"]["status"] == "SUSPENDED" and sus["attention"], "status must flag the suspension"
    assert _cli(ops.pg, ops.root, "run-once")["status"] == "rolled_back"
    st = _cli(ops.pg, ops.root, "status", "--tenant", ALPHA)
    assert st["authority"]["work"] == work_a and st["authority"]["status"] == "ACTIVE" and st["attention"] == []
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.21"
    assert _cli(ops.pg, ops.root, "run-once")["status"] == "no_jobs"


@pytest.mark.parametrize("kwargs,reason", [
    ({"attest": False}, "attest-independent-approval"),
    ({"proposer": "alice", "reviewer": "alice"}, "must differ"),
    ({"proposer": "", "reviewer": "bob"}, "mandatory"),
])
def test_submit_refuses_without_independent_approval(ops, kwargs, reason):
    out = _cli(ops.pg, ops.root, *_submit(ops.pg, ops.root, ops.tmp, ALPHA, "A", **kwargs), expect=2)
    assert out["ok"] is False and reason in out["refused"]
    assert pg_state(ops.pg.sessions, ALPHA)["works"] == {}, "nothing may be queued on a refusal"


def test_submit_refuses_a_corpus_row_from_another_tenant(ops):
    args = _submit(ops.pg, ops.root, ops.tmp, ALPHA, "A")
    rows = support.snapshot(ALPHA, "A") + support.snapshot(support.BETA, "A")[:1]
    (ops.tmp / f"corpus_{ALPHA}_A.json").write_text(json.dumps(rows))
    out = _cli(ops.pg, ops.root, *args, expect=2)
    assert "tenant_id == --tenant" in out["refused"]


def test_the_cli_refuses_a_non_postgres_or_unmigrated_database(ops):
    out = _cli(ops.pg, ops.root, "status", "--tenant", ALPHA, env_extra={"DATABASE_URL": "sqlite:///x.db"}, expect=2)
    assert "postgresql+psycopg" in out["refused"]
    support.alembic_cmd(ops.pg.url, "downgrade", "014_publication_scope_claim_v31")
    out = _cli(ops.pg, ops.root, "status", "--tenant", ALPHA, expect=2)
    assert "revision 015" in out["refused"]


def test_status_is_read_only(ops):
    before = pg_state(ops.pg.sessions, ALPHA)
    for _ in range(3):
        _cli(ops.pg, ops.root, "status", "--tenant", ALPHA)
    assert pg_state(ops.pg.sessions, ALPHA) == before


def test_what_the_operator_publishes_is_served_by_the_real_app(ops, tmp_path):
    """Operator CLI -> PostgreSQL/Neo4j/FAISS -> real app over HTTP, then rollback is visible without a restart."""
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    _cli(ops.pg, ops.root, *_submit(ops.pg, ops.root, ops.tmp, ALPHA, "A"))
    _cli(ops.pg, ops.root, "run-once")
    pw = hs.random_secret(12)
    hs.seed_user(ops.pg.engine, username="alpha_analyst", password=pw, tenant=ALPHA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=ops.pg.url, faiss_root=ops.root, llm_url=stub.url, log_path=tmp_path / "app.log")
    try:
        server.start()
        with server.client() as c:
            tok = hs.login(c, "alpha_analyst", pw).json()["token"]
            q = fx.probes(ALPHA)[0]["query"]
            r = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert r.status_code == 200 and "0.21" in r.text and "0.19" not in r.text
            work_b = _cli(ops.pg, ops.root, *_submit(ops.pg, ops.root, ops.tmp, ALPHA, "B"))["work_id"]
            _cli(ops.pg, ops.root, "run-once")
            r = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert r.status_code == 200 and "0.19" in r.text, "the new generation is served without restarting the app"
            _cli(ops.pg, ops.root, "rollback", "--tenant", ALPHA, "--work-id", work_b)
            denied = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert denied.status_code >= 400 and "0.19" not in denied.text and "0.21" not in denied.text
            _cli(ops.pg, ops.root, "run-once")
            back = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert back.status_code == 200 and "0.21" in back.text and "0.19" not in back.text
    finally:
        server.stop()
        stub.stop()
