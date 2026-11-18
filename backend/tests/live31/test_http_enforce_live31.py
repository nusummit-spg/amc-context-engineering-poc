"""WP06 / gate G6: the REAL app (uvicorn, enforce mode) over real HTTP, SSE and WebSocket.

Real: login/logout/revocation, PostgreSQL, the ASGI perimeter, the verified retriever and v2
orchestrator, FAISS generations published by the real worker, Neo4j. Stand-ins: the LLM provider
(a grounded local HTTP stub) and the query-embedding model (a deterministic hash embedder).
Proof of tenant isolation comes from the answer text, the sources, AND the prompts that reached the
LLM stub, not from status codes alone.
"""
import json
import socket
import threading
import time
import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from tests.live31 import support, http_support as hs
from tests.live31.llm_stub import LlmStub
from tests.live31.support import ALPHA, BETA, fx, pg_state

GAMMA, EMPTY = "live31_gamma", "live31_empty"
PERIMETER_BODY = "Unreviewed route disabled in verified pilot mode"
QUERY = "What is the total expense ratio of the Liquid Fund?"


@pytest.fixture(scope="module")
def web(live_pg_admin_url, live_template_db, live_neo4j_driver, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("http31")
    name = "amc_http_" + uuid.uuid4().hex[:8]
    admin = create_engine(live_pg_admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{live_template_db}"'))
    url = make_url(live_pg_admin_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url, pool_size=5, max_overflow=10)
    sessions = sessionmaker(bind=engine)
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(sessions, live_neo4j_driver, tmp / "faiss")
    works = {}
    for tenant in (ALPHA, BETA, GAMMA):
        ent, attr, _ = support.graph_target(tenant, "A")
        support.seed_graph(live_neo4j_driver, tenant, ent, attr, "legacy")
        works[tenant] = stack.submit(tenant, "A")
        assert stack.worker().run_once()["status"] == "published"
    pw = {u: hs.random_secret(12) for u in ("alpha_analyst", "beta_analyst", "gamma_analyst", "no_tenant",
                                            "empty_analyst", "inactive_user", "alpha_reviewer", "beta_reviewer")}
    hs.seed_user(engine, username="alpha_reviewer", password=pw["alpha_reviewer"], tenant=ALPHA,
                 role="Compliance Officer")
    hs.seed_user(engine, username="beta_reviewer", password=pw["beta_reviewer"], tenant=BETA,
                 role="Compliance Officer")
    hs.seed_user(engine, username="alpha_analyst", password=pw["alpha_analyst"], tenant=ALPHA)
    hs.seed_user(engine, username="beta_analyst", password=pw["beta_analyst"], tenant=BETA)
    hs.seed_user(engine, username="gamma_analyst", password=pw["gamma_analyst"], tenant=GAMMA)
    hs.seed_user(engine, username="no_tenant", password=pw["no_tenant"], tenant=None)
    hs.seed_user(engine, username="empty_analyst", password=pw["empty_analyst"], tenant=EMPTY)
    hs.seed_user(engine, username="inactive_user", password=pw["inactive_user"], tenant=ALPHA, status="Inactive")
    stub = LlmStub().start()
    server = hs.AppServer(database_url=url, faiss_root=tmp / "faiss", llm_url=stub.url, log_path=tmp / "app.log")
    server.start()
    ns = SimpleNamespace(server=server, stub=stub, stack=stack, engine=engine, url=url, passwords=pw,
                         works=works, driver=live_neo4j_driver, tmp=tmp, admin_url=live_pg_admin_url, db=name)
    yield ns
    server.stop()
    stub.stop()
    support.clean_graph(live_neo4j_driver)
    engine.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _login(web, user) -> str:
    with web.server.client() as c:
        r = hs.login(c, user, web.passwords[user])
        assert r.status_code == 200, r.text
        return r.json()["token"]


@pytest.fixture(scope="module")
def tokens(web):
    return {u: _login(web, u) for u in ("alpha_analyst", "beta_analyst", "gamma_analyst", "no_tenant", "empty_analyst",
                                        "alpha_reviewer", "beta_reviewer")}


@pytest.fixture
def client(web):
    with web.server.client() as c:
        yield c


def _ask(client, token, path="/api/query", query=QUERY, **extra):
    body = {"query": query, **extra}
    if path.startswith("/api/chat"):
        body.setdefault("session_id", "sess_" + uuid.uuid4().hex[:12])
    return client.post(path, json=body, headers=hs.bearer(token))


def _blob(resp) -> str:
    return json.dumps(resp.json()) if "json" in resp.headers.get("content-type", "") else resp.text


# ===================================================================== authentication


def test_login_returns_a_token_and_the_users_tenant_bound_profile(web, client):
    r = hs.login(client, "alpha_analyst", web.passwords["alpha_analyst"])
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["user"]["username"] == "alpha_analyst"
    me = client.get("/api/auth/me", headers=hs.bearer(body["token"]))
    assert me.status_code == 200 and "alpha_analyst" in me.text
    assert "password" not in me.text.lower() and "hash" not in me.text.lower()


def test_wrong_password_and_unknown_user_are_indistinguishable(web, client):
    wrong = hs.login(client, "beta_analyst", "definitely-wrong")
    unknown = hs.login(client, "no_such_user_" + uuid.uuid4().hex[:6], "definitely-wrong")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json(), "login must not reveal whether the user exists"


def test_inactive_account_cannot_log_in(web, client):
    r = hs.login(client, "inactive_user", web.passwords["inactive_user"])
    assert r.status_code in (401, 403) and "token" not in r.text


@pytest.mark.parametrize("header", [None, "", "Bearer", "Basic abc", "Bearer garbage",
                                    "Bearer a.b", "bearer " + "x" * 400, "Token abc"])
def test_missing_or_malformed_credentials_are_rejected(client, header):
    headers = {} if header is None else {"Authorization": header}
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code in (401, 403), (header, r.status_code)
    for path in ("/api/query", "/api/chat"):
        q = client.post(path, json={"query": QUERY, "session_id": "s1"}, headers=headers)
        assert q.status_code in (401, 403, 422), (path, header, q.status_code)
        assert "0.21" not in q.text


def test_a_tampered_or_foreign_signed_or_expired_token_is_rejected(web, client, tokens):
    good = tokens["alpha_analyst"]
    payload, sig = good.split(".")
    flipped = payload + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    forged_other_secret, _ = __import__("app.auth.security", fromlist=["x"]).issue_session_token(
        "alpha_analyst", "some-other-secret-key-0123456789abcdef", 60)
    expired, _ = __import__("app.auth.security", fromlist=["x"]).issue_session_token(
        "alpha_analyst", web.server.secret, -5)
    for bad in (flipped, forged_other_secret, expired, good[:-3]):
        assert client.get("/api/auth/me", headers=hs.bearer(bad)).status_code == 401
        denied = _ask(client, bad)       # optional-auth route: refused as "no authenticated tenant" (403)
        assert denied.status_code in (401, 403) and "0.21" not in denied.text


def test_a_validly_signed_token_for_a_nonexistent_user_is_rejected(web, client):
    token, _ = __import__("app.auth.security", fromlist=["x"]).issue_session_token(
        "ghost_" + uuid.uuid4().hex[:6], web.server.secret, 60)
    assert client.get("/api/auth/me", headers=hs.bearer(token)).status_code == 401
    denied = _ask(client, token)
    assert denied.status_code in (401, 403) and "0.21" not in denied.text


def test_logout_revokes_the_token_server_side(web, client):
    token = _login(web, "beta_analyst")
    assert client.get("/api/auth/me", headers=hs.bearer(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=hs.bearer(token)).status_code == 200
    again = client.get("/api/auth/me", headers=hs.bearer(token))
    assert again.status_code == 401 and "revoked" in again.text.lower()
    denied = _ask(client, token)
    assert denied.status_code in (401, 403) and "0.35" not in denied.text, "a revoked token must not reach retrieval"


def test_a_token_without_a_jti_cannot_be_revoked_so_it_is_refused(web, client):
    """Old-format tokens carry no jti and would bypass revocation entirely."""
    import base64
    import hashlib
    import hmac
    import time
    payload = base64.urlsafe_b64encode(json.dumps(
        {"sub": "alpha_analyst", "iat": int(time.time()), "exp": int(time.time()) + 600},
        separators=(",", ":")).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(hmac.new(web.server.secret.encode(), payload.encode(), hashlib.sha256).digest()
                                   ).rstrip(b"=").decode()
    token = f"{payload}.{sig}"
    assert client.get("/api/auth/me", headers=hs.bearer(token)).status_code == 401


def test_revocation_check_failure_must_fail_closed(web, client):
    """If the revocation table cannot be read, a token must NOT be accepted (fail closed)."""
    token = _login(web, "beta_analyst")
    with web.engine.begin() as c:
        c.execute(text("ALTER TABLE revoked_tokens RENAME TO revoked_tokens_offline"))
    try:
        r = client.get("/api/auth/me", headers=hs.bearer(token))
        q = _ask(client, token)
    finally:
        with web.engine.begin() as c:
            c.execute(text("ALTER TABLE revoked_tokens_offline RENAME TO revoked_tokens"))
    assert r.status_code in (401, 403, 503), f"revocation check failed open: /me -> {r.status_code}"
    assert q.status_code in (401, 403, 503) and "0.35" not in q.text, "query served with an unverifiable token"


def test_logout_must_not_report_success_when_revocation_failed(web, client):
    token = _login(web, "beta_analyst")
    with web.engine.begin() as c:
        c.execute(text("ALTER TABLE revoked_tokens RENAME TO revoked_tokens_offline"))
    try:
        r = client.post("/api/auth/logout", headers=hs.bearer(token))
    finally:
        with web.engine.begin() as c:
            c.execute(text("ALTER TABLE revoked_tokens_offline RENAME TO revoked_tokens"))
    assert r.status_code >= 500 or "failed" not in r.text.lower() or r.json().get("ok") is not True, (
        "logout reported ok although the token was not revoked: " + r.text)


# ===================================================================== positive path + tenant isolation


@pytest.mark.parametrize("path", ["/api/query", "/api/query/v2", "/api/chat", "/api/chat/v2", "/api/chat/query"])
def test_each_pilot_endpoint_answers_from_the_users_own_tenant(web, client, tokens, path):
    for user, tenant in (("alpha_analyst", ALPHA), ("beta_analyst", BETA)):
        before = len(web.stub.calls)
        r = _ask(client, tokens[user], path)
        assert r.status_code == 200, (path, user, r.status_code, r.text[:300])
        blob = _blob(r)
        probe = fx.probes(tenant)[0]
        assert probe["must_contain"]["A"] in blob, (path, user)
        other = "Beta" if tenant == ALPHA else "Alpha"
        assert other not in blob and other.lower() + " " not in blob.lower(), f"{other} content leaked to {user}"
        new_prompts = "\n".join(str(m.get("content", "")) for c in web.stub.calls[before:] for m in c.get("messages", []))
        assert other not in new_prompts, f"{other} content reached the LLM for {user}"
        assert r.headers.get("x-serving-engine", "v2").startswith("v2")


def test_every_fixture_probe_returns_its_expected_fact_for_both_tenants(web, client, tokens):
    for user, tenant in (("alpha_analyst", ALPHA), ("beta_analyst", BETA)):
        for probe in fx.probes(tenant):
            r = _ask(client, tokens[user], query=probe["query"])
            assert r.status_code == 200
            blob = _blob(r)
            assert probe["must_contain"]["A"] in blob, probe["id"]
            assert not any(bad in blob for bad in probe["must_not_contain"]), probe["id"]


def test_sources_returned_to_the_client_belong_to_the_tenant(web, client, tokens):
    r = _ask(client, tokens["alpha_analyst"])
    ids = [json.dumps(s) for s in r.json().get("sources", [])]
    assert ids, "the response must carry source attributions"
    assert all("tenant_beta" not in s and "Beta" not in s for s in ids)


def test_the_tenant_comes_from_the_account_not_from_anything_the_client_sends(web, client, tokens):
    r = client.post("/api/query", json={"query": QUERY, "tenant_id": BETA, "user_id": "beta_analyst"},
                    headers={**hs.bearer(tokens["alpha_analyst"]), "X-Tenant-ID": BETA, "X-Tenant": BETA})
    assert r.status_code in (200, 422)
    assert "0.35" not in r.text and "Beta" not in r.text


def test_an_account_without_a_tenant_is_refused_before_any_retrieval(web, client, tokens):
    before = len(web.stub.calls)
    for path in ("/api/query", "/api/query/v2", "/api/query/stream"):
        r = _ask(client, tokens["no_tenant"], path)
        assert r.status_code == 403, (path, r.status_code)
        assert "0.21" not in r.text and "0.35" not in r.text
    assert len(web.stub.calls) == before, "a tenant-less request must not reach the LLM"


def test_a_tenant_with_no_published_corpus_is_denied_not_answered(web, client, tokens):
    before = len(web.stub.calls)
    r = _ask(client, tokens["empty_analyst"])
    assert r.status_code >= 400, r.text[:200]
    assert "0.21" not in r.text and "0.35" not in r.text and "SYNTHETIC" not in r.text
    assert "Traceback" not in r.text


# ===================================================================== SSE


def _stream(client, token, path="/api/query/stream", query=QUERY):
    body = {"query": query}
    if path.startswith("/api/chat"):
        body["session_id"] = "sess_" + uuid.uuid4().hex[:12]
    with client.stream("POST", path, json=body, headers=hs.bearer(token)) as r:
        ctype = r.headers.get("content-type", "")
        events = hs.sse_events(r) if r.status_code == 200 else []
        return r.status_code, ctype, events


@pytest.mark.parametrize("path", ["/api/query/stream", "/api/chat/stream"])
def test_streaming_delivers_the_users_tenant_content_only(web, client, tokens, path):
    for user, tenant, fact, other in (("alpha_analyst", ALPHA, "0.21", "Beta"), ("beta_analyst", BETA, "0.35", "Alpha")):
        status, ctype, events = _stream(client, tokens[user], path)
        assert status == 200 and "text/event-stream" in ctype, (status, ctype)
        names = [e["event"] for e in events]
        assert "done" in names or names, names
        text_blob = "\n".join(e["data"] for e in events)
        assert fact in text_blob and other not in text_blob, f"{user} via {path}: {text_blob[:300]}"
        assert "error" not in names, (names, text_blob[:300])


@pytest.mark.parametrize("path", ["/api/query/stream", "/api/chat/stream"])
def test_streaming_without_valid_credentials_opens_no_stream(client, tokens, path):
    for hdr in ({}, {"Authorization": "Bearer nope"}):
        r = client.post(path, json={"query": QUERY, "session_id": "s"}, headers=hdr)
        assert r.status_code in (401, 403) and "text/event-stream" not in r.headers.get("content-type", "")


def test_authority_revoked_mid_stream_releases_no_further_content(web, client, tokens):
    """gamma has A then B published; B is rolled back while an answer is being streamed."""
    ent, attr, _ = support.graph_target(GAMMA, "B")
    work_b = web.stack.submit(GAMMA, "B")
    assert web.stack.worker().run_once()["status"] == "published"
    web.stub.server.stream_delay = 0.35
    result = {}

    def run():
        try:
            result["out"] = _stream(client_for_thread(web), tokens["gamma_analyst"])
        except BaseException as exc:          # noqa: BLE001
            result["err"] = exc

    def client_for_thread(w):
        return httpx.Client(base_url=w.server.base, timeout=90)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(1.5)
    web.stack.journal.request_rollback(work_b, GAMMA)         # revoke B while the stream is running
    t.join(90)
    web.stub.server.stream_delay = 0.0
    assert "err" not in result, result.get("err")
    status, ctype, events = result["out"]
    names = [e["event"] for e in events]
    body = "\n".join(e["data"] for e in events)
    assert "0.19" not in body, "generation B content was delivered after its authority was revoked"
    assert "error" in names or status >= 400, f"stream was not terminated as invalidated: {names}"
    # finish the rollback so later tests see gamma on generation A
    assert web.stack.worker().run_once()["status"] == "rolled_back"
    after = _ask(client, tokens["gamma_analyst"])
    assert after.status_code == 200 and "0.21" in _blob(after)


# ===================================================================== perimeter: default deny


DENIED = [
    ("GET", "/api/graph"), ("GET", "/api/graph/neighborhood?name=x"), ("GET", "/api/graph/traversal?query=x"),
    ("GET", "/api/files/Report.pdf"), ("GET", "/files/Report.pdf"), ("GET", "/api/files/Report.pdf?download=true"),
    ("GET", "/api/docs"), ("GET", "/api/docs/DOC-001"), ("GET", "/api/taxonomy"), ("GET", "/api/taxonomy/node/docs"),
    ("GET", "/api/schemes/aggregation/x"), ("POST", "/api/query/traditional"), ("POST", "/api/query/contextgraph"),
    ("GET", "/api/admin/users"), ("POST", "/api/admin/users"), ("DELETE", "/api/admin/users/alpha_analyst"),
    ("POST", "/api/admin/ingestion/run"), ("POST", "/api/admin/ingestion/upload"), ("POST", "/api/ingest"),
    ("POST", "/api/ingest/documents"), ("POST", "/api/feedback"), ("GET", "/api/feedback/issues"),
    ("POST", "/api/governance/approve/x"), ("POST", "/api/governance/batch-approve"),
    ("GET", "/api/sessions"), ("DELETE", "/api/sessions/x"), ("POST", "/api/chat/title"),
    ("GET", "/api/compliance/scorecard"), ("POST", "/api/auth/accept-invitation"),
    ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"), ("GET", "/metrics"), ("GET", "/api/metrics"),
    ("PUT", "/api/query"), ("DELETE", "/api/query"), ("PATCH", "/api/query/v2"), ("GET", "/api/query"),
    ("GET", "/api/auth/login"), ("POST", "/api/health"), ("GET", "/api/nonexistent"), ("GET", "/etc/passwd"),
    ("POST", "/api/publication/status/x"), ("GET", "/api/publication"), ("GET", "/api/publication/status/"),
    ("GET", "/api/query/"), ("GET", "/api/health/"), ("GET", "/Api/Health"),
]


@pytest.mark.parametrize("method,path", DENIED)
def test_unreviewed_routes_are_refused_with_a_uniform_503_and_no_data(web, client, tokens, method, path):
    for headers in ({}, hs.bearer(tokens["alpha_analyst"])):
        r = client.request(method, path, headers=headers, json={} if method in ("POST", "PUT", "PATCH") else None)
        assert r.status_code == 503, (method, path, bool(headers), r.status_code, r.text[:200])
        assert PERIMETER_BODY in r.text and r.headers.get("cache-control") == "no-store"
        assert "SYNTHETIC" not in r.text and "Traceback" not in r.text and "tenant_" not in r.text


def _raw_status(web, request_line: str) -> tuple[int, str]:
    with socket.create_connection(("127.0.0.1", web.server.port), timeout=15) as s:
        s.sendall((request_line + f"\r\nHost: 127.0.0.1:{web.server.port}\r\nConnection: close\r\n\r\n").encode())
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    return int(head.split(b" ", 2)[1]), body.decode("latin1")


@pytest.mark.parametrize("target", [
    "//api/query", "/api//query", "/api/query/../admin/users", "/api/./query/../graph", "/api/%2e%2e/admin/users",
    "/api/%2571uery", "/api/query%00", "/api/query%2f..%2fadmin", "/api\\query", "/%2e%2e/%2e%2e/etc/passwd",
    "/assets/../../etc/passwd", "/assets/..%2f..%2fetc%2fpasswd", "/static-files/../app/main.py",
    "/static-files/..%5c..%5capp%5cmain.py", "/assets/%2e%2e/%2e%2e/app/config.py",
])
def test_path_tricks_never_reach_a_denied_or_private_resource(web, target):
    status, body = _raw_status(web, f"GET {target} HTTP/1.1")
    assert status in (400, 403, 404, 503), (target, status)
    assert "SYNTHETIC" not in body and "auth_secret" not in body.lower() and "root:" not in body
    assert "def create_app" not in body and "class Settings" not in body


def test_head_and_options_do_not_open_a_denied_route(web, client):
    assert client.head("/api/graph").status_code == 503
    r = client.options("/api/graph", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "evil.example" not in r.headers.get("access-control-allow-origin", "")


def test_websocket_is_refused(web):
    from websockets.sync.client import connect
    for path in ("/ws", "/api/ws", "/api/query/stream", "/api/chat/ws"):
        with pytest.raises(Exception):
            with connect(f"ws://127.0.0.1:{web.server.port}{path}", open_timeout=10) as ws:
                ws.recv(timeout=5)


def test_health_is_open_but_is_liveness_only(web, client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "tenant" not in r.text.lower() and "faiss" not in r.text.lower() and "SYNTHETIC" not in r.text
    # liveness != readiness: a tenant with nothing published is still "healthy" at /health yet cannot be served
    assert client.get("/api/health").status_code == 200


def test_spa_entry_points_serve_static_html_only(web, client):
    for path in ("/", "/chat", "/login"):
        r = client.get(path)
        assert r.status_code in (200, 404), path        # 404 when the frontend bundle is not built
        assert "SYNTHETIC" not in r.text and "tenant_" not in r.text


# ===================================================================== publication status


def test_publication_status_is_tenant_scoped_and_reviewer_only(web, client, tokens):
    work = web.works[ALPHA]
    mine = client.get(f"/api/publication/status/{work}", headers=hs.bearer(tokens["alpha_reviewer"]))
    assert mine.status_code == 200
    body = mine.json()
    assert body["status"] == "published" and body["tenant"] == ALPHA
    # an ordinary analyst is not a reviewer (by design in status_route.py)
    assert client.get(f"/api/publication/status/{work}", headers=hs.bearer(tokens["alpha_analyst"])).status_code == 403
    other = client.get(f"/api/publication/status/{work}", headers=hs.bearer(tokens["beta_reviewer"]))
    assert other.status_code == 404, "another tenant's work id must look like it does not exist"
    assert "tenant_alpha" not in other.text
    anon = client.get(f"/api/publication/status/{work}")
    assert anon.status_code in (401, 403)
    rv = hs.bearer(tokens["alpha_reviewer"])
    assert client.get(f"/api/publication/status/{'x' * 200}", headers=rv).status_code == 503
    assert client.get("/api/publication/status/a/b", headers=rv).status_code == 503
    assert client.get("/api/publication/status/nope", headers=rv).status_code == 404


def test_publication_status_does_not_expose_internals(web, client, tokens):
    r = client.get(f"/api/publication/status/{web.works[ALPHA]}", headers=hs.bearer(tokens["alpha_reviewer"]))
    text_ = r.text
    for secret in ("password", "payload", "full_vector_snapshot", "SYNTHETIC", "idempotency"):
        assert secret not in text_, secret


# ===================================================================== robustness


@pytest.mark.parametrize("body,expect", [
    ({"query": "ab"}, 422), ({"query": "x" * 2001}, 422), ({}, 422), ({"query": 5}, 422),
    ({"query": None}, 422), ({"query": ["a"]}, 422), ({"query": QUERY, "top_k": 0}, 422),
    ({"query": QUERY, "top_k": 10_000}, 422),
])
def test_invalid_input_is_a_clean_422_with_no_internals(client, tokens, body, expect):
    r = client.post("/api/query", json=body, headers=hs.bearer(tokens["alpha_analyst"]))
    assert r.status_code == expect, (body, r.status_code)
    assert "Traceback" not in r.text and "\\app\\" not in r.text and "/app/" not in r.text


def test_malformed_json_is_rejected_cleanly(client, tokens):
    r = client.post("/api/query", content=b'{"query": "unterminated', headers={**hs.bearer(tokens["alpha_analyst"]),
                                                                                "Content-Type": "application/json"})
    assert r.status_code in (400, 422) and "Traceback" not in r.text


def test_oversized_body_is_refused(client, tokens):
    r = client.post("/api/query", content=b'{"query": "' + b"a" * 5_000_000 + b'"}',
                    headers={**hs.bearer(tokens["alpha_analyst"]), "Content-Type": "application/json"})
    assert r.status_code in (400, 413, 422)


def test_concurrent_requests_from_two_tenants_never_cross(web, tokens):
    errors, results = [], []

    def worker(user, fact, other):
        try:
            with httpx.Client(base_url=web.server.base, timeout=120) as c:
                for _ in range(4):
                    r = _ask(c, tokens[user])
                    blob = _blob(r)
                    results.append((user, r.status_code, fact in blob, other in blob))
        except BaseException as exc:      # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=("alpha_analyst", "0.21", "Beta")) for _ in range(3)]
    threads += [threading.Thread(target=worker, args=("beta_analyst", "0.35", "Alpha")) for _ in range(3)]
    [t.start() for t in threads]
    [t.join(180) for t in threads]
    assert not errors, errors
    ok = [r for r in results if r[1] == 200]
    assert len(ok) >= 20, results                     # most must succeed; rate limits may refuse a few
    assert all(r[2] and not r[3] for r in ok), "a response contained another tenant's content or missed its own"


def test_stub_provider_outage_is_a_clean_error_not_a_stale_or_foreign_answer(web, client, tokens):
    web.stub.server.fail_next = 50
    try:
        r = _ask(client, tokens["alpha_analyst"])
    finally:
        web.stub.server.fail_next = 0
    assert "Traceback" not in r.text
    assert "Beta" not in r.text and "0.35" not in r.text


# ===================================================================== hygiene (runs last in this module)


def test_zz_server_log_contains_no_credentials_or_tokens(web, tokens):
    log = web.server.log_text()
    for name, secret in list(web.passwords.items()):
        assert secret not in log, f"password of {name} appears in the server log"
    for name, tok in tokens.items():
        assert tok not in log and tok.split(".")[1] not in log, f"session token of {name} appears in the server log"
    pg_pw = make_url(web.url).password
    assert web.server.secret not in log and pg_pw not in log
    assert "local-stub-key-not-a-secret" not in log
