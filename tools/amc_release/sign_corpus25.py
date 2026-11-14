"""Operator-only signer for a *reviewed* full tenant corpus snapshot.

Not an automatic source catalog assembler: it signs an exact, already-reviewed
payload. Completeness/source-manifest correlation requires independent evidence.
No generated secrets; the signing key must be supplied out of band.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def sign(*, payload_path: str | Path, output_path: str | Path, key: str | bytes,
         expected_manifest_sha256: str, apply: bool = False) -> dict:
    from amc_publication.approval_adapter import load_verified_corpus, ApprovalReadinessError
    from amc_publication.types import canonical_bytes
    src=Path(payload_path);dest=Path(output_path)
    if not src.is_file() or src.is_symlink():
        raise ValueError('regular reviewed input JSON required')
    if not isinstance(key,(bytes,str)) or len(key)<32:
        raise ValueError('out-of-band signing key (at least 32 bytes) required')
    if dest.exists() or dest.is_symlink():
        raise FileExistsError('signature output already exists; overwrite refused')
    raw=src.read_bytes()
    if len(raw)>50*1024*1024:
        raise ValueError('reviewed snapshot too large')
    try: body=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as e: raise ValueError('reviewed input is not valid JSON') from e
    if not isinstance(body,dict):
        raise ValueError('reviewed input must be an object')
    digest=body.get('source_manifest_sha256')
    if digest != expected_manifest_sha256 or not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('operator-reviewed external manifest SHA mismatch')
    if not apply:
        return {'status':'DRY_RUN','document_count':len(body.get('documents',[])) if isinstance(body.get('documents'),list) else 0,
                'source_manifest_sha256':digest,'output':str(dest)}
    digest_key=key.encode('utf-8') if isinstance(key,str) else key
    mac=hmac.new(digest_key,canonical_bytes(body),hashlib.sha256).hexdigest()
    serialized=canonical_bytes({'payload':body,'hmac_sha256':mac})
    dest.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile('wb',dir=dest.parent,prefix='.amc-corpus-',delete=False) as temp:
        temp.write(serialized)
        temp.flush();os.fsync(temp.fileno())
        tmp=Path(temp.name)
    try:
        # Validate the signature and schema before installing the file.
        try:
            value=load_verified_corpus(tmp,key,tenant=body.get('tenant'),proposal_id=body.get('proposal_id'),revision=body.get('approved_revision'))
        except ApprovalReadinessError as exc:
            raise ValueError('reviewed payload does not satisfy signed publication contract') from exc
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('output appeared before atomic write')
        # Exclusive hardlink avoids silent overwrite on Unix; Windows fallback
        # can use O_EXCL (without changing the existing destination).
        try:
            os.link(tmp,dest,follow_symlinks=False)
        except (AttributeError,NotImplementedError,OSError) as err:
            # Windows / restricted FS: create destination exclusively.
            fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            try:
                with os.fdopen(fd,'wb') as out:
                    out.write(serialized);out.flush();os.fsync(out.fileno())
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
        try: dest.chmod(0o600)
        except OSError: pass
        return {'status':'SIGNED_REQUIRES_EXTERNAL_COMPLETENESS_REVIEW',
                'tenant':value.tenant,'proposal_id':value.proposal_id,'approved_revision':value.revision,
                'document_count':len(value.documents),'source_manifest_sha256':digest,
                'snapshot_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'output':str(dest)}
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None):
    ap=argparse.ArgumentParser(description='Sign a separately-reviewed complete corpus; no source data auto-discovery')
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--manifest-sha256',required=True)
    ap.add_argument('--apply',action='store_true')
    a=ap.parse_args(argv)
    key=os.environ.get('AMC_PUBLICATION_CORPUS_SIGNING_KEY')
    if not key:
        ap.error('AMC_PUBLICATION_CORPUS_SIGNING_KEY must be configured outside Git')
    out=sign(payload_path=a.input,output_path=a.output,key=key,expected_manifest_sha256=a.manifest_sha256,apply=a.apply)
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
