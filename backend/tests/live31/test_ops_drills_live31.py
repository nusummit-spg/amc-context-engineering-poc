"""WP08 / gate G8: operational drills on the REAL app and REAL services (no Docker).

Drills stop and start the local PostgreSQL/Neo4j through the same script an operator uses, so they need
AMC_LOCAL_SERVICES_SCRIPT (and AMC_PG_BIN for backup/restore). Without them they are SKIPPED as
LIVE31_BLOCKED, never passed. AMC_LIVE_EVIDENCE_DIR, when set, receives measured numbers as JSON.
"""
import json
import os
import statistics
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from tests.live31 import support, http_support as hs
from tests.live31.llm_stub import LlmStub
from tests.live31.support import ALPHA, fx, pg_state, serving_allowed

QUERY = fx.probes(ALPHA)[0]["query"]


@pytest.fixture(scope="module")
def svc():
    script = os.environ.get("AMC_LOCAL_SERVICES_SCRIPT")
    if not script or not Path(script).is_file():
        pytest.skip("LIVE31_BLOCKED: AMC_LOCAL_SERVICES_SCRIPT is not set (service start/stop drills need it)")

    log = Path(os.environ.get("TEMP", ".")) / "amc_live31_services.log"

    def run(*args):
        # Redirect to a FILE, never a pipe: the services this script starts inherit the handle, and a
        # pipe would make subprocess wait for them to exit (a hang that looks like a stuck drill).
        with open(log, "ab") as fh:
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args],
                           stdout=fh, stderr=subprocess.STDOUT, timeout=240, stdin=subprocess.DEVNULL)
        return log.read_text(errors="replace")[-2000:]

    return run


def _wait_port(port: int, up: bool, timeout=120):
    import socket
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(1)
            is_up = s.connect_ex(("127.0.0.1", port)) == 0
        if is_up == up:
            return True
        time.sleep(1)
    return False


@pytest.fixture
def app(live_pg, live_neo4j_driver, tmp_path):
    """Alpha generation A published, real app running, one logged-in analyst."""
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "faiss", lease_seconds=2)
    entity, attr, _ = support.graph_target(ALPHA, "A")
    support.seed_graph(live_neo4j_driver, ALPHA, entity, attr, "legacy")
    stack.submit(ALPHA, "A")
    assert stack.worker().run_once()["status"] == "published"
    pw = hs.random_secret(12)
    hs.seed_user(live_pg.engine, username="alpha_analyst", password=pw, tenant=ALPHA)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=live_pg.url, faiss_root=tmp_path / "faiss", llm_url=stub.url,
                          log_path=tmp_path / "app.log")
    server.start()
    ns = type("App", (), {})()
    ns.server, ns.stub, ns.stack, ns.pg, ns.pw, ns.tmp, ns.entity, ns.attr = server, stub, stack, live_pg, pw, tmp_path, entity, attr
    ns.driver = live_neo4j_driver

    def login():
        with server.client() as c:
            return hs.login(c, "alpha_analyst", pw).json()["token"]
    ns.login = login
    yield ns
    server.stop()
    stub.stop()
    support.clean_graph(live_neo4j_driver)


def _query(server, token, timeout=60):
    with server.client(timeout=timeout) as c:
        return c.post("/api/query", json={"query": QUERY}, headers=hs.bearer(token))


# ------------------------------------------------------------------------- startup


def _counts(engine):
    with engine.connect() as c:
        tables = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' order by 1"))]
        return tables, {t: c.execute(text(f'select count(*) from "{t}"')).scalar() for t in tables}


def _graph_shape(driver):
    with driver.session() as s:
        nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        cons = sorted(r["name"] for r in s.run("SHOW CONSTRAINTS"))
        idx = sorted(r["name"] for r in s.run("SHOW INDEXES"))
    return {"nodes": nodes, "rels": rels, "constraints": cons, "indexes": idx}


