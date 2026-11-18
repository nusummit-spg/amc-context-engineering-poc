"""Refuse to run the live suite against anything that is not a local, disposable service.

These tests CREATE and DROP PostgreSQL databases and DELETE Neo4j nodes (every node whose tenant_id starts with
"tenant_" or "live31_"). Pointing them at a shared server would destroy real data, so by default the PostgreSQL
and Neo4j hosts must resolve to loopback addresses. A deliberate override exists for a throwaway remote host and
requires an exact phrase, so it cannot happen by accident or through a copied environment file.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

OVERRIDE_ENV = "AMC_LIVE_ALLOW_NONLOCAL"
OVERRIDE_PHRASE = "I_UNDERSTAND_THIS_DESTROYS_DATABASES_AND_GRAPH_NODES"


class LiveTargetRefused(RuntimeError):
    pass


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False
    host = host.strip("[]")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    try:                                    # a name must resolve ONLY to loopback addresses
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_loopback for a in addrs)


def _host_of_pg(url: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(url).host or ""


def _host_of_neo4j(uri: str) -> str:
    return urlparse(uri).hostname or ""


def assert_local_targets(*, pg_url: str | None = None, neo4j_uri: str | None = None, environ=None) -> None:
    """Raise LiveTargetRefused unless every given target is loopback (or the explicit override is set)."""
    import os
    env = os.environ if environ is None else environ
    if env.get(OVERRIDE_ENV) == OVERRIDE_PHRASE:
        return
    problems = []
    if pg_url is not None and not _is_loopback_host(_host_of_pg(pg_url)):
        problems.append(f"PostgreSQL host {_host_of_pg(pg_url) or '(none)'!r}")
    if neo4j_uri is not None and not _is_loopback_host(_host_of_neo4j(neo4j_uri)):
        problems.append(f"Neo4j host {_host_of_neo4j(neo4j_uri) or '(none)'!r}")
    if problems:
        raise LiveTargetRefused(
            "refusing to run the live suite against a non-local target (" + "; ".join(problems) + "). "
            "It creates and drops databases and deletes graph nodes. Use the local disposable services "
            "(ops/validation/local_services31.ps1). A throwaway remote host needs "
            f"{OVERRIDE_ENV}=<the exact phrase in tests/live31/guard.py>.")
