"""Offline operator CLI for verified publication (Wave 3.1, WP08).

The pilot has NO HTTP publication endpoint; an operator publishes, replays and rolls back from here.
It builds the PRODUCTION worker (real FAISS generation store, real Neo4j graph port, real serving
probe) against the PostgreSQL named by DATABASE_URL, after proving the database is at the exact
migration revision. It never edits state by hand and never force-releases a claim.

Two controls are VERIFIED, not attested:
  * Approval: `submit` needs an approval record signed by two different approvers, each with their own
    Ed25519 key, over this exact change and corpus (see approvals31.py). The signed record is stored with the work
    and the worker re-verifies it before any effect. The operator host holds only the approvers' PUBLIC keys.
  * Generations: every FAISS generation the worker publishes is signed with the publisher key and verified with
    the trusted public keys before it can be activated or served (see signing31.py).

    python -m amc_publication.operator_cli submit  --tenant T --entity E --attribute A --value V \\
        --corpus corpus.json --proposal-id P --revision 1 --approval approval.json
    python -m amc_publication.operator_cli run-once
    python -m amc_publication.operator_cli rollback --tenant T --work-id W
    python -m amc_publication.operator_cli status   --tenant T

Structured fund data (Wave 4.0, fin40):
    python -m amc_publication.operator_cli fin-stage    --tenant T --chunks-dir data/source_docs/chunks
    python -m amc_publication.operator_cli fin-subject  --tenant T --dataset-version V --proposal-id P \\
        --corpus-out fin_manifest.json --record-out fin_approval.json
    (two approvers sign fin_approval.json with amc_publication.approvals31 sign --corpus fin_manifest.json)
    python -m amc_publication.operator_cli fin-activate --tenant T --dataset-version V --approval fin_approval.json
    python -m amc_publication.operator_cli fin-status   --tenant T

Environment: DATABASE_URL (postgresql+psycopg); for submit AMC_PUBLICATION_APPROVER_KEYS (approver public keys);
for run-once AMC_VERIFIED_FAISS_ROOT, NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD, AMC_PUBLICATION_GRAPH_ATTRIBUTES
(explicit allowlist), AMC_PUBLICATION_SIGNING_KEY_FILE (publisher private key), AMC_VERIFIED_FAISS_PUBLIC_KEYS,
AMC_PUBLICATION_APPROVER_KEYS, AMC_PUBLICATION_EMBEDDER ("package.module:factory", default
app.vector.client:get_base_vector_store).
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


def _journal(engine):
    """Submit and rollback only need the journal: no Neo4j, no keys."""
    from sqlalchemy.orm import sessionmaker
    from .journal import Journal
    return Journal(sessionmaker(bind=engine))


def _approver_verifier():
    from .approvals31 import TRUST_ENV, approver_verifier_from_env
    try:
        verifier = approver_verifier_from_env()
    except ValueError as exc:
        raise CliRefused(str(exc)) from exc
    if verifier is None:
        raise CliRefused(f"{TRUST_ENV} is required: approvals are verified against the approvers' public keys")
    return verifier


def _build(engine):
    """The production worker: signed generations, verified approvals, real Neo4j, real serving probe."""
    from sqlalchemy.orm import sessionmaker
    from neo4j import GraphDatabase
    from .journal import Journal
    from .faiss_artifacts import FaissGenerationStore
    from .faiss_reader27 import VerifiedFaissRetriever
    from .serving28 import ActiveReceiptResolver
    from .graph import Neo4jGraphPort
    from .worker import PublicationWorker
    from .signing31 import PUBLIC_KEYS_ENV, SIGNING_KEY_ENV, signer_from_env, verifier_from_env
    try:
        signer, verifier = signer_from_env(), verifier_from_env()
    except ValueError as exc:
        raise CliRefused(str(exc)) from exc
    if signer is None:
        raise CliRefused(f"{SIGNING_KEY_ENV} is required: published generations must be signed")
    if verifier is None:
        raise CliRefused(f"{PUBLIC_KEYS_ENV} is required: generations are verified against trusted public keys")
    if not verifier.trusts(signer.key_id, signer.public_key_b64):
        raise CliRefused(f"the signing key {signer.key_id!r} is not trusted by {PUBLIC_KEYS_ENV} (unknown or revoked)")
    approvals = _approver_verifier()
    sessions = sessionmaker(bind=engine)
    root = _env("AMC_VERIFIED_FAISS_ROOT")
    attrs = {a.strip() for a in _env("AMC_PUBLICATION_GRAPH_ATTRIBUTES").split(",") if a.strip()}
    driver = GraphDatabase.driver(_env("NEO4J_URI"), auth=(_env("NEO4J_USER"), _env("NEO4J_PASSWORD")))
    driver.verify_connectivity()
    store = FaissGenerationStore(root, _embedder(), signer=signer, verifier=verifier)
    reader = VerifiedFaissRetriever(sessions, root, verifier=verifier)
    reader.resolver = ActiveReceiptResolver(sessions, reader.store, serving_loader=reader._load)
    graph = Neo4jGraphPort(driver, label="Entity", allowed_attributes=attrs)
    worker = PublicationWorker(Journal(sessions), graph, store, serving_probe=reader.probe_activation,
                               approval_verifier=approvals)
    return sessions, worker, driver


def cmd_submit(args) -> dict:
    from .approvals31 import ApprovalRefused, make_subject
    from .integration import ApprovedProposal, queue_verified_approval
    from .types import Conflict
    with open(args.corpus, encoding="utf-8") as fh:
        corpus = json.load(fh)
    if not isinstance(corpus, list) or not corpus:
        raise CliRefused("--corpus must be a nonempty JSON list (a COMPLETE corpus snapshot)")
    if any(not isinstance(r, dict) or r.get("tenant_id") != args.tenant for r in corpus):
        raise CliRefused("every corpus row must carry tenant_id == --tenant")
    try:
        with open(args.approval, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CliRefused(f"--approval {args.approval!r} is missing or not valid JSON") from exc
    verifier = _approver_verifier()
    try:
        expected = make_subject(tenant=args.tenant, entity=args.entity, attribute=args.attribute, value=args.value,
                                proposal_id=args.proposal_id, revision=args.revision, corpus=corpus)
        approved = verifier.verify(record, expected_subject=expected)
    except ApprovalRefused as exc:
        raise CliRefused(f"approval refused: {exc}") from exc
    engine = _engine()
    journal = _journal(engine)
    proposal = ApprovedProposal(proposal_id=args.proposal_id, tenant=args.tenant, revision=args.revision,
                                proposer_id=approved.proposer, reviewer_id=approved.reviewer, status="APPROVED",
                                entity_id=args.entity, attribute=args.attribute, proposed_value=args.value)
    try:
        work_id = queue_verified_approval(journal, proposal, corpus, approval_evidence=record)
    except Conflict as exc:
        raise CliRefused(str(exc)) from exc
    return {"ok": True, "work_id": work_id, "proposer": approved.proposer, "reviewer": approved.reviewer,
            "approval_sha256": approved.evidence_sha256, "next": "run-once"}


def cmd_run_once(_args) -> dict:
    engine = _engine()
    _sessions, worker, driver = _build(engine)
    try:
        result = worker.run_once()
    finally:
        driver.close()
    return {"ok": result.get("status") in ("published", "rolled_back", "no_jobs"), **result}


def cmd_rollback(args) -> dict:
    from .types import Conflict
    engine = _engine()
    journal = _journal(engine)
    try:
        journal.request_rollback(args.work_id, args.tenant)
    except Conflict as exc:
        raise CliRefused(str(exc)) from exc
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


# ------------------------------------------------------------------ Wave 4.0: structured (fin) dataset plane

def _fin_keys():
    from .signing31 import PUBLIC_KEYS_ENV, signer_from_env, verifier_from_env
    try:
        return signer_from_env(), verifier_from_env()
    except ValueError as exc:
        raise CliRefused(str(exc)) from exc


def cmd_fin_stage(args) -> dict:
    """Stage, reconcile and sign one dataset version. Never activates."""
    from sqlalchemy.orm import sessionmaker
    from .fin40 import stage_dataset
    from .signing31 import SIGNING_KEY_ENV
    from .types import Conflict
    signer, verifier = _fin_keys()
    if signer is None:
        raise CliRefused(f"{SIGNING_KEY_ENV} is required: staged datasets must be signed")
    if verifier is not None and not verifier.trusts(signer.key_id, signer.public_key_b64):
        raise CliRefused(f"the signing key {signer.key_id!r} is not trusted (unknown or revoked)")
    sessions = sessionmaker(bind=_engine(), expire_on_commit=False)
    try:
        with sessions.begin() as s:
            report = stage_dataset(s, tenant=args.tenant, chunks_dir=args.chunks_dir, signer=signer)
    except Conflict as exc:
        raise CliRefused(f"staging refused: {exc}") from exc
    return {"ok": True, **report.as_dict(), "next": "fin-subject, then two approvers sign, then fin-activate"}


def cmd_fin_subject(args) -> dict:
    """Write what approvers must review (manifest as the 'corpus') and an unsigned approval record."""
    from datetime import timedelta
    from sqlalchemy.orm import sessionmaker
    from .approvals31 import new_record
    from .fin40 import FinDatasetVersion, activation_subject
    sessions = sessionmaker(bind=_engine())
    with sessions() as s:
        ds = s.get(FinDatasetVersion, args.dataset_version)
        if ds is None or ds.tenant != args.tenant:
            raise CliRefused("dataset version does not exist for this tenant")
        manifest = ds.manifest
    corpus = [{"chunk_id": f"fin:{args.dataset_version}", "manifest": manifest}]
    subject = activation_subject(tenant=args.tenant, dataset_version=args.dataset_version, manifest=manifest,
                                 proposal_id=args.proposal_id, revision=args.revision)
    record = new_record(subject, valid_for=timedelta(days=args.valid_days))
    with open(args.corpus_out, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2)
    with open(args.record_out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return {"ok": True, "corpus": args.corpus_out, "record": args.record_out, "counts": manifest.get("counts"),
            "next": "each approver: python -m amc_publication.approvals31 sign --record ... --corpus ... "
                    "--key-file <own key> --role proposer|reviewer"}


def cmd_fin_activate(args) -> dict:
    """Activate (or roll back to) one dataset version in one SQL transaction, with two-person approval."""
    from sqlalchemy.orm import sessionmaker
    from .approvals31 import ApprovalRefused
    from .fin40 import activate_dataset
    from .types import Conflict, VerificationFailed
    _signer, verifier = _fin_keys()
    if verifier is None:
        raise CliRefused("AMC_VERIFIED_FAISS_PUBLIC_KEYS is required: datasets are verified before activation")
    try:
        with open(args.approval, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CliRefused(f"--approval {args.approval!r} is missing or not valid JSON") from exc
    approvals = _approver_verifier()
    sessions = sessionmaker(bind=_engine(), expire_on_commit=False)
    try:
        with sessions.begin() as s:
            receipt = activate_dataset(s, tenant=args.tenant, dataset_version=args.dataset_version,
                                       approval_record=record, approval_verifier=approvals,
                                       generation_verifier=verifier)
    except (Conflict, VerificationFailed, ApprovalRefused) as exc:
        raise CliRefused(f"activation refused: {exc}") from exc
    return {"ok": True, "receipt": receipt.id, "dataset_version": receipt.dataset_version,
            "previous_dataset_version": receipt.previous_dataset_version, "proposer": receipt.proposer,
            "reviewer": receipt.reviewer}


def cmd_fin_status(args) -> dict:
    """Read-only."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from .active_authority28 import PublicationScopeClaim31
    from .fin40 import DOMAIN, NAMESPACE, FinActiveDataset, FinDatasetVersion
    sessions = sessionmaker(bind=_engine())
    with sessions() as s:
        p = s.get(FinActiveDataset, (args.tenant, DOMAIN))
        c = s.get(PublicationScopeClaim31, (args.tenant, NAMESPACE))
        versions = {d.dataset_version: {"status": d.status, "valid": d.valid_rows, "rejected": d.rejected_rows,
                                        "created_at": d.created_at}
                    for d in s.scalars(select(FinDatasetVersion).where(FinDatasetVersion.tenant == args.tenant))}
    out = {"ok": True, "tenant": args.tenant, "versions": versions,
           "active": None if p is None else {"dataset_version": p.dataset_version, "receipt": p.receipt_id,
                                             "epoch": p.epoch},
           "claim": None if c is None else {"owner": c.owner_work_id, "status": c.status}}
    out["attention"] = ([f"fin scope claim HELD by {c.owner_work_id}: {REVIEW_REQUIRED}"]
                        if c is not None and c.status == "HELD" else [])
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="amc_publication.operator_cli", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    fs = sub.add_parser("fin-stage", help="stage, reconcile and sign a structured dataset version (no activation)")
    fs.add_argument("--tenant", required=True)
    fs.add_argument("--chunks-dir", required=True)
    fj = sub.add_parser("fin-subject", help="write the manifest and an unsigned approval record for approvers")
    for flag in ("tenant", "dataset-version", "proposal-id", "corpus-out", "record-out"):
        fj.add_argument("--" + flag, required=True)
    fj.add_argument("--revision", type=int, default=1)
    fj.add_argument("--valid-days", type=int, default=3)
    fa = sub.add_parser("fin-activate", help="activate or roll back to a dataset version (two-person approval)")
    for flag in ("tenant", "dataset-version", "approval"):
        fa.add_argument("--" + flag, required=True)
    ft = sub.add_parser("fin-status", help="read-only structured dataset state for a tenant")
    ft.add_argument("--tenant", required=True)
    p = sub.add_parser("submit", help="queue an approved publication")
    for flag in ("tenant", "entity", "attribute", "value", "corpus", "proposal-id", "approval"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--revision", type=int, default=1)
    sub.add_parser("run-once", help="claim and process one queued job (publish, replay or rollback)")
    r = sub.add_parser("rollback", help="request rollback of a published work, then run-once")
    r.add_argument("--tenant", required=True)
    r.add_argument("--work-id", required=True)
    s = sub.add_parser("status", help="read-only durable state for a tenant")
    s.add_argument("--tenant", required=True)
    args = parser.parse_args(argv)
    handler = {"submit": cmd_submit, "run-once": cmd_run_once, "rollback": cmd_rollback, "status": cmd_status,
               "fin-stage": cmd_fin_stage, "fin-subject": cmd_fin_subject, "fin-activate": cmd_fin_activate,
               "fin-status": cmd_fin_status}[args.cmd]
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
