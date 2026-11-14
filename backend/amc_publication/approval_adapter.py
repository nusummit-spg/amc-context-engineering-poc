"""Wave 2.5: fail-closed, *application-integrated* queueing of approved work.

No new publication engine, schema, request-time DDL, or HTTP-supplied corpus.
A trusted operator prepares a signed, immutable *complete* tenant snapshot;
reviewer/proposer identity comes from persisted proposal data, not the request.
This is a staging integration adapter. It does not establish completeness by
itself; the signer must prove the snapshot's relationship to the source catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import hmac
import json
import os

from .integration import ApprovedProposal, queue_verified_approval
from .journal import Journal
from .types import Conflict, canonical_bytes


class ApprovalReadinessError(Conflict):
    """An approved proposal or trusted complete corpus is unavailable."""


@dataclass(frozen=True)
class VerifiedCorpus:
    tenant: str
    proposal_id: str
    revision: int
    source_version: str
    source_manifest_sha256: str
    documents: list[dict]
    file_sha256: str


def load_verified_corpus(path: str | Path, signing_key: str | bytes, *,
                         tenant: str, proposal_id: str, revision: int) -> VerifiedCorpus:
    """Verify a signer-authenticated, proposal-scoped full corpus snapshot.

    The JSON file contains {payload:{...}, hmac_sha256:<hex>}. The HMAC key must
    arrive out-of-band, not via Git. Reject any unusable or ambiguous record.
    External manifest reconciliation and authoritative completeness review
    remain mandatory before accepting the signer as a production source.
    """
    if not (tenant and proposal_id and type(revision) is int and revision >= 1):
        raise ApprovalReadinessError('explicit tenant, proposal ID and revision required')
    if not signing_key or len(signing_key) < 32:
        raise ApprovalReadinessError('nontrivial external snapshot signing key required')
    key = signing_key.encode('utf-8') if isinstance(signing_key, str) else signing_key
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 50 * 1024 * 1024:
        raise ApprovalReadinessError('regular bounded snapshot file required')
    raw = p.read_bytes()
    try:
        envelope = json.loads(raw)
        if set(envelope) != {'payload', 'hmac_sha256'}:
            raise ValueError('invalid envelope keys')
        body = envelope['payload']
        if not isinstance(body, dict):
            raise ValueError('invalid payload')
        digest = hmac.new(key, canonical_bytes(body), hashlib.sha256).hexdigest()
        if not isinstance(envelope['hmac_sha256'], str) or not hmac.compare_digest(digest, envelope['hmac_sha256']):
            raise ValueError('HMAC does not match')
        if set(body) != {'tenant','proposal_id','approved_revision','source_version','source_manifest_sha256','documents','complete'}:
            raise ValueError('corpus metadata incomplete or ambiguous')
        if body['tenant'] != tenant or body['proposal_id'] != proposal_id or body['approved_revision'] != revision:
            raise ValueError('tenant/proposal/revision does not match verified corpus')
        if body['complete'] is not True or not isinstance(body['source_version'], str) or not body['source_version']:
            raise ValueError('complete source version evidence required')
        source_digest = body['source_manifest_sha256']
        if not isinstance(source_digest, str) or len(source_digest) != 64 or any(c not in '0123456789abcdef' for c in source_digest):
            raise ValueError('source manifest SHA-256 invalid')
        docs = body['documents']
        if not isinstance(docs, list) or not docs:
            raise ValueError('complete corpus must be a nonempty list')
        seen = set()
        for doc in docs:
            if not isinstance(doc, dict) or not isinstance(doc.get('chunk_id'), str) or not doc['chunk_id']:
                raise ValueError('document missing stable chunk ID')
            if doc.get('tenant_id') != tenant or not isinstance(doc.get('text'), str):
                raise ValueError('cross-tenant document or missing document text')
            if doc['chunk_id'] in seen:
                raise ValueError('duplicate chunk ID')
            seen.add(doc['chunk_id'])
        return VerifiedCorpus(tenant, proposal_id, revision, body['source_version'], source_digest,
                              docs, hashlib.sha256(raw).hexdigest())
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, OverflowError) as ex:
        raise ApprovalReadinessError('trusted corpus rejected: ' + str(ex)) from ex


def queue_from_reviewed_patch(*, sessions, patch: Any, actor: Any,
                              snapshot_path: str | Path, signing_key: str | bytes) -> str:
    """Strict adapter to Wave 1.9 `queue_verified_approval`.

    Caller must already have authenticated/authorized the actor and loaded the
    patch from the persisted layer. No default tenant, guessed revision, or
    synthetic source corpus is allowed. Existing Alembic tables must exist.
    """
    provenance = getattr(patch, 'provenance', None) or {}
    if not isinstance(provenance, dict):
        raise ApprovalReadinessError('persisted proposal provenance required')
    proposer = provenance.get('proposer_username') or provenance.get('actor_id')
    reviewer = provenance.get('approver_username')
    actor_id = getattr(actor, 'username', None)
    status = getattr(patch, 'status', None)
    status = getattr(status, 'value', status)
    if str(status).upper() != 'APPROVED':
        raise ApprovalReadinessError('must have a persisted APPROVED state')
    if not proposer or not reviewer or proposer == reviewer or not actor_id or actor_id == proposer:
        raise ApprovalReadinessError('persisted independent approval and authorized promoter required')
    # CorrectionPatch currently has no tenant_id dataclass field. Accept only
    # an explicit persisted provenance tenant; never guess 'default'.
    tenant = getattr(patch, 'tenant_id', None) or provenance.get('tenant_id')
    proposal_id = getattr(patch, 'patch_id', None)
    version = getattr(patch, 'version', None)
    entity = getattr(patch, 'entity_id', None)
    attribute = getattr(patch, 'attribute', None)
    corrected_value = getattr(patch, 'corrected_value', None)
    if not tenant or not proposal_id or not entity or not attribute or type(version) is not int or version < 1:
        raise ApprovalReadinessError('persisted tenant, identity and positive approved revision required')
    if corrected_value is None:
        raise ApprovalReadinessError('persisted corrected value unavailable')
    verified = load_verified_corpus(snapshot_path, signing_key, tenant=tenant,
                                   proposal_id=proposal_id, revision=version)
    proposal = ApprovedProposal(proposal_id=proposal_id, tenant=tenant, revision=version,
                                proposer_id=proposer, reviewer_id=reviewer, status='APPROVED',
                                entity_id=entity, attribute=attribute, proposed_value=corrected_value)
    # Journal.submit uses the repository's existing transaction, idempotency and
    # the Alembic 012 schema. It DOES NOT create tables or fake a verified receipt.
    return queue_verified_approval(Journal(sessions), proposal, verified.documents)


def queue_from_environment(*, sessions, patch: Any, actor: Any) -> str:
    """Explicit opt-in for a server-side signed corpus; no HTTP source override."""
    path = os.environ.get('AMC_PUBLICATION_CORPUS_SNAPSHOT')
    key = os.environ.get('AMC_PUBLICATION_CORPUS_SIGNING_KEY')
    if not path or not key:
        raise ApprovalReadinessError('trusted publication corpus source not configured')
    return queue_from_reviewed_patch(sessions=sessions, patch=patch, actor=actor,
                                     snapshot_path=path, signing_key=key)
