"""SQL-backed transactional journal for publication and rollback.

Properties:
* one job per (tenant, idempotency key); mismatched replay -> conflict;
* monotonic claim epoch and lease, database-conditional claim;
* durable preimage recorded before any external mutation;
* verified effect readbacks required for a receipt;
* active generation pointer switched with expected-generation CAS;
* retry after process death, but stale owners cannot commit receipts.

Do not use SQLite for multiple production workers. PostgreSQL is the target for
multi-worker deployment; run the PostgreSQL concurrency suite before rollout.
"""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .models import PublicationWork, PublicationEffect, GenerationPointer, PublicationReceipt, PublicationFence, utcnow
from .types import Claim, Conflict, LeaseLost, PublicationError, sha256_json


class Journal:
    def __init__(self, sessions: sessionmaker, lease_seconds: int = 60):
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.sessions, self.lease_seconds = sessions, lease_seconds

    def submit(self, *, tenant: str, key: str, proposal_id: str, revision: int, payload: dict) -> str:
        if not (tenant and key and proposal_id and revision > 0):
            raise ValueError("tenant, key, proposal_id and approved revision required")
        if not isinstance(payload, dict) or not payload.get("entity") or not payload.get("attribute"):
            raise ValueError("publication payload requires graph entity and attribute")
        if not isinstance(payload.get("full_vector_snapshot"), list):
            raise ValueError("full_vector_snapshot must be an explicit COMPLETE corpus list")
        digest = sha256_json({"proposal": proposal_id, "revision": revision, "payload": payload})
        with self.sessions() as session:
            existing = session.scalar(select(PublicationWork).where(
                PublicationWork.tenant == tenant, PublicationWork.idempotency_key == key
            ))
            if existing:
                if existing.payload_hash != digest:
                    raise Conflict("same tenant/idempotency key reused with different payload")
                return existing.id
            job_id = "pub_" + uuid4().hex[:24]
            session.add(PublicationWork(
                id=job_id, tenant=tenant, idempotency_key=key,
                proposal_id=proposal_id, approved_revision=revision,
                payload_hash=digest, payload=payload, status="queued",
            ))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(PublicationWork).where(
                    PublicationWork.tenant == tenant, PublicationWork.idempotency_key == key
                ))
                if not existing or existing.payload_hash != digest:
                    raise Conflict("concurrent submission with different payload")
                return existing.id
            return job_id

    def claim(self, owner: str, now=None):
        if not owner:
            raise ValueError("worker owner required")
        now = now or utcnow()
        # compare-and-swap update makes two workers contending for one row safe.
        with self.sessions.begin() as session:
            candidates = session.scalars(select(PublicationWork).where(or_(
                PublicationWork.status.in_(["queued", "rollback_pending"]),
                and_(PublicationWork.status == "leased", PublicationWork.lease_until < now),
            )).order_by(PublicationWork.created_at, PublicationWork.id).limit(30)).all()
            for row in candidates:
                if row.attempts >= row.max_attempts:
                    continue
                old_status, old_epoch = row.status, row.epoch
                condition = [PublicationWork.id == row.id, PublicationWork.status == old_status,
                             PublicationWork.epoch == old_epoch]
                if old_status == "leased":
                    condition.append(PublicationWork.lease_until < now)
                fence = session.get(PublicationFence, 1, with_for_update=True)
                if fence is None:
                    fence = PublicationFence(id=1, counter=0)
                    session.add(fence)
                    session.flush()
                fence.counter += 1
                token = fence.counter
                res = session.execute(update(PublicationWork).where(*condition).values(
                    status="leased", owner=owner, epoch=old_epoch + 1,
                    lease_until=now + timedelta(seconds=self.lease_seconds),
                    attempts=PublicationWork.attempts + 1, updated_at=now, fence=token,
                ))
                if res.rowcount == 1:
                    # A prior crash during rollback can be recognized from the journal.
                    mode = "rollback" if old_status == "rollback_pending" or (old_status == "leased" and row.last_error == "ROLLBACK_REQUESTED") else "publish"
                    return Claim(row.id, row.tenant, owner, old_epoch + 1, dict(row.payload), token, mode)
            return None

    def _require(self, session, claim: Claim, now=None) -> PublicationWork:
        now = now or utcnow()
        row = session.get(PublicationWork, claim.work_id)
        if not row or row.tenant != claim.tenant or row.status != "leased" or row.owner != claim.owner or row.epoch != claim.epoch or row.fence != claim.fence or not row.lease_until or row.lease_until <= now:
            raise LeaseLost("publication lease expired, revoked, or claimed by another worker")
        return row

    def assert_lease(self, claim: Claim):
        with self.sessions() as session:
            self._require(session, claim)

    def renew(self, claim: Claim):
        now = utcnow()
        with self.sessions.begin() as s:
            row = self._require(s, claim, now)
            row.lease_until = now + timedelta(seconds=self.lease_seconds)

    def pointer(self, tenant: str, namespace="vector_faiss") -> dict:
        with self.sessions() as session:
            row = session.get(GenerationPointer, (tenant, namespace))
            return {"generation_id": row.generation_id, "digest": row.artifact_digest, "epoch": row.epoch} if row else {"generation_id": None, "digest": None, "epoch": 0}

    def effect(self, job_id: str, kind: str, target: str) -> dict | None:
        with self.sessions() as session:
            row = session.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == job_id, PublicationEffect.kind == kind,
                PublicationEffect.target == target))
            if row is None:
                return None
            return {"pre": row.preimage, "post": row.postimage, "state": row.state,
                    "pre_hash": row.pre_hash, "post_hash": row.post_hash}

    def prepare(self, claim: Claim, *, kind: str, target: str, pre: dict, post: dict):
        """Durable before any side effect. Replays must use the original preimage."""
        with self.sessions.begin() as s:
            self._require(s, claim)
            existing = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id, PublicationEffect.kind == kind,
                PublicationEffect.target == target))
            if existing:
                if existing.post_hash != sha256_json(post):
                    raise Conflict("effect retry is not identical to first attempt")
                return dict(existing.preimage)
            s.add(PublicationEffect(
                id="eff_" + uuid4().hex[:24], work_id=claim.work_id, tenant=claim.tenant,
                kind=kind, target=target, preimage=pre, postimage=post,
                pre_hash=sha256_json(pre), post_hash=sha256_json(post),
                claim_epoch=claim.epoch, state="prepared",
            ))
            return pre

    def verified(self, claim: Claim, *, kind: str, target: str, observed: dict):
        with self.sessions.begin() as s:
            self._require(s, claim)
            row = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id, PublicationEffect.kind == kind,
                PublicationEffect.target == target))
            if not row or sha256_json(observed) != row.post_hash:
                raise Conflict("readback does not match intended exact postcondition")
            row.state = "verified"
            row.claim_epoch = claim.epoch
            row.verified_at = utcnow()

    def switch_pointer(self, claim: Claim, *, namespace: str, expected: dict, new_id: str, digest: str):
        """CAS under a short DB transaction, never blindly overwrite a new generation."""
        with self.sessions.begin() as s:
            self._require(s, claim)
            row = s.get(GenerationPointer, (claim.tenant, namespace))
            cur = {"generation_id": row.generation_id, "digest": row.artifact_digest, "epoch": row.epoch} if row else {"generation_id": None, "digest": None, "epoch": 0}
            if cur["generation_id"] == new_id and cur["digest"] == digest:
                # Replay after crash: already switched to our generation.
                return
            if cur != expected:
                raise Conflict("active generation pointer changed since preimage; refusing stale activation")
            if row:
                row.generation_id, row.artifact_digest, row.epoch, row.activated_at = new_id, digest, row.epoch + 1, utcnow()
            else:
                s.add(GenerationPointer(tenant=claim.tenant, namespace=namespace, generation_id=new_id,
                                        artifact_digest=digest, epoch=1))

    def publish(self, claim: Claim) -> str:
        with self.sessions.begin() as s:
            row = self._require(s, claim)
            effects = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == claim.work_id)).all()
            graph = [e for e in effects if e.kind == "graph"]
            vector = [e for e in effects if e.kind == "vector"]
            if len(graph) != 1 or len(vector) != 1 or any(e.state != "verified" for e in effects):
                raise Conflict("cannot publish: both exact graph/vector effect receipts are required")
            ptr = s.get(GenerationPointer, (claim.tenant, "vector_faiss"))
            if not ptr or ptr.generation_id != vector[0].postimage["generation_id"] or ptr.artifact_digest != vector[0].postimage["digest"]:
                raise Conflict("active vector pointer does not match verified publication effect")
            receipt = PublicationReceipt(id="rcpt_"+uuid4().hex[:24],work_id=claim.work_id,
                                         tenant=claim.tenant,graph_hash=graph[0].post_hash,
                                         generation_id=ptr.generation_id,generation_digest=ptr.artifact_digest,
                                         verified=True)
            s.add(receipt)
            row.status, row.owner, row.lease_until, row.last_error = "published", None, None, None
            return receipt.id

    def retry(self, claim: Claim, error: Exception):
        with self.sessions.begin() as s:
            row = self._require(s, claim)
            if row.attempts >= row.max_attempts:
                row.status = "failed"
            else:
                row.status = "rollback_pending" if claim.mode == "rollback" else "queued"
            row.owner = None
            row.lease_until = None
            row.last_error = ("ROLLBACK_REQUESTED" if claim.mode == "rollback" else str(error))[:4000]

    def request_rollback(self, job_id: str, tenant: str):
        with self.sessions.begin() as s:
            row = s.get(PublicationWork, job_id)
            if row is None or row.tenant != tenant or row.status not in ("published", "rollback_pending"):
                raise Conflict("only a verified published job of this tenant can be rolled back")
            row.status = "rollback_pending"
            row.last_error = "ROLLBACK_REQUESTED"
            row.attempts = 0

    def switch_back(self, claim: Claim, *, current_id: str, current_digest: str, before: dict):
        """Restores an existing previous generation; empty baseline requires a dedicated deactivation."""
        with self.sessions.begin() as s:
            self._require(s, claim)
            row = s.get(GenerationPointer, (claim.tenant, "vector_faiss"))
            if not row or row.generation_id != current_id or row.artifact_digest != current_digest:
                raise Conflict("active pointer changed; manual rollback reconciliation required")
            if before["generation_id"] is None:
                # No prior corpus: delete only the exact generation being rolled back.
                s.delete(row)
            else:
                row.generation_id, row.artifact_digest = before["generation_id"], before["digest"]
                row.epoch += 1
                row.activated_at = utcnow()

    def compensate(self, claim: Claim, kind: str, target: str):
        with self.sessions.begin() as s:
            self._require(s, claim)
            effect = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id, PublicationEffect.kind == kind,
                PublicationEffect.target == target))
            if not effect:
                raise Conflict("missing persisted preimage for compensation")
            effect.state = "compensated"

    def finish_rollback(self, claim: Claim):
        with self.sessions.begin() as s:
            row = self._require(s, claim)
            effects = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == claim.work_id)).all()
            if len(effects) != 2 or any(e.state != "compensated" for e in effects):
                raise Conflict("cannot mark rolled_back without both compensations")
            row.status, row.owner, row.lease_until = "rolled_back", None, None

    def snapshot(self, job_id: str) -> dict | None:
        with self.sessions() as s:
            row = s.get(PublicationWork, job_id)
            if row is None:
                return None
            return {"id": row.id, "status": row.status, "epoch": row.epoch,
                    "attempts": row.attempts, "last_error": row.last_error, "tenant": row.tenant}
