"""Stand up the REAL Wave 4.0 pilot stack for a browser run (TDS-40 E11.6) and keep it running.

Same as tests/live31/pilot_demo31.py (disposable migrated PostgreSQL, generation A published for tenant_alpha and
tenant_beta through the real worker, real app in enforce mode serving the BUILT frontend, local LLM stand-in),
plus the signed, two-person-approved fund dataset for tenant_alpha and the Wave 4.0 flags:
AMC_FIN_PLANE, AMC_NUMERIC_GUARD, AMC_QE_POSTGRES and AMC_PILOT_FEEDBACK on.

Writes <state-dir>/demo.json (url, database, user passwords) for the browser suite; nothing secret is printed.
Build the frontend first with VITE_AMC_PILOT_MODE=true and VITE_AMC_PILOT_FEEDBACK=true.

    python -m tests.live40.pilot_demo40 --state-dir <dir>
    python -m tests.live40.pilot_demo40 --cleanup <dir>
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

from neo4j import GraphDatabase  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from amc_publication import fin40  # noqa: E402
from amc_publication.approvals31 import ApprovalVerifier  # noqa: E402
from tests.live31 import guard, support, http_support as hs  # noqa: E402
from tests.live31.llm_stub import LlmStub  # noqa: E402
from tests.live31.pilot_demo31 import cleanup  # noqa: E402

CHUNKS = BACKEND / "data" / "source_docs" / "chunks"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", type=Path)
    ap.add_argument("--cleanup", type=Path)
    args = ap.parse_args()
    if args.cleanup:
        return cleanup(args.cleanup)
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True)
    admin_url = os.environ["AMC_LIVE_PG_URL"]
    guard.assert_local_targets(pg_url=admin_url, neo4j_uri=os.environ["NEO4J_URI"])
    name = "amc_demo40_" + uuid.uuid4().hex[:6]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    support.alembic_cmd(url, "upgrade", "head")
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    support.clean_graph(driver)
    stack = support.make_stack(sessions, driver, state / "faiss")
    for tenant in (support.ALPHA, support.BETA):
        ent, attr, _ = support.graph_target(tenant, "A")
        support.seed_graph(driver, tenant, ent, attr, "legacy")
        stack.submit(tenant, "A")
        assert stack.worker().run_once()["status"] == "published"
    with sessions.begin() as s:
        version = fin40.stage_dataset(s, tenant=support.ALPHA, chunks_dir=CHUNKS, signer=stack.keys.signer).dataset_version
    with sessions() as s:
        manifest = s.get(fin40.FinDatasetVersion, version).manifest
    record = stack.keys.approval(fin40.activation_subject(tenant=support.ALPHA, dataset_version=version,
                                                          manifest=manifest, proposal_id="DEMO40", revision=1))
    trust = json.loads(stack.keys.approver_trust_file.read_text())
    with sessions.begin() as s:
        fin40.activate_dataset(s, tenant=support.ALPHA, dataset_version=version, approval_record=record,
                               approval_verifier=ApprovalVerifier(trust["approvers"]),
                               generation_verifier=stack.keys.verifier)
    creds = {u: hs.random_secret(10) for u in ("alpha_analyst", "beta_analyst")}
    hs.seed_user(engine, username="alpha_analyst", password=creds["alpha_analyst"], tenant=support.ALPHA)
    hs.seed_user(engine, username="beta_analyst", password=creds["beta_analyst"], tenant=support.BETA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=url, faiss_root=state / "faiss", llm_url=stub.url, log_path=state / "app.log",
                          public_keys_file=stack.keys.public_keys_file,
                          extra_env={"VITE_AMC_PILOT_MODE": "true", "AMC_FIN_PLANE": "on", "AMC_NUMERIC_GUARD": "on",
                                     "AMC_QE_POSTGRES": "on", "AMC_PILOT_FEEDBACK": "on",
                                     "AMC_PILOT_TENANTS": support.ALPHA})
    server.start()
    (state / "demo.json").write_text(json.dumps({
        "url": server.base, "database": name, "users": creds, "fin_dataset_version": version,
        "tenants": {"alpha_analyst": support.ALPHA, "beta_analyst": support.BETA}}))
    print("READY", server.base, flush=True)
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        stub.stop()
        support.clean_graph(driver)
        driver.close()


if __name__ == "__main__":
    main()
