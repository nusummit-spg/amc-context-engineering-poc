"""WP08 + review P0s: the offline operator CLI drives the production worker against real PostgreSQL/Neo4j/FAISS
with VERIFIED two-person approval evidence and SIGNED generations, and what it publishes is served by the real app."""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from amc_publication import approvals31 as ap
from tests.live31 import support, http_support as hs
from tests.live31.llm_stub import LlmStub
from tests.live31.support import ALPHA, BETA, fx, pg_state, read_graph, seed_graph

BACKEND = hs.BACKEND


@pytest.fixture
def ops(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    root = tmp_path / "faiss"
    root.mkdir()
    keys = support.make_keys(tmp_path / "keys")
    yield type("Ops", (), {"pg": live_pg, "root": root, "driver": live_neo4j_driver, "tmp": tmp_path, "keys": keys})()
    support.clean_graph(live_neo4j_driver)


def _cli(ops, *args, env_extra=None, drop=(), expect=0):
    env = {**os.environ, "DATABASE_URL": ops.pg.url, "AMC_VERIFIED_FAISS_ROOT": str(ops.root),
           "AMC_PUBLICATION_GRAPH_ATTRIBUTES": "ter,exit_load",
           "AMC_PUBLICATION_EMBEDDER": "tests.live31.support:HashEmbedder",
           "PYTHONPATH": f"{BACKEND}{os.pathsep}{BACKEND.parent}", "PYTHONDONTWRITEBYTECODE": "1", **ops.keys.env()}
    env.pop("AMC_MIGRATION_DATABASE_URL", None)
    for name in drop:
        env.pop(name, None)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, "-m", "amc_publication.operator_cli", *args], cwd=str(BACKEND), env=env,
                       capture_output=True, text=True, timeout=180)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert r.returncode == expect, (args, r.returncode, r.stdout[-400:], r.stderr[-400:])
    return out


def _subject(tenant, generation, **over):
    entity, attr, value = support.graph_target(tenant, generation)
    base = dict(tenant=tenant, entity=entity, attribute=attr, value=value, proposal_id=f"P-{generation}",
                revision=1, corpus=support.snapshot(tenant, generation))
    base.update(over)
    return ap.make_subject(**base)


def _submit_args(ops, tenant, generation, *, record=None, record_path=None, corpus=None, **kw):
    """Write the corpus and an approval record to disk and return the CLI arguments for `submit`."""
    entity, attr, value = support.graph_target(tenant, generation)
    rows = corpus if corpus is not None else support.snapshot(tenant, generation)
    corpus_path = ops.tmp / f"corpus_{tenant}_{generation}.json"
    corpus_path.write_text(json.dumps(rows))
    if record_path is None:
        record = record if record is not None else ops.keys.approval(_subject(tenant, generation), **kw)
        record_path = ops.tmp / f"approval_{tenant}_{generation}.json"
        record_path.write_text(json.dumps(record))
    return ["submit", "--tenant", tenant, "--entity", entity, "--attribute", attr, "--value", value,
            "--corpus", str(corpus_path), "--proposal-id", f"P-{generation}", "--revision", "1",
            "--approval", str(record_path)]


def _works_in(ops, tenant):
    return pg_state(ops.pg.sessions, tenant)["works"]


# ----------------------------------------------------------------------------- the happy path, end to end


def test_submit_run_once_status_and_rollback_through_the_cli(ops):
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    out = _cli(ops, *_submit_args(ops, ALPHA, "A"))
    work_a = out["work_id"]
    assert (out["proposer"], out["reviewer"]) == ("alice", "bob") and len(out["approval_sha256"]) == 64
    assert _cli(ops, "run-once")["status"] == "published"
    st = _cli(ops, "status", "--tenant", ALPHA)
    assert st["authority"]["status"] == "ACTIVE" and st["authority"]["work"] == work_a and st["attention"] == []
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.21"

    work_b = _cli(ops, *_submit_args(ops, ALPHA, "B", proposer="carol", reviewer="alice"))["work_id"]
    assert _cli(ops, "run-once")["status"] == "published"
    assert _cli(ops, "status", "--tenant", ALPHA)["authority"]["work"] == work_b
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.19"

    out = _cli(ops, "rollback", "--tenant", ALPHA, "--work-id", work_b)
    assert "suspended" in out["serving"]
    sus = _cli(ops, "status", "--tenant", ALPHA)
    assert sus["authority"]["status"] == "SUSPENDED" and sus["attention"], "status must flag the suspension"
    assert _cli(ops, "run-once")["status"] == "rolled_back"
    st = _cli(ops, "status", "--tenant", ALPHA)
    assert st["authority"]["work"] == work_a and st["authority"]["status"] == "ACTIVE" and st["attention"] == []
    assert read_graph(ops.driver, ALPHA, entity, attr) == "0.21"
    assert _cli(ops, "run-once")["status"] == "no_jobs"


