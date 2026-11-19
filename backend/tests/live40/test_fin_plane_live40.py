"""Wave 4.0 E1 on a real PostgreSQL: migration 016 matches the models, the real dataset stages and serves with
results identical to SQLite, and concurrent activations serialize on the scope-claim row lock."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker

from amc_publication import fin40 as fin
from amc_publication.approvals31 import ApprovalVerifier, ApproverSigner, generate_approver_keypair, new_record
from amc_publication.fin_query40 import FinPlan
from amc_publication.models import Base
from amc_publication.signing31 import GenerationSigner, GenerationVerifier, generate_keypair
from amc_publication.structured_serving40 import VerifiedStructuredExecutor
from amc_publication.types import Conflict

CHUNKS = Path(__file__).resolve().parents[2] / "data" / "source_docs" / "chunks"


@pytest.fixture
def keys():
    priv, pub = generate_keypair()
    a_priv, a_pub = generate_approver_keypair()
    b_priv, b_pub = generate_approver_keypair()
    return {"signer": GenerationSigner("pub-k", priv), "verifier": GenerationVerifier({"pub-k": pub}),
            "approvers": ApprovalVerifier({"steward": {"roles": ["proposer"], "keys": {"sk": a_pub}},
                                           "compliance": {"roles": ["reviewer"], "keys": {"ck": b_pub}}}),
            "p": ApproverSigner("steward", "sk", a_priv), "r": ApproverSigner("compliance", "ck", b_priv)}


def _sessions(live_pg):
    return sessionmaker(bind=live_pg.engine, expire_on_commit=False)


def _record(keys, sessions, tenant, version, proposal):
    with sessions() as s:
        manifest = s.get(fin.FinDatasetVersion, version).manifest
    rec = new_record(fin.activation_subject(tenant=tenant, dataset_version=version, manifest=manifest,
                                            proposal_id=proposal, revision=1))
    return keys["r"].sign(keys["p"].sign(rec, "proposer"), "reviewer")


def _mini(tmp: Path, name: str, nav: str) -> Path:
    import json
    d = tmp / name
    d.mkdir()
    rows = [f"1001,A Fund,A AMC,Open Ended,Equity,A Fund - Direct - Growth,1,{nav},2026-06-29,10.5,January - March 2026,-,-,-,,"]
    (d / "c.csv").write_text(",".join(fin.EXPECTED_HEADER) + "\n" + "\n".join(rows) + "\n")
    (d / "manifest.json").write_text(json.dumps({"original_rows": 1, "chunk_count": 1, "chunks": [
        {"chunk_num": 1, "filename": "c.csv", "rows": 1, "start_row": 1, "end_row": 1}]}))
    return d


def test_migrations_016_017_match_models_and_evidence_is_append_only(live_pg):
    from amc_publication.evidence40 import EVIDENCE_TABLES
    with live_pg.engine.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == "017_query_evidence_feedback_v40"
        for table in ("query_evidence_v40", "pilot_feedback_v40"):
            for priv in ("UPDATE", "DELETE", "TRUNCATE"):
                assert c.execute(text("select has_table_privilege('public', :t, :p)"),
                                 {"t": table, "p": priv}).scalar() is False, (table, priv)
    insp = inspect(live_pg.engine)
    for table in fin.FIN_TABLES + EVIDENCE_TABLES:
        migrated = {col["name"]: col for col in insp.get_columns(table.name)}
        assert set(migrated) == set(table.columns.keys()), table.name
        for col in table.columns:
            assert migrated[col.name]["nullable"] == col.nullable, f"{table.name}.{col.name}"


def test_real_dataset_on_postgres_matches_sqlite(live_pg, keys, tmp_path):
    pg = _sessions(live_pg)
    with pg.begin() as s:
        version = fin.stage_dataset(s, tenant="tenant_alpha", chunks_dir=CHUNKS, signer=keys["signer"]).dataset_version
    with pg.begin() as s:
        fin.activate_dataset(s, tenant="tenant_alpha", dataset_version=version,
                             approval_record=_record(keys, pg, "tenant_alpha", version, "P1"),
                             approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
    sqlite_engine = create_engine("sqlite:///" + str(tmp_path / "parity.sqlite"))
    Base.metadata.create_all(sqlite_engine)
    lite = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with lite.begin() as s:
        assert fin.stage_dataset(s, tenant="tenant_alpha", chunks_dir=CHUNKS,
                                 signer=keys["signer"]).dataset_version == version
    with lite.begin() as s:
        fin.activate_dataset(s, tenant="tenant_alpha", dataset_version=version,
                             approval_record=_record(keys, lite, "tenant_alpha", version, "P1"),
                             approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
    on_pg = VerifiedStructuredExecutor(pg, keys["verifier"])
    on_lite = VerifiedStructuredExecutor(lite, keys["verifier"])
    for plan in (FinPlan("TOP_AMC_AAUM", limit=10), FinPlan("TOP_SCHEME_AAUM", limit=10),
                 FinPlan("CATEGORY_AAUM_SHARE", limit=40), FinPlan("NAV_LOOKUP", scheme_code="100033"),
                 FinPlan("COUNT_SCHEMES"), FinPlan("DATASET_SUMMARY")):
        a, b = on_pg.execute("tenant_alpha", plan), on_lite.execute("tenant_alpha", plan)
        assert a.rows == b.rows and a.result_set_hash == b.result_set_hash, plan.intent
    assert on_pg.execute("tenant_alpha", FinPlan("NAV_LOOKUP", scheme_code="100033")).rows[0][3] == "922.670000"
    sqlite_engine.dispose()


def test_concurrent_activations_serialize_and_stay_consistent(live_pg, keys, tmp_path):
    sessions = _sessions(live_pg)
    versions = []
    for i, nav in enumerate(("10.1", "10.2", "10.3", "10.4")):
        with sessions.begin() as s:
            versions.append(fin.stage_dataset(s, tenant="T", chunks_dir=_mini(tmp_path, f"m{i}", nav),
                                              signer=keys["signer"]).dataset_version)
    records = [_record(keys, sessions, "T", v, f"P{i}") for i, v in enumerate(versions)]
    barrier, outcomes = threading.Barrier(len(versions)), []

    def go(v, rec):
        barrier.wait()
        try:
            with sessions.begin() as s:
                fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record=rec,
                                     approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
            outcomes.append(("ok", v))
        except Conflict as exc:
            outcomes.append(("conflict", str(exc)))

    threads = [threading.Thread(target=go, args=(v, r)) for v, r in zip(versions, records)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    wins = [v for kind, v in outcomes if kind == "ok"]
    assert len(outcomes) == len(versions) and wins, outcomes
    with sessions() as s:
        pin = fin.current_pin(s, "T")
        statuses = dict(s.execute(select(fin.FinDatasetVersion.dataset_version, fin.FinDatasetVersion.status)).all())
        receipts = s.scalars(select(fin.FinPublicationReceipt).order_by(fin.FinPublicationReceipt.created_at)).all()
    assert pin.epoch == len(wins) and pin.dataset_version in wins
    assert list(statuses.values()).count("ACTIVE") == 1 and statuses[pin.dataset_version] == "ACTIVE"
    assert len(receipts) == len(wins)
    # every successful activation saw the previous winner as its predecessor: a single linear history
    previous = {r.previous_dataset_version for r in receipts}
    assert None in previous and len(previous) == len(receipts)
