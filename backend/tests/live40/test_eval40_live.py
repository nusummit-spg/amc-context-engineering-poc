"""Wave 4.0 E5 on the REAL stack: the eval40 harness drives the real app over HTTP (enforce mode, PostgreSQL,
Neo4j, signed FAISS generations, the signed and approved fund dataset) and scores every frozen GS-FIN and
GS-ADV case, including the cross-tenant probes over the synthetic two-tenant corpus.

Stand-ins, exactly as in the live31 HTTP matrix: the LLM (a grounded local stub) and the query embedder. So this
measures the structured path, routing, refusals, grounding, citations and tenant isolation end to end. It does
NOT measure answer quality of a real model: that needs the chosen provider (decision D3) and the SME gold sets.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from amc_publication import fin40
from amc_publication.approvals31 import ApprovalVerifier
from amc_publication.evidence40 import QueryEvidence40
from tests.live31 import http_support as hs
from tests.live31 import support
from tests.live31.llm_stub import LlmStub
from tests.live31.support import ALPHA, BETA
from tools.amc_release import eval40 as ev
from tools.amc_release import gold40

CHUNKS = Path(__file__).resolve().parents[2] / "data" / "source_docs" / "chunks"


@pytest.fixture(scope="module")
def stack_app(live_pg_admin_url, live_template_db, live_neo4j_driver, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("eval40")
    name = "amc_eval40_" + uuid.uuid4().hex[:8]
    admin = create_engine(live_pg_admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{live_template_db}"'))
    url = make_url(live_pg_admin_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url, pool_size=5, max_overflow=10)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(sessions, live_neo4j_driver, tmp / "faiss")
    for tenant in (ALPHA, BETA):
        ent, attr, _ = support.graph_target(tenant, "A")
        support.seed_graph(live_neo4j_driver, tenant, ent, attr, "legacy")
        stack.submit(tenant, "A")
        assert stack.worker().run_once()["status"] == "published"
    # the fund dataset: staged, signed with the same publisher key, two-person approved, activated
    with sessions.begin() as s:
        version = fin40.stage_dataset(s, tenant=ALPHA, chunks_dir=CHUNKS, signer=stack.keys.signer).dataset_version
    with sessions() as s:
        manifest = s.get(fin40.FinDatasetVersion, version).manifest
    record = stack.keys.approval(fin40.activation_subject(tenant=ALPHA, dataset_version=version, manifest=manifest,
                                                          proposal_id="EVAL40", revision=1))
    trust = json.loads(stack.keys.approver_trust_file.read_text())
    with sessions.begin() as s:
        fin40.activate_dataset(s, tenant=ALPHA, dataset_version=version, approval_record=record,
                               approval_verifier=ApprovalVerifier(trust["approvers"]),
                               generation_verifier=stack.keys.verifier)
    password = hs.random_secret(12)
    hs.seed_user(engine, username="alpha_analyst", password=password, tenant=ALPHA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=url, faiss_root=tmp / "faiss", llm_url=stub.url, log_path=tmp / "app.log",
                          public_keys_file=stack.keys.public_keys_file,
                          extra_env={"AMC_FIN_PLANE": "on", "AMC_NUMERIC_GUARD": "on", "AMC_QE_POSTGRES": "on",
                                     "AMC_PILOT_TENANTS": ALPHA})
    server.start()
    yield {"server": server, "sessions": sessions, "password": password, "version": version, "tmp": tmp,
           "stack": stack}
    server.stop()
    stub.stop()
    support.clean_graph(live_neo4j_driver)
    engine.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _signed_generation(stack_app):
    state = support.pg_state(stack_app["sessions"], ALPHA)
    gen = state["authority"]["generation"]
    dirs = [m.parent for m in (stack_app["tmp"] / "faiss").rglob("manifest.json") if gen in str(m.parent)]
    assert len(dirs) == 1, dirs
    return dirs[0], gen


def test_eval40_over_live_http_meets_every_measurable_e5_gate(stack_app):
    manifest, cases = gold40.load_gold(gold40.REPO / "remediation" / "wave4_0" / "gold")
    assert manifest["fin_dataset_version"] == stack_app["version"], "gold is pinned to a different dataset version"
    chosen = [c for c in ev.select_cases(cases, smoke=False, fixtures=["fixtures31"]) if c["status"] == "FROZEN"]
    assert len(chosen) == 250
    responses = ev.run_http(stack_app["server"].base, "alpha_analyst", stack_app["password"], chosen)
    gen_dir, gen_id = _signed_generation(stack_app)
    valid = ev.load_valid_chunks(gen_dir, tenant=ALPHA, generation_id=gen_id,
                                 public_keys=stack_app["stack"].keys.public_keys_file)
    report = ev.score(manifest, chosen, responses, valid_chunks=valid)
    out = Path(os.environ.get("AMC_EVAL40_REPORT_DIR") or stack_app["tmp"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "live_responses.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in responses),
                                              encoding="utf-8")
    (out / "live_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                          encoding="utf-8")
    m = {k: v["value"] for k, v in report["metrics"].items()}
    fails = [(f["case_id"], f["answer_kind"], f["notes"], f["ungrounded_numbers"], f["leaks"])
             for f in report["failures"]]
    print("\nLIVE E5:", json.dumps(m), "\nfailures:", fails[:25])
    assert all(r["http_status"] == 200 for r in responses), [r for r in responses if r["http_status"] != 200][:3]
    assert m["fin_exact_match_p0"] == 1.0 and m["fin_exact_match"] >= 0.99, fails
    assert m["routing_accuracy"] >= 0.98, fails
    assert m["advice_refusal"] == 1.0 and m["cross_tenant_leak"] == 0, fails
    assert m["ungrounded_number_rate"] == 0.0 and m["citation_validity"] == 1.0, fails
    assert m["abstention_should_abstain"] >= 0.95 and m["abstention_answerable"] >= 0.90, fails
    # every released answer has its append-only evidence row, keyed by the request id the harness recorded
    ids = {r["request_id"] for r in responses}
    assert None not in ids and len(ids) == len(responses)
    with stack_app["sessions"]() as s:
        stored = s.scalar(select(func.count()).select_from(QueryEvidence40).where(QueryEvidence40.request_id.in_(ids)))
    assert stored == len(responses)
    # and the overall decision is still BLOCKED: GS-REG / GS-MIX are not authored and no real model was measured
    assert report["decision"] == "BLOCKED"
