"""The live suite must refuse shared databases. These tests need no services."""
import pytest

from tests.live31 import guard

OK = guard.OVERRIDE_PHRASE


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@127.0.0.1:55432/postgres",
    "postgresql+psycopg://u:p@localhost:5432/postgres",
    "postgresql+psycopg://u:p@[::1]:5432/postgres",
])
def test_loopback_postgres_is_accepted(url):
    guard.assert_local_targets(pg_url=url, environ={})


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@10.0.0.5:5432/postgres",
    "postgresql+psycopg://u:p@192.168.1.20/postgres",
    "postgresql+psycopg://u:p@db.prod.example.com/postgres",
    "postgresql+psycopg://u:p@8.8.8.8/postgres",
    "postgresql+psycopg://u:p@/postgres",             # no host: a unix socket or a library default, not provably local
])
def test_non_loopback_or_unprovable_postgres_is_refused(url):
    with pytest.raises(guard.LiveTargetRefused, match="non-local target"):
        guard.assert_local_targets(pg_url=url, environ={})


@pytest.mark.parametrize("uri,ok", [
    ("bolt://127.0.0.1:57687", True), ("neo4j://localhost:7687", True), ("bolt://[::1]:7687", True),
    ("bolt://10.1.2.3:7687", False), ("neo4j+s://graph.prod.example.com", False), ("bolt://", False),
])
def test_neo4j_uri_host_is_checked(uri, ok):
    if ok:
        guard.assert_local_targets(neo4j_uri=uri, environ={})
    else:
        with pytest.raises(guard.LiveTargetRefused):
            guard.assert_local_targets(neo4j_uri=uri, environ={})


def test_either_target_being_remote_refuses_the_pair():
    with pytest.raises(guard.LiveTargetRefused, match="Neo4j"):
        guard.assert_local_targets(pg_url="postgresql+psycopg://u:p@127.0.0.1/postgres",
                                   neo4j_uri="bolt://10.0.0.9:7687", environ={})


def test_override_needs_the_exact_phrase():
    remote = "postgresql+psycopg://u:p@10.0.0.5/postgres"
    for wrong in ("1", "true", "yes", OK.lower(), OK + " ", ""):
        with pytest.raises(guard.LiveTargetRefused):
            guard.assert_local_targets(pg_url=remote, environ={guard.OVERRIDE_ENV: wrong})
    guard.assert_local_targets(pg_url=remote, environ={guard.OVERRIDE_ENV: OK})


def test_a_name_that_resolves_off_loopback_is_refused(monkeypatch):
    monkeypatch.setattr(guard.socket, "getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("127.0.0.1", 0)), (2, 1, 6, "", ("10.9.9.9", 0))])
    with pytest.raises(guard.LiveTargetRefused):
        guard.assert_local_targets(pg_url="postgresql+psycopg://u:p@looks-local.example/postgres", environ={})


def test_the_refusal_names_the_remedy_and_never_echoes_credentials():
    with pytest.raises(guard.LiveTargetRefused) as exc:
        guard.assert_local_targets(pg_url="postgresql+psycopg://admin:Sup3rSecret@10.0.0.5/postgres", environ={})
    text = str(exc.value)
    assert "local_services31.ps1" in text and "Sup3rSecret" not in text and "admin" not in text


def test_conftest_applies_the_guard_to_both_targets():
    import inspect
    from tests.live31 import conftest
    src = inspect.getsource(conftest)
    assert src.count("guard.assert_local_targets") >= 2
    assert "pg_url=raw" in src and "neo4j_uri=uri" in src
