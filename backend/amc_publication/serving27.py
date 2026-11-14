"""Fail-closed authoritative generation eligibility and loaded-reader verification.

Read-only; DOES NOT change publication state or activate a vector index.
The activation probe intentionally makes no claim that publication has completed.

A real deployment must pass a serving_loader which reloads and proves that the
actual serving FAISS reader references the selected immutable generation.
This module cannot, by itself, establish that legacy retrieval calls use it.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .models import (GenerationPointer, PublicationWork, PublicationReceipt,
                     PublicationEffect)
from .types import sha256_json


class ServingDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedServingGeneration:
    tenant: str
    generation_id: str
    digest: str
    epoch: int
    work_id: str
    receipt_id: str
    document_count: int


class VerifiedGenerationResolver:
    def __init__(self, sessions: sessionmaker, store: Any, *,
                 serving_loader: Callable[[str, str, str], bool]):
        if not callable(serving_loader):
            raise ValueError('actual serving reader loader/probe is required')
        if not callable(getattr(store, 'verify_by_digest', None)):
            raise ValueError('verified artifact store is required')
        self.sessions = sessions
        self.store = store
        self.serving_loader = serving_loader

    @staticmethod
    def _check_tenant(tenant: str):
        if not isinstance(tenant, str) or not tenant.strip():
            raise ServingDenied('explicit authenticated tenant required')

    def _pointer(self, tenant: str) -> tuple[str, str, int]:
        with self.sessions() as s:
            p = s.get(GenerationPointer, (tenant, 'vector_faiss'))
            if not p or not p.generation_id or not p.artifact_digest or p.epoch < 1:
                raise ServingDenied('no authoritative active generation')
            if p.generation_id != p.artifact_digest:
                # AMC full-corpus IDs are content digests, never arbitrary tags.
                raise ServingDenied('generation/digest identity mismatch')
            return p.generation_id, p.artifact_digest, p.epoch

    def probe_activation(self, tenant: str, generation_id: str, digest: str) -> bool:
        """Check loaded reader before writing receipt; NOT eligibility to serve.

        Used by Wave 2.6 worker serving_probe AFTER pointer CAS, BEFORE the
        publication receipt exists. This ordering prevents a receipt deadlock.
        The request serving path MUST separately call resolve_for_serving().
        """
        self._check_tenant(tenant)
        if (generation_id, digest) != self._pointer(tenant)[:2]:
            raise ServingDenied('reader probe does not match active pointer')
        self.store.verify_by_digest(digest, tenant)
        if self.serving_loader(tenant, generation_id, digest) is not True:
            raise ServingDenied('actual serving reader did not load generation')
        if (generation_id, digest) != self._pointer(tenant)[:2]:
            raise ServingDenied('pointer changed during reader load')
        return True

    def _receipt(self, tenant: str, generation_id: str, digest: str,
                 work_id: str | None, receipt_id: str | None) -> tuple[str, str, int]:
        with self.sessions() as s:
            q = (select(PublicationReceipt, PublicationWork)
                 .join(PublicationWork, PublicationReceipt.work_id == PublicationWork.id)
                 .where(PublicationReceipt.tenant == tenant,
                        PublicationWork.tenant == tenant,
                        PublicationReceipt.verified.is_(True),
                        PublicationWork.status == 'published',
                        PublicationReceipt.generation_id == generation_id,
                        PublicationReceipt.generation_digest == digest))
            if work_id is not None:
                q = q.where(PublicationWork.id == work_id)
            if receipt_id is not None:
                q = q.where(PublicationReceipt.id == receipt_id)
            matches = s.execute(q).all()
            if len(matches) != 1:
                raise ServingDenied('no unique active verified publication receipt')
            receipt, job = matches[0]
            effects = s.scalars(select(PublicationEffect).where(
                PublicationEffect.work_id == job.id,
                PublicationEffect.tenant == tenant)).all()
            if len(effects) != 2 or {e.kind for e in effects} != {'graph', 'vector'}:
                raise ServingDenied('missing exact graph/vector effect pair')
            if any(e.state != 'verified' or e.verified_at is None or
                   sha256_json(e.postimage) != e.post_hash for e in effects):
                raise ServingDenied('unverified or altered external effect')
            graph = next(e for e in effects if e.kind == 'graph')
            vector = next(e for e in effects if e.kind == 'vector')
            if graph.post_hash != receipt.graph_hash or (
                vector.postimage.get('generation_id'), vector.postimage.get('digest')
            ) != (generation_id, digest):
                raise ServingDenied('receipt/effect artifact mismatch')
            return job.id, receipt.id, int(vector.postimage.get('count', -1))

    def resolve_for_serving(self, tenant: str, *, work_id: str | None = None,
                            receipt_id: str | None = None) -> VerifiedServingGeneration:
        """Eligible only if pointer, receipt, effects, verified bytes and reader agree.

        The caller must use this per request, including after rollback. It must
        NOT cache the Boolean outcome independently of the pointer epoch.
        """
        self._check_tenant(tenant)
        if work_id is not None and (not isinstance(work_id, str) or not work_id):
            raise ServingDenied('invalid work ID')
        if receipt_id is not None and (not isinstance(receipt_id, str) or not receipt_id):
            raise ServingDenied('invalid receipt ID')
        generation, digest, epoch = self._pointer(tenant)
        wid, rid, count = self._receipt(tenant, generation, digest, work_id, receipt_id)
        docs = self.store.verify_by_digest(digest, tenant)
        if not isinstance(docs, list) or len(docs) != count or count < 1:
            raise ServingDenied('artifact count does not match durable effect')
        if self.serving_loader(tenant, generation, digest) is not True:
            raise ServingDenied('live serving reader not loaded')
        # Validate after asynchronous/external file and reader activity to prevent
        # a rollback/replacement from leaving the request bound to stale evidence.
        if self._pointer(tenant) != (generation, digest, epoch):
            raise ServingDenied('active pointer changed during serving validation')
        if self._receipt(tenant, generation, digest, wid, rid) != (wid, rid, count):
            raise ServingDenied('publication receipt changed during validation')
        return VerifiedServingGeneration(tenant, generation, digest, epoch, wid, rid, count)