def test_the_signed_approval_is_stored_with_the_work_and_every_generation_is_signed(ops):
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    args = _submit_args(ops, ALPHA, "A")
    work = _cli(ops, *args)["work_id"]
    _cli(ops, "run-once")
    stored = json.loads(open(args[args.index("--approval") + 1], encoding="utf-8").read())
    with ops.pg.engine.connect() as c:
        payload = c.execute(text("select payload from publication_work_v2 where id = :w"), {"w": work}).scalar()
    payload = payload if isinstance(payload, dict) else json.loads(payload)
    assert payload["approval"] == stored, "the exact signed record must be durable evidence on the work"
    assert [a["role"] for a in payload["approval"]["approvals"]] == ["proposer", "reviewer"]
    dirs = [p for p in ops.root.rglob("signature.json")]
    assert dirs, "the published generation must carry a signature"
    sig = json.loads(dirs[0].read_text())
    assert sig["alg"] == "ed25519" and sig["key_id"] == "pub-live31"


# ----------------------------------------------------------------------------- approval evidence is verified, not attested


def _variants(ops):
    """Each way an approval can be wrong, as (record, message that the refusal must contain)."""
    now = datetime.now(timezone.utc)
    good = _subject(ALPHA, "A")
    k = ops.keys
    mallory_priv, _ = ap.generate_approver_keypair()
    mallory = ap.ApproverSigner("mallory", "mallory-1", mallory_priv)
    forged_priv, _ = ap.generate_approver_keypair()
    forged_bob = ap.ApproverSigner("bob", "bob-live31", forged_priv)
    proposer_only = k.approvers["alice"].sign(ap.new_record(good), "proposer")
    return {
        "same_person": (k.approval(good, proposer="alice", reviewer="alice"), "different people"),
        "only_proposer": (proposer_only, "exactly one proposer and one reviewer"),
        "wrong_value": (k.approval(_subject(ALPHA, "A", value="9.99")), "value differs"),
        "wrong_tenant": (k.approval(_subject(BETA, "A", corpus=support.snapshot(BETA, "A"))), "tenant differs"),
        "other_corpus": (k.approval(_subject(ALPHA, "A", corpus=support.snapshot(ALPHA, "B"))), "corpus_sha256 differs"),
        "expired": (k.approval(good, now=now - timedelta(days=10), valid_for=timedelta(days=1)), "expired"),
        "forged_reviewer": (forged_bob.sign(proposer_only, "reviewer"), "signature is invalid"),
        "untrusted_approver": (mallory.sign(proposer_only, "reviewer"), "not in the trust store"),
    }


@pytest.mark.parametrize("case", ["same_person", "only_proposer", "wrong_value", "wrong_tenant", "other_corpus",
                                  "expired", "forged_reviewer", "untrusted_approver"])
def test_submit_refuses_approval_evidence_that_does_not_verify(ops, case):
    record, message = _variants(ops)[case]
    out = _cli(ops, *_submit_args(ops, ALPHA, "A", record=record), expect=2)
    assert out["ok"] is False and "approval refused" in out["refused"] and message in out["refused"], out
    assert _works_in(ops, ALPHA) == {}, "nothing may be queued on a refusal"


