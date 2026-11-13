"""Wave 2.8: durable, fail-closed active receipt authority.

This sidecar is committed in the SAME SQL transaction as the publication receipt.
The sidecar does not activate a FAISS reader; request serving also requires
independent proof of immutable bytes and the loaded reader. No automatic
backfill from legacy pointers is permitted.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.exc import IntegrityError
from .models import Base, PublicationWork, PublicationReceipt, GenerationPointer, utcnow
from .types import Conflict


class ActiveReceiptAuthority(Base):
    __tablename__ = 'publication_active_authority_v28'
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), primary_key=True)
    generation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    pointer_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_work_v2.id'), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_receipt_v2.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    suspended_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','SUSPENDED')",name='ck_authority_v28_status'),)


class AuthorityPreimage(Base):
    """Original authority captured before the graph write, keyed to work ID.

    A previous missing/legacy authority is recorded as NULL and never guessed.
    A replay must use this original record rather than observing current state.
    """
    __tablename__ = 'publication_authority_preimage_v28'
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_work_v2.id'), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_generation: Mapped[str | None] = mapped_column(String(64))
    previous_digest: Mapped[str | None] = mapped_column(String(64))
    previous_work_id: Mapped[str | None] = mapped_column(String(64))
    previous_receipt_id: Mapped[str | None] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class PublicationScopeClaim31(Base):
    """Durable, one-writer-per-tenant reservation, even before first receipt.

    A row survives crashes. Never automatically expire an in-flight claim based
    on wall-clock time: its graph side effects may have already occurred.
    Operator reconciliation is required for abandoned claims.
    """
    __tablename__ = 'publication_scope_claim_v31'
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_work_id: Mapped[str] = mapped_column(String(64), ForeignKey('publication_work_v2.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    __table_args__ = (CheckConstraint("status IN ('HELD','RELEASED')", name='ck_publication_scope_claim_v31'),)


def _claim_scope(s: Session, tenant: str, namespace: str, work_id: str, *, rollback: bool = False):
    """Serialize first publication and every later mutation/rollback.

    The unique (tenant, namespace) row prevents concurrent first publishers.
    PostgreSQL row locking serializes replacements. A race inserting the first
    row is converted to a safe Conflict via a nested savepoint.
    """
    if not all(isinstance(v, str) and v.strip() for v in (tenant, namespace, work_id)):
        raise Conflict('explicit tenant/namespace/work required for scope claim')
    claim = s.get(PublicationScopeClaim31, (tenant, namespace), with_for_update=True)
    if claim is None:
        try:
            with s.begin_nested():
                claim = PublicationScopeClaim31(tenant=tenant, namespace=namespace,
                    owner_work_id=work_id, status='HELD', claim_epoch=1)
                s.add(claim)
                s.flush()
        except IntegrityError as exc:
            raise Conflict('publication scope is held by another writer') from exc
        return claim
    if claim.status == 'HELD':
        if claim.owner_work_id != work_id:
            raise Conflict('another publication owns tenant/namespace mutation scope')
        return claim
    if claim.status != 'RELEASED':
        raise Conflict('invalid durable mutation claim status')
    if claim.owner_work_id == work_id and not rollback:
        raise Conflict('previously released publication may not reenter mutation scope')
    claim.owner_work_id = work_id
    claim.status = 'HELD'
    claim.claim_epoch += 1
    claim.updated_at = utcnow()
    return claim


def _require_scope(s: Session, tenant: str, namespace: str, work_id: str):
    claim = s.get(PublicationScopeClaim31, (tenant, namespace), with_for_update=True)
    if not claim or claim.status != 'HELD' or claim.owner_work_id != work_id:
        raise Conflict('publication has no exclusive durable mutation claim')
    return claim


def _release_scope(s: Session, tenant: str, namespace: str, work_id: str):
    claim = _require_scope(s, tenant, namespace, work_id)
    claim.status = 'RELEASED'
    claim.updated_at = utcnow()


def _get_locked(s: Session, tenant: str, namespace='vector_faiss'):
    return s.get(ActiveReceiptAuthority, (tenant, namespace), with_for_update=True)


def _pointer(s: Session, tenant: str, namespace='vector_faiss'):
    return s.get(GenerationPointer, (tenant, namespace), with_for_update=True)


def suspend_before_graph(s: Session, claim, namespace='vector_faiss'):
    """Atomically revoke serving before any graph mutation. Call within prepare()."""
    # W31_SCOPE_CLAIM: claim first, before reading the pointer or graph preimage.
    _claim_scope(s, claim.tenant, namespace, claim.work_id)
    authority = _get_locked(s, claim.tenant, namespace)
    existing = s.get(AuthorityPreimage, claim.work_id)
    if existing:
        if existing.tenant != claim.tenant or existing.namespace != namespace:
            raise Conflict('authority preimage tenant/namespace mismatch')
        # W30: On crash replay a prior preimage is not itself permission to
        # mutate the graph. Ensure the OLD authoritative generation remains
        # suspended by this exact work. A later ACTIVE receipt must never be
        # overwritten by retrying a stale claimed publication.
        if authority:
            if (authority.status != 'SUSPENDED' or
                    authority.suspended_by != claim.work_id or
                    (authority.generation_id, authority.digest) !=
                    (existing.previous_generation, existing.previous_digest) or
                    (authority.work_id, authority.receipt_id) !=
                    (existing.previous_work_id, existing.previous_receipt_id)):
                raise Conflict('replay no longer owns the suspended authority')
        elif existing.previous_receipt_id or existing.previous_work_id:
            raise Conflict('previous verified authority disappeared during replay')
        pointer = _pointer(s, claim.tenant, namespace)
        if pointer and (pointer.generation_id, pointer.artifact_digest) != (
                existing.previous_generation, existing.previous_digest):
            from .models import PublicationEffect
            effect = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id,
                PublicationEffect.kind == 'vector',
                PublicationEffect.tenant == claim.tenant))
            # A crash AFTER this work's pointer switch is recoverable; an
            # unrelated generation change is not.
            if (not effect or
                    (pointer.generation_id, pointer.artifact_digest) !=
                    (effect.postimage.get('generation_id'), effect.postimage.get('digest'))):
                raise Conflict('replay pointer changed to an unrelated generation')
        return
    pointer = _pointer(s, claim.tenant, namespace)
    if authority:
        if authority.status != 'ACTIVE' or authority.suspended_by:
            raise Conflict('another publication or rollback already suspended serving')
        if not pointer or (authority.generation_id, authority.digest, authority.pointer_epoch) != (pointer.generation_id, pointer.artifact_digest, pointer.epoch):
            raise Conflict('active authority does not match generation pointer')
    s.add(AuthorityPreimage(
        work_id=claim.work_id,tenant=claim.tenant,namespace=namespace,
        previous_generation=pointer.generation_id if pointer else None,
        previous_digest=pointer.artifact_digest if pointer else None,
        previous_work_id=authority.work_id if authority else None,
        previous_receipt_id=authority.receipt_id if authority else None,
    ))
    if authority:
        authority.status='SUSPENDED'
        authority.suspended_by=claim.work_id
        authority.updated_at=utcnow()


def bind_published(s: Session, claim, receipt: PublicationReceipt, namespace='vector_faiss'):
    """Call in Journal.publish's receipt transaction after effect verification."""
    _require_scope(s, claim.tenant, namespace, claim.work_id)
    p=_pointer(s,claim.tenant,namespace)
    if not p or (p.generation_id,p.artifact_digest)!=(receipt.generation_id,receipt.generation_digest):
        raise Conflict('cannot bind authority: pointer and receipt differ')
    if receipt.tenant != claim.tenant or receipt.work_id != claim.work_id or receipt.verified is not True:
        raise Conflict('cannot bind authority: untrusted receipt')
    history=s.get(AuthorityPreimage,claim.work_id)
    if not history or history.tenant!=claim.tenant:
        raise Conflict('missing durable authority preimage prior to graph write')
    a=_get_locked(s,claim.tenant,namespace)
    if a and (a.status!='SUSPENDED' or a.suspended_by != claim.work_id):
        raise Conflict('authority must be suspended by this exact publication')
    if a is None:
        s.add(ActiveReceiptAuthority(tenant=claim.tenant,namespace=namespace,
            generation_id=p.generation_id,digest=p.artifact_digest,pointer_epoch=p.epoch,
            work_id=claim.work_id,receipt_id=receipt.id,status='ACTIVE',suspended_by=None))
    else:
        a.generation_id=p.generation_id; a.digest=p.artifact_digest; a.pointer_epoch=p.epoch
        a.work_id=claim.work_id; a.receipt_id=receipt.id; a.status='ACTIVE'
        a.suspended_by=None; a.updated_at=utcnow()
    _release_scope(s, claim.tenant, namespace, claim.work_id)


