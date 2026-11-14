"""Wave 2.9: isolated staging boundary for unapproved ingestion.

This module NEVER mutates Neo4j, FAISS, publication pointers, or SQL journal.
It records a content-addressed quarantine candidate for an independent canonical
inventory review. It is NOT a replacement for approved full-corpus publication.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .types import canonical_bytes
from .serving27 import ServingDenied


class IngestionQuarantineError(ValueError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _strict_documents(tenant: str, documents: list[dict]) -> list[dict]:
    if not isinstance(tenant, str) or not tenant.strip() or tenant != tenant.strip():
        raise IngestionQuarantineError('explicit canonical tenant required')
    if not isinstance(documents, list) or not documents or len(documents) > 100_000:
        raise IngestionQuarantineError('nonempty bounded staged documents required')
    ids: set[str] = set()
    results = []
    for doc in documents:
        if not isinstance(doc, dict):
            raise IngestionQuarantineError('document must be an object')
        chunk_id = doc.get('chunk_id')
        if (doc.get('tenant_id') != tenant or not isinstance(chunk_id, str) or not chunk_id
            or not isinstance(doc.get('text'), str) or not doc['text'].strip()
            or not isinstance(doc.get('source_version'), str) or not doc['source_version'].strip()
            or not _sha_hex(doc.get('source_sha256'))):
            raise IngestionQuarantineError('tenant, chunk, source version or raw-source digest missing')
        if chunk_id in ids:
            raise IngestionQuarantineError('duplicate chunk ID')
        ids.add(chunk_id)
        results.append(dict(doc))
    return sorted(results, key=lambda d:d['chunk_id'])


class ImmutableIngestionQuarantine29:
    """Content-addressed candidate store; no writable activation API."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if self.root.is_symlink():
            raise IngestionQuarantineError('root must not be a symlink')
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir() or self.root.is_symlink():
            raise IngestionQuarantineError('unsafe quarantine root')

    def _path(self, digest: str) -> Path:
        if not _sha_hex(digest):
            raise IngestionQuarantineError('invalid staging digest')
        return self.root / digest[:2] / (digest + '.json')

    def stage(self, *, tenant: str, source_version: str, batch_id: str,
              submitted_by: str, documents: list[dict]) -> dict:
        if not all(isinstance(v,str) and v.strip() and len(v) <= 256 for v in
                   (source_version, batch_id, submitted_by)):
            raise IngestionQuarantineError('source version, batch and actor required')
        docs = _strict_documents(tenant, documents)
        if any(d['source_version'] != source_version for d in docs):
            raise IngestionQuarantineError('mixed source version')
        payload = {'schema':'amc-ingestion-quarantine-v29', 'tenant':tenant,
                   'source_version':source_version, 'batch_id':batch_id,
                   'submitted_by':submitted_by, 'documents':docs,
                   'publication_authorized':False, 'complete_corpus':False}
        raw = canonical_bytes(payload)
        if len(raw) > 50*1024*1024:
            raise IngestionQuarantineError('quarantine candidate over 50 MiB')
        digest = _sha256_bytes(raw)
        target = self._path(digest)
        parent = target.parent
        if parent.is_symlink():
            raise IngestionQuarantineError('unsafe quarantine shard')
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink():
            raise IngestionQuarantineError('unsafe quarantine shard')
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=parent, prefix='.candidate-', suffix='.tmp',
                                             delete=False) as f:
                tmp = Path(f.name)
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            # Link installs only when absent; no writer can overwrite a sealed candidate.
            try:
                os.link(tmp, target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != raw:
                    raise IngestionQuarantineError('candidate digest collision or tampered record')
            if target.is_symlink() or target.read_bytes() != raw:
                raise IngestionQuarantineError('candidate not durable or tampered')
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        return {'candidate_sha256':digest, 'document_count':len(docs),
                'source_version':source_version, 'tenant':tenant,
                'state':'QUARANTINED_UNAPPROVED', 'publication_authorized':False}

    def verify(self, digest: str, *, tenant: str) -> dict:
        target = self._path(digest)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 50*1024*1024:
            raise IngestionQuarantineError('missing or unsafe candidate')
        raw=target.read_bytes()
        if _sha256_bytes(raw) != digest:
            raise IngestionQuarantineError('quarantine digest mismatch')
        try:
            data=json.loads(raw)
        except (ValueError, UnicodeDecodeError) as ex:
            raise IngestionQuarantineError('invalid quarantine document') from ex
        if not isinstance(data,dict) or set(data) != {
            'schema','tenant','source_version','batch_id','submitted_by','documents',
            'publication_authorized','complete_corpus'}:
            raise IngestionQuarantineError('unknown quarantine schema')
        if (data['schema'] != 'amc-ingestion-quarantine-v29' or data['tenant'] != tenant
            or data['publication_authorized'] is not False or data['complete_corpus'] is not False
            or not isinstance(data['source_version'],str)
            or not isinstance(data['submitted_by'],str)
            or not isinstance(data['batch_id'],str)):
            raise IngestionQuarantineError('candidate incorrectly claims publication readiness')
        _strict_documents(tenant,data['documents'])
        if canonical_bytes(data) != raw:
            raise IngestionQuarantineError('non-canonical quarantine data')
        return data


class DenyDirectVectorMutation29:
    """Object placed on ingestion pipeline in verified mode, never a write fallback."""

    async def index_chunks(self, *args, **kwargs):
        raise ServingDenied('legacy direct vector ingestion disabled; use signed reviewed corpus publication')

    async def add_documents(self,*args,**kwargs):
        raise ServingDenied('legacy direct vector ingestion disabled')

    async def add(self,*args,**kwargs):
        raise ServingDenied('legacy direct vector ingestion disabled')

    def __getattr__(self, name):
        raise ServingDenied(f'ingestion port does not expose unreviewed operation: {name}')
