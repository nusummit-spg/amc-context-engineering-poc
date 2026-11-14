"""Wave 2.6 production queue admission: signed snapshot AND canonical catalog.

Does not silently use an empty snapshot or a snapshot created by the caller.
The authenticated request's actor is from the application's JWT dependency.
"""
from __future__ import annotations

from pathlib import Path
import os
from .approval_adapter import ApprovalReadinessError, load_verified_corpus, queue_from_reviewed_patch
from .catalog26 import verify_catalog, CatalogMismatch


def queue_from_environment_26(*, sessions, patch, actor) -> str:
    path=os.getenv('AMC_PUBLICATION_CORPUS_SNAPSHOT')
    key=os.getenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY')
    catalog_path=os.getenv('AMC_PUBLICATION_SOURCE_CATALOG')
    if not path or not key or not catalog_path:
        raise ApprovalReadinessError('signed snapshot, key and independent source catalog are mandatory')
    prov=getattr(patch,'provenance',None) or {}
    if not isinstance(prov,dict):
        raise ApprovalReadinessError('persisted proposal provenance required')
    tenant=getattr(patch,'tenant_id',None) or prov.get('tenant_id')
    if not tenant:
        raise ApprovalReadinessError('explicit persisted tenant required')
    verified=load_verified_corpus(path,key,tenant=tenant,
                                proposal_id=getattr(patch,'patch_id',None),
                                revision=getattr(patch,'version',None))
    try:
        verify_catalog(verified,catalog_path)
    except CatalogMismatch as ex:
        raise ApprovalReadinessError('canonical source catalog reconciliation refused publication') from ex
    # Wave 2.5 validates actor/reviewer/identity and queues to the durable
    # journal. Re-reading the authenticated snapshot must still verify its HMAC.
    return queue_from_reviewed_patch(sessions=sessions,patch=patch,actor=actor,
                                     snapshot_path=path,signing_key=key)
