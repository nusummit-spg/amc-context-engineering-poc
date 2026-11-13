"""Wave 2.6 source-catalog attestation for signed full-vector snapshots.

A complete snapshot HMAC is necessary but not sufficient: it must also agree
exactly with a separately constructed canonical ingestion inventory. This
module verifies bytes, tenant, source version, chunk IDs and content hashes.
The inventory's *authority* is an operational trust boundary; it must be
built from the actual canonical catalog by a separate trusted process.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
from .types import canonical_bytes, Conflict


class CatalogMismatch(Conflict):
    pass


def _hex(digest: str) -> bool:
    return (isinstance(digest, str) and len(digest) == 64 and
            all(c in '0123456789abcdef' for c in digest))


def document_sha256(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def inventory_bytes(tenant: str, source_version: str, documents: list[dict]) -> bytes:
    """Construct deterministic inventory *only* from trusted canonical rows.

    Creating this inventory from a candidate snapshot does not prove that the
    candidate includes everything. Operators must independently reconcile the
    canonical source's row IDs/count first.
    """
    if not (isinstance(tenant, str) and tenant and isinstance(source_version, str) and source_version):
        raise CatalogMismatch('nonempty tenant and source version required')
    if not isinstance(documents,list) or not documents:
        raise CatalogMismatch('nonempty canonical documents required')
    chunks=[]; ids=set()
    for d in documents:
        if not isinstance(d,dict) or d.get('tenant_id')!=tenant or not isinstance(d.get('chunk_id'),str) or not d['chunk_id'] or not isinstance(d.get('text'),str):
            raise CatalogMismatch('invalid or cross-tenant catalog document')
        if d['chunk_id'] in ids:
            raise CatalogMismatch('duplicate canonical chunk ID')
        ids.add(d['chunk_id'])
        chunks.append({'chunk_id':d['chunk_id'],'document_sha256':document_sha256(d)})
    chunks.sort(key=lambda x:x['chunk_id'])
    return canonical_bytes({'schema':'amc-source-catalog-v1','tenant':tenant,
                            'source_version':source_version,'declared_count':len(chunks),
                            'chunks':chunks,'complete':True})


def verify_catalog(verified, catalog_path: str | Path) -> dict:
    """Compare a verified signed corpus with exact independently stored catalog.

    `verified` is the VerifiedCorpus returned by load_verified_corpus() and
    contains its independently authenticated source_manifest_sha256.
    """
    p=Path(catalog_path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>50*1024*1024:
        raise CatalogMismatch('regular bounded catalog file required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=verified.source_manifest_sha256:
        raise CatalogMismatch('catalog bytes digest differs from authenticated corpus anchor')
    try:
        catalog=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as e:
        raise CatalogMismatch('catalog JSON invalid') from e
    if not isinstance(catalog,dict) or set(catalog)!={'schema','tenant','source_version','declared_count','chunks','complete'}:
        raise CatalogMismatch('catalog shape is unknown')
    if (catalog['schema']!='amc-source-catalog-v1' or catalog['complete'] is not True or
        catalog['tenant']!=verified.tenant or catalog['source_version']!=verified.source_version):
        raise CatalogMismatch('catalog tenant/version/complete evidence mismatch')
    documents=verified.documents
    expected=inventory_bytes(verified.tenant,verified.source_version,documents)
    if raw!=expected:
        raise CatalogMismatch('catalog chunk identity/content differs from signed corpus')
    if type(catalog['declared_count']) is not int or catalog['declared_count']!=len(documents):
        raise CatalogMismatch('catalog row count differs from signed corpus')
    return {'status':'PASS_CATALOG_EQUALS_SIGNED_SNAPSHOT',
            'tenant':verified.tenant,'version':verified.source_version,
            'chunks':len(documents),'catalog_sha256':verified.source_manifest_sha256,
            'warning':'Authority/completeness of original canonical inventory requires independent stewardship'}
