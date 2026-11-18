"""Offline operator CLI for verified publication (Wave 3.1, WP08).

The pilot has NO HTTP publication endpoint; an operator publishes, replays and rolls back from here.
It builds the PRODUCTION worker (real FAISS generation store, real Neo4j graph port, real serving
probe) against the PostgreSQL named by DATABASE_URL, after proving the database is at the exact
migration revision. It never edits state by hand, never force-releases a claim and never accepts
an approval it cannot attribute to two different people.

    python -m amc_publication.operator_cli submit  --tenant T --entity E --attribute A --value V \\
        --corpus corpus.json --proposal-id P --revision 1 --proposer alice --reviewer bob \\
        --attest-independent-approval
    python -m amc_publication.operator_cli run-once
    python -m amc_publication.operator_cli rollback --tenant T --work-id W
    python -m amc_publication.operator_cli status   --tenant T

Environment: DATABASE_URL (postgresql+psycopg), AMC_VERIFIED_FAISS_ROOT, NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD,
AMC_PUBLICATION_GRAPH_ATTRIBUTES (comma list, explicit allowlist), AMC_PUBLICATION_EMBEDDER
("package.module:factory", default app.vector.client:get_base_vector_store).
Exit codes: 0 success, 2 refused or failed (a JSON object with the reason is printed either way).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

DEFAULT_EMBEDDER = "app.vector.client:get_base_vector_store"
REVIEW_REQUIRED = "operator review required; do not edit database rows by hand"


class CliRefused(Exception):
    pass


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CliRefused(f"{name} is required")
    return value


def _engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = _env("DATABASE_URL")
    if make_url(url).drivername != "postgresql+psycopg":
        raise CliRefused("DATABASE_URL must be postgresql+psycopg://...")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        from app.core.db_runtime31 import verify_migrated_postgresql
        verify_migrated_postgresql(engine)           # exact revision or refuse
    except RuntimeError as exc:
        raise CliRefused(str(exc)) from exc
    return engine


def _embedder():
    spec = os.environ.get("AMC_PUBLICATION_EMBEDDER", DEFAULT_EMBEDDER)
    module, _, factory = spec.partition(":")
    if not module or not factory:
        raise CliRefused("AMC_PUBLICATION_EMBEDDER must look like package.module:factory")
    obj = getattr(importlib.import_module(module), factory)
    return obj() if callable(obj) else obj


def _build(engine):
    from sqlalchemy.orm import sessionmaker
    from neo4j import GraphDatabase
    from .journal import Journal
    from .faiss_artifacts import FaissGenerationStore
    from .faiss_reader27 import VerifiedFaissRetriever
    from .serving28 import ActiveReceiptResolver
    from .graph import Neo4jGraphPort
    from .worker import PublicationWorker
    sessions = sessionmaker(bind=engine)
    root = _env("AMC_VERIFIED_FAISS_ROOT")
    attrs = {a.strip() for a in _env("AMC_PUBLICATION_GRAPH_ATTRIBUTES").split(",") if a.strip()}
    driver = GraphDatabase.driver(_env("NEO4J_URI"), auth=(_env("NEO4J_USER"), _env("NEO4J_PASSWORD")))
    driver.verify_connectivity()
    store = FaissGenerationStore(root, _embedder())
    reader = VerifiedFaissRetriever(sessions, root)
    reader.resolver = ActiveReceiptResolver(sessions, reader.store, serving_loader=reader._load)
    graph = Neo4jGraphPort(driver, label="Entity", allowed_attributes=attrs)
    journal = Journal(sessions)
    worker = PublicationWorker(journal, graph, store, serving_probe=reader.probe_activation)
    return sessions, journal, worker, driver


def cmd_submit(args) -> dict:
    from .integration import ApprovedProposal, queue_verified_approval
    from .types import Conflict
    if not args.attest_independent_approval:
        raise CliRefused("--attest-independent-approval is required: a proposer and a different reviewer "
                         "must have approved this change")
    if not args.proposer or not args.reviewer or args.proposer == args.reviewer:
        raise CliRefused("independent human proposer and reviewer IDs are mandatory and must differ")
    with open(args.corpus, encoding="utf-8") as fh:
        corpus = json.load(fh)
    if not isinstance(corpus, list) or not corpus:
        raise CliRefused("--corpus must be a nonempty JSON list (a COMPLETE corpus snapshot)")
    if any(not isinstance(r, dict) or r.get("tenant_id") != args.tenant for r in corpus):
        raise CliRefused("every corpus row must carry tenant_id == --tenant")
    engine = _engine()
    _sessions, journal, _worker, driver = _build(engine)
    try:
        proposal = ApprovedProposal(proposal_id=args.proposal_id, tenant=args.tenant, revision=args.revision,
                                    proposer_id=args.proposer, reviewer_id=args.reviewer, status="APPROVED",
                                    entity_id=args.entity, attribute=args.attribute, proposed_value=args.value)
        try:
            work_id = queue_verified_approval(journal, proposal, corpus)
        except Conflict as exc:
            raise CliRefused(str(exc)) from exc
    finally:
        driver.close()
    return {"ok": True, "work_id": work_id, "next": "run-once"}


def cmd_run_once(_args) -> dict:
    engine = _engine()
    _sessions, _journal, worker, driver = _build(engine)
    try:
        result = worker.run_once()
    finally:
        driver.close()
    return {"ok": result.get("status") in ("published", "rolled_back", "no_jobs"), **result}


def cmd_rollback(args) -> dict:
    from .types import Conflict
    engine = _engine()
    _sessions, journal, _worker, driver = _build(engine)
    try:
        try:
            journal.request_rollback(args.work_id, args.tenant)
        except Conflict as exc:
            raise CliRefused(str(exc)) from exc
    finally:
        driver.close()
    return {"ok": True, "serving": "suspended until the rollback completes", "next": "run-once"}


def cmd_status(args) -> dict:
    """Read-only. Reports durable state; never changes it."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from .models import GenerationPointer, PublicationWork
    from .active_authority28 import ActiveReceiptAuthority, PublicationScopeClaim31
    engine = _engine()
    sessions = sessionmaker(bind=engine)
    with sessions() as s:
        a = s.get(ActiveReceiptAuthority, (args.tenant, "vector_faiss"))
        p = s.get(GenerationPointer, (args.tenant, "vector_faiss"))
        c = s.get(PublicationScopeClaim31, (args.tenant, "vector_faiss"))
        works = {w.id: {"status": w.status, "attempts": w.attempts, "last_error": w.last_error}
                 for w in s.scalars(select(PublicationWork).where(PublicationWork.tenant == args.tenant))}
    out = {"ok": True, "tenant": args.tenant, "works": works,
           "authority": None if a is None else {"status": a.status, "work": a.work_id, "epoch": a.pointer_epoch,
                                                 "generation": a.generation_id, "suspended_by": a.suspended_by},
           "pointer": None if p is None else {"generation": p.generation_id, "epoch": p.epoch},
           "claim": None if c is None else {"owner": c.owner_work_id, "status": c.status}}
    stuck = []
    if c is not None and c.status == "HELD":
        stuck.append(f"scope claim HELD by {c.owner_work_id}: run-once replays it; {REVIEW_REQUIRED} if it cannot finish")
    if a is not None and a.status == "SUSPENDED":
        stuck.append(f"serving SUSPENDED by {a.suspended_by}: denied until that work completes or is rolled back")
    out["attention"] = stuck
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="amc_publication.operator_cli", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("submit", help="queue an approved publication")
    for flag in ("tenant", "entity", "attribute", "value", "corpus", "proposal-id", "proposer", "reviewer"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--revision", type=int, default=1)
    p.add_argument("--attest-independent-approval", action="store_true")
    sub.add_parser("run-once", help="claim and process one queued job (publish, replay or rollback)")
    r = sub.add_parser("rollback", help="request rollback of a published work, then run-once")
    r.add_argument("--tenant", required=True)
    r.add_argument("--work-id", required=True)
    s = sub.add_parser("status", help="read-only durable state for a tenant")
    s.add_argument("--tenant", required=True)
    args = parser.parse_args(argv)
    handler = {"submit": cmd_submit, "run-once": cmd_run_once, "rollback": cmd_rollback, "status": cmd_status}[args.cmd]
    try:
        result = handler(args)
    except CliRefused as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 2
    except Exception as exc:       # noqa: BLE001  report, never a bare traceback with credentials
        print(json.dumps({"ok": False, "error": type(exc).__name__, "detail": str(exc)[:300]}))
        return 2
    print(json.dumps(result, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