def test_enforce_startup_creates_no_schema_no_rows_and_no_graph_writes(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    tables_before, rows_before = _counts(live_pg.engine)
    graph_before = _graph_shape(live_neo4j_driver)
    stub = LlmStub().start()
    server = hs.AppServer(database_url=live_pg.url, faiss_root=tmp_path / "faiss", llm_url=stub.url,
                          log_path=tmp_path / "app.log")
    try:
        server.start()
        time.sleep(20)                         # long enough for any scheduler or warm-up to fire
        assert httpx.get(server.base + "/health", timeout=10).status_code == 200
    finally:
        server.stop()
        stub.stop()
    tables_after, rows_after = _counts(live_pg.engine)
    assert tables_after == tables_before, "startup created or dropped a table"
    changed = {t: (rows_before[t], rows_after[t]) for t in rows_before if rows_before[t] != rows_after.get(t)}
    assert changed == {}, f"startup wrote rows: {changed}"
    assert _graph_shape(live_neo4j_driver) == graph_before, "startup mutated the graph (schema, seed or data)"
    log = server.log_text()
    assert "Verified pilot: disabled legacy ingest queue" in log
    for forbidden in ("Background TaskScheduler wired", "FAISS store + embedder + reranker warmed up",
                      "Compliance rules and fund schemes initialized", "Feedback loop background tasks"):
        assert forbidden not in log, forbidden


@pytest.mark.parametrize("case,expected", [
    ("bad_mode", "Invalid AMC_VERIFIED_SERVING_MODE"),
    ("sqlite_url", "postgresql+psycopg"),
    ("db_at_014", "revision 015"),
    ("unmigrated", "revision 015"),
])
def test_the_app_refuses_to_start_on_unsafe_configuration(live_pg, live_neo4j_driver, tmp_path, case, expected):
    stub = LlmStub().start()
    url, mode = live_pg.url, "enforce"
    if case == "bad_mode":
        mode = "enforc"
    elif case == "sqlite_url":
        url = "sqlite:///should_not_be_used.db"
    elif case == "db_at_014":
        support.alembic_cmd(live_pg.url, "downgrade", "014_publication_scope_claim_v31")
    elif case == "unmigrated":
        support.alembic_cmd(live_pg.url, "downgrade", "base")
    server = hs.AppServer(database_url=url, faiss_root=tmp_path / "faiss", llm_url=stub.url,
                          log_path=tmp_path / "app.log", mode=mode)
    try:
        with pytest.raises(RuntimeError) as exc:
            server.start(timeout=120)
        assert "exited during startup" in str(exc.value)
        assert expected in server.log_text() + str(exc.value), (case, server.log_tail(15))
        with pytest.raises(httpx.HTTPError):
            httpx.get(server.base + "/health", timeout=3)         # and nothing is listening
    finally:
        server.stop()
        stub.stop()


# ------------------------------------------------------------------------- crash and restart


def test_hard_kill_during_a_stream_then_restart_serves_correctly_with_state_intact(app):
    token = app.login()
    before = pg_state(app.pg.sessions, ALPHA)
    app.stub.server.stream_delay = 0.3

    def stream():
        try:
            with httpx.Client(base_url=app.server.base, timeout=60) as c, \
                    c.stream("POST", "/api/query/stream", json={"query": QUERY}, headers=hs.bearer(token)) as r:
                for _ in r.iter_lines():
                    pass
        except httpx.HTTPError:
            pass

    t = threading.Thread(target=stream)
    t.start()
    time.sleep(1.5)
    app.server.kill()                          # no shutdown hooks run
    t.join(30)
    app.stub.server.stream_delay = 0.0
    assert pg_state(app.pg.sessions, ALPHA) == before, "a killed reader must not change durable publication state"
    restarted = hs.AppServer(database_url=app.pg.url, faiss_root=app.tmp / "faiss", llm_url=app.stub.url,
                             log_path=app.tmp / "app2.log")
    try:
        restarted.start()
        with restarted.client() as c:
            tok = hs.login(c, "alpha_analyst", app.pw).json()["token"]
            r = c.post("/api/query", json={"query": QUERY}, headers=hs.bearer(tok))
        assert r.status_code == 200 and "0.21" in r.text and "Beta" not in r.text
    finally:
        restarted.stop()


# ------------------------------------------------------------------------- dependency outages


def test_postgres_outage_denies_cleanly_and_the_app_recovers_without_a_restart(app, svc):
    token = app.login()
    assert _query(app.server, token).status_code == 200
    svc("-KillPostgres")
    try:
        assert _wait_port(55432, up=False, timeout=60), "postgres did not stop"
        started = time.perf_counter()
        try:
            r = _query(app.server, token, timeout=240)
        finally:
            outage_response_s = time.perf_counter() - started
        print(f"\nLIVE31_MEASUREMENT postgres_down_query_response_s={outage_response_s:.1f}")
        assert outage_response_s < 30, f"a request with the database down took {outage_response_s:.0f}s (unbounded)"
        assert r.status_code >= 400, "served an answer with the database down"
        assert "0.21" not in r.text and "SYNTHETIC" not in r.text and "Traceback" not in r.text
        with app.server.client() as c:
            assert hs.login(c, "alpha_analyst", app.pw).status_code >= 400
            assert c.get("/health").status_code == 200, "liveness must not depend on the database"
    finally:
        svc()                                  # start whatever is down again
    assert _wait_port(55432, up=True, timeout=120), "postgres did not come back"
    deadline, last = time.time() + 60, None
    while time.time() < deadline:
        try:
            last = _query(app.server, token)
            if last.status_code == 200:
                break
        except httpx.HTTPError as exc:
            last = exc
        time.sleep(2)
    assert getattr(last, "status_code", None) == 200 and "0.21" in last.text, f"no recovery: {last}"


def test_neo4j_outage_never_serves_stale_or_foreign_data_and_publication_recovers(app, svc):
    token = app.login()
    svc("-KillNeo4j")
    try:
        assert _wait_port(57687, up=False, timeout=60), "neo4j did not stop"
        r = _query(app.server, token)
        assert "Traceback" not in r.text and "Beta" not in r.text
        if r.status_code == 200:               # the v2 vector path may not need the graph; if it answers it must be right
            assert "0.21" in r.text
        # a publication attempted while the graph is down fails BEFORE it can suspend serving
        app.stack.submit(ALPHA, "B")
        with pytest.raises(Exception):
            app.stack.worker().run_once()
        mid = pg_state(app.pg.sessions, ALPHA)
        assert mid["authority"]["status"] == "ACTIVE" and serving_allowed(app.stack, ALPHA), \
            "an outage before any graph write must not take serving down"
        assert mid["claim"]["status"] == "HELD"
    finally:
        svc()
    assert _wait_port(57687, up=True, timeout=180), "neo4j did not come back"
    time.sleep(2.5)                            # the dead worker's lease expires
    deadline, result = time.time() + 90, None
    while time.time() < deadline:
        try:
            result = app.stack.worker().run_once()
            if result["status"] == "published":
                break
        except Exception:                      # driver reconnecting
            pass
        time.sleep(3)
    assert result and result["status"] == "published", result
    assert pg_state(app.pg.sessions, ALPHA)["authority"]["status"] == "ACTIVE"
    r = _query(app.server, token)
    assert r.status_code == 200 and "0.19" in r.text


# ------------------------------------------------------------------------- backup and restore


def test_backup_and_restore_into_a_disposable_database_still_serves(app):
    pg_bin = os.environ.get("AMC_PG_BIN")
    if not pg_bin or not (Path(pg_bin) / "pg_dump.exe").is_file():
        pytest.skip("LIVE31_BLOCKED: AMC_PG_BIN (pg_dump/psql) is not set")
    src = make_url(app.pg.url)
    env = {**os.environ, "PGPASSWORD": src.password}
    dump = app.tmp / "backup.sql"
    r = subprocess.run([str(Path(pg_bin) / "pg_dump.exe"), "-h", "127.0.0.1", "-p", str(src.port), "-U", src.username,
                        "-d", src.database, "--no-owner", "-f", str(dump)], env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-300:]
    name = "amc_restore_" + uuid.uuid4().hex[:8]
    admin = create_engine(app.pg.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        r = subprocess.run([str(Path(pg_bin) / "psql.exe"), "-h", "127.0.0.1", "-p", str(src.port), "-U", src.username,
                            "-d", name, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(dump)], env=env,
                           capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr[-300:]
        restored_url = src.set(database=name).render_as_string(hide_password=False)
        engine = create_engine(restored_url)
        from app.core.db_runtime31 import verify_migrated_postgresql
        verify_migrated_postgresql(engine)
        sessions = sessionmaker(bind=engine)
        original, restored = pg_state(app.pg.sessions, ALPHA), pg_state(sessions, ALPHA)
        assert restored == original, "restored publication state differs from the original"
        tables_a, rows_a = _counts(app.pg.engine)
        tables_b, rows_b = _counts(engine)
        assert (tables_a, rows_a) == (tables_b, rows_b)
        restored_stack = support.make_stack(sessions, app.driver, app.tmp / "faiss")
        assert serving_allowed(restored_stack, ALPHA), "the restored database + existing index must serve"
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# ------------------------------------------------------------------------- measurements (no invented thresholds)


def _pct(values, p):
    values = sorted(values)
    k = min(len(values) - 1, max(0, int(round(p / 100 * (len(values) - 1)))))
    return values[k]


def test_measure_latency_throughput_and_memory(app):
    token = app.login()
    t0 = time.perf_counter()
    cold = _query(app.server, token, timeout=180)
    cold_s = time.perf_counter() - t0
    assert cold.status_code == 200
    for _ in range(3):
        assert _query(app.server, token).status_code == 200

    seq = []
    for _ in range(40):
        t = time.perf_counter()
        r = _query(app.server, token)
        seq.append(time.perf_counter() - t)
        assert r.status_code == 200

    conc, errs = [], []

    def worker():
        with httpx.Client(base_url=app.server.base, timeout=120) as c:
            for _ in range(6):
                t = time.perf_counter()
                r = c.post("/api/query", json={"query": QUERY}, headers=hs.bearer(token))
                conc.append((time.perf_counter() - t, r.status_code))
                if r.status_code != 200:
                    errs.append(r.status_code)

    wall = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join(240) for t in threads]
    wall = time.perf_counter() - wall
    ok = [s for s, code in conc if code == 200]
    rss = None
    try:
        import psutil
        rss = round(psutil.Process(app.server.proc.pid).memory_info().rss / 1e6, 1)
    except Exception:                          # noqa: BLE001
        pass
    result = {
        "measured_on": "single Windows dev machine, Python 3.11, local PostgreSQL/Neo4j, stubbed LLM and hash embedder",
        "note": "Numbers describe THIS run only. LLM latency is a stub, so end-to-end latency with a real provider will differ.",
        "cold_first_query_s": round(cold_s, 2),
        "sequential": {"n": len(seq), "p50_s": round(statistics.median(seq), 3), "p95_s": round(_pct(seq, 95), 3),
                       "p99_s": round(_pct(seq, 99), 3), "max_s": round(max(seq), 3)},
        "concurrent": {"clients": 6, "requests": len(conc), "ok": len(ok), "errors": errs,
                       "wall_s": round(wall, 2), "throughput_rps": round(len(ok) / wall, 2),
                       "p50_s": round(statistics.median(ok), 3) if ok else None,
                       "p95_s": round(_pct(ok, 95), 3) if ok else None},
        "server_rss_mb": rss,
    }
    out = os.environ.get("AMC_LIVE_EVIDENCE_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "latency_live31.json").write_text(json.dumps(result, indent=2))
    print("\nLIVE31_MEASUREMENT " + json.dumps(result))
    assert len(ok) == len(conc), f"requests failed under concurrency: {errs}"
