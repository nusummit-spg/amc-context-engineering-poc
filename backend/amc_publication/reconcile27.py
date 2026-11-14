"""Bounded, read-only durable publication DB reconciliation for operators.

Never reports system/production readiness: Neo4j/FAISS/browser/SLO proofs require
separate real-service evidence. Avoids mutating or auto-repairing corrupted jobs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker
from .models import (PublicationWork, PublicationEffect, PublicationReceipt,
                     GenerationPointer, FeedbackPublicationLink)
from .feedback import FeedbackCausality
from .types import sha256_json


@dataclass(frozen=True)
class Reconciliation:
    tenant: str
    jobs: int
    receipts: int
    resolved_feedback: int
    pointer: dict | None
    violations: tuple[str, ...]
    database_integrity: str
    external_services: str = 'NOT_RUN'
    release_status: str = 'BLOCK'

    def to_dict(self) -> dict:
        return asdict(self)


def inspect(sessions: sessionmaker, tenant: str, *, limit: int = 5000) -> Reconciliation:
    if not isinstance(tenant, str) or not tenant.strip():
        raise ValueError('explicit tenant required')
    if not isinstance(limit, int) or limit < 1 or limit > 50000:
        raise ValueError('bounded limit required')
    problems: list[str] = []
    with sessions() as s:
        total = s.scalar(select(func.count()).select_from(PublicationWork).where(PublicationWork.tenant == tenant)) or 0
        if total > limit:
            return Reconciliation(tenant, total, 0, 0, None, ('UNBOUNDED_WORK_INVENTORY',), 'FAIL')
        work = s.scalars(select(PublicationWork).where(PublicationWork.tenant == tenant)).all()
        ids = {w.id for w in work}
        receipts = s.scalars(select(PublicationReceipt).where(PublicationReceipt.tenant == tenant)).all()
        effects = s.scalars(select(PublicationEffect).where(PublicationEffect.tenant == tenant)).all()
        feedback = s.scalars(select(FeedbackPublicationLink).where(FeedbackPublicationLink.tenant == tenant)).all()
        pointer = s.get(GenerationPointer, (tenant, 'vector_faiss'))
        p = {'generation_id': pointer.generation_id,'digest':pointer.artifact_digest,'epoch':pointer.epoch} if pointer else None
        for row in receipts:
            if row.work_id not in ids:
                problems.append('CROSS_TENANT_OR_ORPHAN_RECEIPT')
        for row in effects:
            if row.work_id not in ids:
                problems.append('CROSS_TENANT_OR_ORPHAN_EFFECT')
            if row.state == 'verified' and (row.verified_at is None or sha256_json(row.postimage) != row.post_hash):
                problems.append('INVALID_VERIFIED_EFFECT_HASH')
        for row in work:
            matches = [x for x in receipts if x.work_id == row.id]
            item_effects = [x for x in effects if x.work_id == row.id]
            if row.status == 'published':
                if len(matches) != 1 or not matches[0].verified:
                    problems.append('PUBLISHED_WITHOUT_VERIFIED_RECEIPT')
                if len(item_effects) != 2 or {e.kind for e in item_effects} != {'graph','vector'} or any(e.state != 'verified' for e in item_effects):
                    problems.append('PUBLISHED_WITHOUT_TWO_VERIFIED_EFFECTS')
            if row.status in {'queued','leased','rollback_pending'}:
                problems.append('INCOMPLETE_PUBLICATION_JOB')
            if row.status == 'failed':
                problems.append('FAILED_PUBLICATION_JOB')
        for link in feedback:
            if link.status == 'resolved':
                # Read-only causality implementation also checks current pointer.
                if not FeedbackCausality(sessions).is_verified_active(tenant,link.work_id,link.receipt_id):
                    problems.append('RESOLVED_FEEDBACK_WITHOUT_ACTIVE_RECEIPT')
        if p is not None:
            valid = [x for x in receipts if x.verified and x.generation_id == p['generation_id'] and x.generation_digest == p['digest'] and any(w.id == x.work_id and w.status == 'published' for w in work)]
            if len(valid) != 1:
                problems.append('ACTIVE_POINTER_WITHOUT_UNIQUE_PUBLISHED_RECEIPT')
    unique=tuple(sorted(set(problems)))
    return Reconciliation(tenant,total,len(receipts),sum(x.status=='resolved' for x in feedback),p,unique,'FAIL' if unique else 'PASS')
