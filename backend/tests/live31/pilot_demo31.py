"""Stand up the REAL pilot stack and keep it running for a browser walkthrough (WP07).

Creates a disposable migrated PostgreSQL database, publishes generation A for tenant_alpha and
tenant_beta through the real worker, seeds users, and starts the real app in enforce mode (serving the
built frontend) plus the local LLM stand-in. Writes connection details to <state-dir>/demo.json and then
waits. Stop with Ctrl+C / kill; run with --cleanup <state-dir> to drop the database afterwards.

    python -m tests.live31.pilot_demo31 --state-dir C:\\amc-work\\evidence\\pilot-demo
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

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from tests.live31 import support, http_support as hs  # noqa: E402
from tests.live31.llm_stub import LlmStub  # noqa: E402


def cleanup(state_dir: Path):
    info = json.loads((state_dir / "demo.json").read_text())
    admin = create_engine(os.environ["AMC_LIVE_PG_URL"], isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{info["database"]}" WITH (FORCE)'))
    print("dropped", info["database"])


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
    from tests.live31 import guard
    guard.assert_local_targets(pg_url=admin_url, neo4j_uri=os.environ["NEO4J_URI"])
    name = "amc_demo_" + uuid.uuid4().hex[:6]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    support.alembic_cmd(url, "upgrade", "head")
    engine = create_engine(url)
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    support.clean_graph(driver)
    stack = support.make_stack(sessionmaker(bind=engine), driver, state / "faiss")
    for tenant in (support.ALPHA, support.BETA):
        ent, attr, _ = support.graph_target(tenant, "A")
        support.seed_graph(driver, tenant, ent, attr, "legacy")
        stack.submit(tenant, "A")
        assert stack.worker().run_once()["status"] == "published"
    creds = {u: hs.random_secret(10) for u in ("alpha_analyst", "beta_analyst")}
    hs.seed_user(engine, username="alpha_analyst", password=creds["alpha_analyst"], tenant=support.ALPHA)
    hs.seed_user(engine, username="beta_analyst", password=creds["beta_analyst"], tenant=support.BETA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=url, faiss_root=state / "faiss", llm_url=stub.url, log_path=state / "app.log",
                          extra_env={"VITE_AMC_PILOT_MODE": "true"}, public_keys_file=stack.keys.public_keys_file)
    server.start()
    (state / "demo.json").write_text(json.dumps({"url": server.base, "database": name, "users": creds,
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
