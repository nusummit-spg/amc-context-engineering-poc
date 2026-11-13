"""Build a deterministic, independently reviewable catalog from canonical export.

Does not sign the catalog or infer that an arbitrary export is complete. The
source export's canonical completeness and tenant scoping must be established
by ingestion stewardship before the hash is used for publication admission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from amc_publication.catalog26 import inventory_bytes, CatalogMismatch


def build(*, source_export: str | Path, destination: str | Path,
          expected_tenant: str, expected_version: str, expected_count: int,
          apply: bool = False) -> dict:
    p=Path(source_export); dest=Path(destination)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>50*1024*1024:
        raise CatalogMismatch('regular bounded canonical export required')
    if dest.exists() or dest.is_symlink():
        raise FileExistsError('catalog output exists; refuse overwrite')
    raw=p.read_bytes()
    try:
        data=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as ex:
        raise CatalogMismatch('source export JSON invalid') from ex
    if not isinstance(data,dict) or set(data)!={'tenant','source_version','canonical_document_count','documents'}:
        raise CatalogMismatch('canonical export shape unknown')
    docs=data['documents']; n=data['canonical_document_count']
    if (type(expected_count) is not int or expected_count < 1 or
        type(n) is not int or n!=expected_count or
        not isinstance(docs,list) or len(docs)!=expected_count):
        raise CatalogMismatch('count differs from externally required canonical count')
    if data['tenant']!=expected_tenant or data['source_version']!=expected_version:
        raise CatalogMismatch('canonical export tenant/version mismatch')
    result=inventory_bytes(expected_tenant,expected_version,docs)
    sha=hashlib.sha256(result).hexdigest()
    if apply:
        dest.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation; a file appearing during output validation is not overwritten.
        with dest.open('xb') as f:
            f.write(result)
            f.flush()
            import os
            os.fsync(f.fileno())
    return {'status':'CREATED_REQUIRES_CANONICAL_SOURCE_ATTESTATION' if apply else 'DRY_RUN',
            'source_sha256':hashlib.sha256(raw).hexdigest(),
            'source_version':expected_version,'tenant':expected_tenant,
            'count':len(docs),'catalog_sha256':sha,'output':str(dest),
            'operator_required':'confirm source export represents all active canonical chunks'}


def main(argv=None):
    p=argparse.ArgumentParser(description='Build deterministic tenant catalog from independently reviewed canonical export')
    p.add_argument('--source-export',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--version',required=True)
    p.add_argument('--count',required=True,type=int)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args(argv)
    print(json.dumps(build(source_export=a.source_export,destination=a.output,
        expected_tenant=a.tenant,expected_version=a.version,expected_count=a.count,
        apply=a.apply),indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