def suspend_rollback(s:Session, *, tenant:str, work_id:str, namespace='vector_faiss'):
    _claim_scope(s, tenant, namespace, work_id, rollback=True)
    a=_get_locked(s,tenant,namespace)
    if a is None or a.work_id != work_id:
        raise Conflict('rollback must target currently authoritative work')
    if a.status not in ('ACTIVE','SUSPENDED') or (a.suspended_by and a.suspended_by != work_id):
        raise Conflict('authority already suspended by a different publication')
    a.status='SUSPENDED';a.suspended_by=work_id;a.updated_at=utcnow()


def restore_after_rollback(s:Session, claim, namespace='vector_faiss'):
    """Only call in finish_rollback, AFTER both graph and vector compensation."""
    _require_scope(s, claim.tenant, namespace, claim.work_id)
    history=s.get(AuthorityPreimage,claim.work_id)
    if not history or history.tenant!=claim.tenant:
        raise Conflict('missing original authority preimage for rollback')
    ptr=_pointer(s,claim.tenant,namespace)
    a=_get_locked(s,claim.tenant,namespace)
    if a and (a.work_id!=claim.work_id or a.status!='SUSPENDED'):
        raise Conflict('other publication owns authority during rollback')
    current_pointer = (ptr.generation_id, ptr.artifact_digest) if ptr else (None, None)
    if current_pointer != (history.previous_generation, history.previous_digest):
        raise Conflict('rollback pointer differs from original publication preimage')
    # No old verified authority: return to fail-closed state, not a guessed owner.
    if not history.previous_receipt_id or not history.previous_work_id:
        if a:s.delete(a)
        _release_scope(s, claim.tenant, namespace, claim.work_id)
        return
    old_receipt=s.get(PublicationReceipt,history.previous_receipt_id)
    old_work=s.get(PublicationWork,history.previous_work_id)
    if not ptr or not old_receipt or not old_work or not old_receipt.verified or old_work.status!='published':
        raise Conflict('previous authority no longer backed by a published receipt')
    if (old_receipt.tenant,old_work.tenant,old_receipt.work_id)!=(claim.tenant,claim.tenant,old_work.id):
        raise Conflict('previous authority tenant/work mismatch')
    if (old_receipt.generation_id,old_receipt.generation_digest)!=(ptr.generation_id,ptr.artifact_digest):
        raise Conflict('previous authority receipt does not match restored pointer')
    if not a:
        s.add(ActiveReceiptAuthority(tenant=claim.tenant,namespace=namespace,
            generation_id=ptr.generation_id,digest=ptr.artifact_digest,pointer_epoch=ptr.epoch,
            work_id=old_work.id,receipt_id=old_receipt.id,status='ACTIVE'))
    else:
        a.generation_id=ptr.generation_id;a.digest=ptr.artifact_digest;a.pointer_epoch=ptr.epoch
        a.work_id=old_work.id;a.receipt_id=old_receipt.id;a.status='ACTIVE'
        a.suspended_by=None;a.updated_at=utcnow()
    _release_scope(s, claim.tenant, namespace, claim.work_id)


def current_binding(s:Session,tenant:str,namespace='vector_faiss') -> tuple[str,str,int,str,str]:
    a=s.get(ActiveReceiptAuthority,(tenant,namespace))
    p=s.get(GenerationPointer,(tenant,namespace))
    if not a or a.status!='ACTIVE' or a.suspended_by or not p:
        raise Conflict('no active receipt binding')
    if (a.generation_id,a.digest,a.pointer_epoch)!=(p.generation_id,p.artifact_digest,p.epoch):
        raise Conflict('active receipt binding is stale')
    return (a.generation_id,a.digest,a.pointer_epoch,a.work_id,a.receipt_id)
