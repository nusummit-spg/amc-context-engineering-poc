"""W31: remove the last known direct-promotion bypass in verified serving mode.

Runs AFTER the Wave 2.5/2.6 patch. No blanket exception handler around
HTTPException: a deliberate 503 must never be converted into a 500.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from .publication_patch25 import SourceDrift, _once

RELATIVE='backend/app/api/routes/governance.py'
MARKER='W31_DISABLE_LEGACY_DIRECT_PROMOTE'
ANCHOR='''    require_approval_role(current_user)
    service = PromotionService(db=db)
'''
REPLACEMENT='''    require_approval_role(current_user)
    # W31_DISABLE_LEGACY_DIRECT_PROMOTE: direct Neo4j promotion has no v2
    # durable journal or active-receipt binding and must be unreachable.
    from amc_publication.vector_bridge28 import verified_mode
    if verified_mode() == 'enforce':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Legacy direct promotion disabled; use reviewed v2 publication',
        )
    service = PromotionService(db=db)
'''


def transform(src: str) -> str:
    if MARKER in src:
        raise SourceDrift('Wave 3.1 governance guard already present')
    start=src.find('async def promote_approved_proposals(')
    end=src.find('@router.post("/promote/{patch_id}"',start)
    if start<0 or end<start:
        raise SourceDrift('reviewed promotion endpoints missing or reordered')
    sub=src[start:end]
    if sub.count(ANCHOR)!=1 or src.count(ANCHOR)!=1:
        raise SourceDrift('legacy promotion call changed; re-audit before cutover')
    patched=_once(sub, ANCHOR, REPLACEMENT, 'disable unsafe direct promotion')
    result=src[:start]+patched+src[end:]
    compile(result,RELATIVE,'exec')
    return result


def patch(repo: Path, *,apply:bool=False) -> dict:
    root=Path(repo).resolve()
    file=root/RELATIVE
    if not (root/'.git').is_dir() or not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):
        raise SourceDrift('safe full AMC checkout required')
    before=file.read_bytes()
    after=transform(before.decode('utf-8')).encode('utf-8')
    result={'status':'DRY_RUN','path':RELATIVE,
        'before_sha256':hashlib.sha256(before).hexdigest(),
        'after_sha256':hashlib.sha256(after).hexdigest(),
        'blocks_legacy_promotion_under_verified_mode':True}
    if not apply:return result
    backup=file.with_name(file.name+'.wave31.bak')
    if backup.exists() or backup.is_symlink():raise SourceDrift('backup collision, refusing write')
    if file.read_bytes()!=before:raise SourceDrift('concurrent source change')
    shutil.copy2(file,backup)
    try:file.write_bytes(after)
    except BaseException:
        shutil.copy2(backup,file)
        raise
    return {**result,'status':'PATCHED_REVIEW_REQUIRED'}


def main():
    args=argparse.ArgumentParser()
    args.add_argument('--repo',type=Path,required=True)
    args.add_argument('--apply',action='store_true')
    opts=args.parse_args()
    try:
        print(json.dumps(patch(opts.repo,apply=opts.apply),indent=2))
        return 0
    except (ValueError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','reason':str(ex)}))
        return 2

if __name__=='__main__':raise SystemExit(main())