def test_submit_refuses_a_revoked_approver_key(ops):
    trust = json.loads(ops.keys.approver_trust_file.read_text())
    trust["revoked"] = ["bob-live31"]
    ops.keys.approver_trust_file.write_text(json.dumps(trust))
    out = _cli(ops, *_submit_args(ops, ALPHA, "A"), expect=2)
    assert "revoked" in out["refused"] and _works_in(ops, ALPHA) == {}


def test_submit_refuses_a_missing_or_unreadable_approval_and_a_missing_trust_store(ops):
    args = _submit_args(ops, ALPHA, "A")
    out = _cli(ops, *args[:-1], str(ops.tmp / "nope.json"), expect=2)
    assert "missing or not valid JSON" in out["refused"]
    (ops.tmp / "junk.json").write_text("{not json")
    assert "missing or not valid JSON" in _cli(ops, *args[:-1], str(ops.tmp / "junk.json"), expect=2)["refused"]
    out = _cli(ops, *args, drop=("AMC_PUBLICATION_APPROVER_KEYS",), expect=2)
    assert "AMC_PUBLICATION_APPROVER_KEYS is required" in out["refused"]
    assert _works_in(ops, ALPHA) == {}


def test_the_old_self_attestation_flags_no_longer_exist(ops):
    args = _submit_args(ops, ALPHA, "A")
    r = subprocess.run([sys.executable, "-m", "amc_publication.operator_cli", *args, "--proposer", "a",
                        "--reviewer", "b", "--attest-independent-approval"], cwd=str(BACKEND),
                       env={**os.environ, "PYTHONPATH": f"{BACKEND}{os.pathsep}{BACKEND.parent}"},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "unrecognized arguments" in r.stderr


def test_submit_refuses_a_corpus_row_from_another_tenant(ops):
    rows = support.snapshot(ALPHA, "A") + support.snapshot(BETA, "A")[:1]
    out = _cli(ops, *_submit_args(ops, ALPHA, "A", corpus=rows), expect=2)
    assert "tenant_id == --tenant" in out["refused"]


# ----------------------------------------------------------------------------- the worker re-verifies at execution time


def test_a_work_queued_without_approval_evidence_is_refused_before_any_effect(ops):
    """Someone with database access inserts a publication directly; the CLI's worker must not execute it."""
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    stack = support.make_stack(ops.pg.sessions, ops.driver, ops.root, keys=ops.keys)
    stack.submit(ALPHA, "A")                                         # no "approval" in the payload
    out = _cli(ops, "run-once", expect=2)
    assert out["status"] == "failed" and "no approval evidence" in out["error"], out
    st = pg_state(ops.pg.sessions, ALPHA)
    assert st["receipts"] == [] and st["authority"] is None and st["effects"] == []
    assert read_graph(ops.driver, ALPHA, entity, attr) == "legacy", "the graph must be untouched"


def test_a_payload_altered_after_approval_is_refused_before_any_effect(ops):
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    work = _cli(ops, *_submit_args(ops, ALPHA, "A"))["work_id"]
    with ops.pg.engine.begin() as c:                                 # tamper with the queued value
        payload = c.execute(text("select payload from publication_work_v2 where id = :w"), {"w": work}).scalar()
        payload = payload if isinstance(payload, dict) else json.loads(payload)
        payload["corrected_value"] = "99.99"
        c.execute(text("update publication_work_v2 set payload = cast(:p as json) where id = :w"),
                  {"p": json.dumps(payload), "w": work})
    out = _cli(ops, "run-once", expect=2)
    assert out["status"] == "failed" and "value differs" in out["error"], out
    assert read_graph(ops.driver, ALPHA, entity, attr) == "legacy"
    assert pg_state(ops.pg.sessions, ALPHA)["receipts"] == []


# ----------------------------------------------------------------------------- generation signing is required to publish


@pytest.mark.parametrize("case,message", [
    ("no_signing_key", "AMC_PUBLICATION_SIGNING_KEY_FILE is required"),
    ("no_public_keys", "AMC_VERIFIED_FAISS_PUBLIC_KEYS is required"),
    ("untrusted_signing_key", "not trusted"),
    ("revoked_signing_key", "not trusted"),
    ("no_approver_keys", "AMC_PUBLICATION_APPROVER_KEYS is required"),
])
def test_run_once_refuses_to_publish_without_a_trusted_signing_key(ops, case, message):
    _cli(ops, *_submit_args(ops, ALPHA, "A"))
    drop, extra = (), {}
    if case == "no_signing_key":
        drop = ("AMC_PUBLICATION_SIGNING_KEY_FILE",)
    elif case == "no_public_keys":
        drop = ("AMC_VERIFIED_FAISS_PUBLIC_KEYS",)
    elif case == "no_approver_keys":
        drop = ("AMC_PUBLICATION_APPROVER_KEYS",)
    elif case == "untrusted_signing_key":
        other = support.make_keys(ops.tmp / "other_keys")
        extra = {"AMC_VERIFIED_FAISS_PUBLIC_KEYS": str(other.public_keys_file)}       # trusts a different publisher
    elif case == "revoked_signing_key":
        pk = json.loads(ops.keys.public_keys_file.read_text())
        pk["revoked"] = ["pub-live31"]
        ops.keys.public_keys_file.write_text(json.dumps(pk))
    out = _cli(ops, "run-once", drop=drop, env_extra=extra, expect=2)
    assert message in out["refused"], out
    assert not list(ops.root.rglob("manifest.json")), "nothing may be staged when signing is refused"
    assert pg_state(ops.pg.sessions, ALPHA)["receipts"] == []


# ----------------------------------------------------------------------------- unchanged behavior


@pytest.mark.parametrize("env_extra,drop,reason", [
    ({"DATABASE_URL": "sqlite:///x.db"}, (), "postgresql+psycopg"),
])
def test_the_cli_refuses_a_non_postgres_database(ops, env_extra, drop, reason):
    out = _cli(ops, "status", "--tenant", ALPHA, env_extra=env_extra, drop=drop, expect=2)
    assert reason in out["refused"]


def test_the_cli_refuses_a_database_left_at_014(ops):
    support.alembic_cmd(ops.pg.url, "downgrade", "014_publication_scope_claim_v31")
    assert "revision 017" in _cli(ops, "status", "--tenant", ALPHA, expect=2)["refused"]


def test_status_is_read_only(ops):
    before = pg_state(ops.pg.sessions, ALPHA)
    for _ in range(3):
        _cli(ops, "status", "--tenant", ALPHA)
    assert pg_state(ops.pg.sessions, ALPHA) == before


def test_what_the_operator_publishes_is_served_by_the_real_app(ops, tmp_path):
    """Operator CLI -> PostgreSQL/Neo4j/FAISS -> real app over HTTP, then rollback is visible without a restart."""
    entity, attr, _ = support.graph_target(ALPHA, "A")
    seed_graph(ops.driver, ALPHA, entity, attr, "legacy")
    _cli(ops, *_submit_args(ops, ALPHA, "A"))
    _cli(ops, "run-once")
    pw = hs.random_secret(12)
    hs.seed_user(ops.pg.engine, username="alpha_analyst", password=pw, tenant=ALPHA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=ops.pg.url, faiss_root=ops.root, llm_url=stub.url, log_path=tmp_path / "app.log",
                          public_keys_file=ops.keys.public_keys_file)
    try:
        server.start()
        with server.client() as c:
            tok = hs.login(c, "alpha_analyst", pw).json()["token"]
            q = fx.probes(ALPHA)[0]["query"]
            r = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert r.status_code == 200 and "0.21" in r.text and "0.19" not in r.text
            work_b = _cli(ops, *_submit_args(ops, ALPHA, "B"))["work_id"]
            _cli(ops, "run-once")
            r = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert r.status_code == 200 and "0.19" in r.text, "the new generation is served without restarting the app"
            _cli(ops, "rollback", "--tenant", ALPHA, "--work-id", work_b)
            denied = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert denied.status_code >= 400 and "0.19" not in denied.text and "0.21" not in denied.text
            _cli(ops, "run-once")
            back = c.post("/api/query", json={"query": q}, headers=hs.bearer(tok))
            assert back.status_code == 200 and "0.21" in back.text and "0.19" not in back.text
    finally:
        server.stop()
        stub.stop()
