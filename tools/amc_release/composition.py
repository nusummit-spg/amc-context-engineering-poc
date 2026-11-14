"""GATE01 read-only cross-store publication acceptance probe.

This is deliberately *not* a publication worker or state machine. It compares
persistent Wave 1.9 work/effect/receipt/pointer facts with an independent graph
read and immutable generation artifact verification. Real acceptance requires
real Neo4jGraphPort + FaissGenerationStore; all fakes are SIMULATION_ONLY.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PublicationReadback:
    tenant: str
    work_id: str
    mode: str
    status: str
    checks: dict[str, bool]
    reasons: tuple[str, ...]
    release_evidence_eligible: bool

    def to_dict(self) -> dict:
        return asdict(self)


def inspect(*, sessions, graph: Any, snapshots: Any, tenant: str,
            work_id: str, expected_issue_id: str | None = None,
            mode: str = 'simulation', reader_probe=None) -> PublicationReadback:
    """Check one already-published work item; performs no writes.

    Requires application-supplied DB sessionmaker, graph port and snapshot
    store, bound to an explicitly identified tenant and work. Never trusts
    a caller's bool such as ``verified=True`` in lieu of external readback.
    """
    if not isinstance(tenant, str) or not tenant or not isinstance(work_id, str) or not work_id:
        raise ValueError('explicit tenant and work ID required')
    if mode not in {'simulation', 'live'}:
        raise ValueError('mode must be simulation or live')
    from sqlalchemy import select
    from amc_publication.models import (PublicationWork, PublicationEffect, PublicationReceipt,
                                        GenerationPointer, FeedbackPublicationLink)
    from amc_publication.types import Generation, sha256_json
    from amc_publication.graph import Neo4jGraphPort
    from amc_publication.faiss_artifacts import FaissGenerationStore

    checks: dict[str, bool] = {}
    reasons: list[str] = []

    def check(label: str, condition: bool):
        checks[label] = bool(condition)
        if not condition:
            reasons.append(label)

    real_adapters = isinstance(graph, Neo4jGraphPort) and isinstance(snapshots, FaissGenerationStore)
    check('REAL_EXTERNAL_ADAPTERS', mode != 'live' or real_adapters)
    check('LIVE_READER_PROBE_CONFIGURED', mode != 'live' or callable(reader_probe))

    with sessions() as s:
        work = s.get(PublicationWork, work_id)
        check('TENANT_SCOPED_PUBLISHED_WORK', work is not None and work.tenant == tenant and work.status == 'published')
        if not checks['TENANT_SCOPED_PUBLISHED_WORK']:
            return PublicationReadback(tenant, work_id, mode, 'FAIL', checks, tuple(reasons), False)
        receipt = s.scalar(select(PublicationReceipt).where(PublicationReceipt.work_id == work_id))
        check('VERIFIED_TENANT_RECEIPT', receipt is not None and receipt.tenant == tenant and receipt.verified is True)
        effects = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == work_id)).all()
        graph_effects = [e for e in effects if e.kind == 'graph' and e.tenant == tenant and e.state == 'verified']
        vector_effects = [e for e in effects if e.kind == 'vector' and e.tenant == tenant and e.state == 'verified']
        check('EXACT_TWO_VERIFIED_EFFECTS', len(effects) == 2 and len(graph_effects) == 1 and len(vector_effects) == 1)
        pointer = s.get(GenerationPointer, (tenant, 'vector_faiss'))
        check('CURRENT_POINTER_MATCHES_RECEIPT', bool(receipt and pointer and pointer.generation_id == receipt.generation_id and pointer.artifact_digest == receipt.generation_digest))
        if expected_issue_id:
            feedback = s.get(FeedbackPublicationLink, (tenant, expected_issue_id))
            check('TENANT_SCOPED_FEEDBACK', bool(feedback and receipt and feedback.status == 'resolved' and feedback.work_id == work_id and feedback.receipt_id == receipt.id))
        if not all(checks.values()):
            return PublicationReadback(tenant, work_id, mode, 'FAIL', checks, tuple(reasons), False)
        g, v = graph_effects[0], vector_effects[0]
        check('EFFECT_GRAPH_TARGET_MATCHES_WORK', g.target in {work.payload.get('entity'), f"{work.payload.get('entity')}:{work.payload.get('attribute')}"})
        check('EFFECT_VECTOR_TARGET_MATCHES_WORK', v.target in {work.payload.get('entity'), 'vector_faiss'})
        check('RECEIPT_AND_EFFECT_HASH', bool(receipt and g.post_hash == receipt.graph_hash and v.postimage.get('generation_id') == receipt.generation_id and v.postimage.get('digest') == receipt.generation_digest))
        graph_identity = work.payload.get('entity')
        graph_attribute = work.payload.get('attribute')
        g_expected = dict(g.postimage)
        vector_id = receipt.generation_id
        vector_digest = receipt.generation_digest
        count = v.postimage.get('count')
    # Read external systems outside the short SQL transaction.
    if all(checks.values()):
        try:
            graph_readback = graph.read(tenant, graph_identity, graph_attribute)
            check('GRAPH_INDEPENDENT_READBACK', graph_readback == g_expected and sha256_json(graph_readback) == g.post_hash)
        except Exception:
            check('GRAPH_INDEPENDENT_READBACK', False)
        try:
            if count is None:
                documents = snapshots.verify_by_digest(vector_digest, tenant)
                check('IMMUTABLE_GENERATION_READBACK', isinstance(documents, list))
            else:
                if type(count) is not int or count < 0:
                    raise ValueError('invalid generation count')
                documents = snapshots.verify(Generation(vector_id, vector_digest, count), tenant)
                check('IMMUTABLE_GENERATION_READBACK', isinstance(documents, list) and len(documents) == count)
        except Exception:
            check('IMMUTABLE_GENERATION_READBACK', False)
        if mode == 'live' and checks.get('IMMUTABLE_GENERATION_READBACK'):
            try:
                check('LIVE_READER_GENERATION_MATCH', reader_probe(tenant, vector_id, vector_digest) is True)
            except Exception:
                check('LIVE_READER_GENERATION_MATCH', False)
    if not all(checks.values()):
        return PublicationReadback(tenant, work_id, mode, 'FAIL', checks, tuple(reasons), False)
    if mode != 'live':
        return PublicationReadback(tenant, work_id, mode, 'SIMULATION_ONLY', checks, ('LIVE_SERVICE_EVIDENCE_NOT_RUN',), False)
    return PublicationReadback(tenant, work_id, mode, 'PASS', checks, (), True)
