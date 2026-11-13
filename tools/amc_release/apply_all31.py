"""Wave 3.1 branch bootstrap: one preflight then Wave3.0 + 3.1.

A partial failure leaves the local branch for manual inspection. This tool
never pushes, commits, deploys, runs DDL or authorizes UAT.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from .apply_all30 import run as run30
from .preflight30 import preflight, Preflight30Error
from .publication_patch26 import build_patch
from .governance_guard31 import transform, patch as guard_patch
from .apply_all29 import BRANCH


def preflight31(repo:Path,bundle:Path):
    repo=Path(repo).resolve();bundle=Path(bundle).resolve()
    report=preflight(repo,bundle)
    # Rehearse our post-W26 endpoint guard against the exact reviewed bytes.
    from tempfile import TemporaryDirectory
    import shutil
    with TemporaryDirectory(prefix='amc-guard31-review-') as t:
        shadow=Path(t)
        (shadow/'.git').mkdir()
        from .publication_patch26 import REVIEWED_GIT_BLOBS
        for rel in REVIEWED_GIT_BLOBS:
            src=repo/rel
            dst=shadow/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dst)
        after=build_patch(shadow)['backend/app/api/routes/governance.py']['new']
        transform(after)
    import install_wave31
    additive=install_wave31.install(bundle,repo,apply=False)
    return {**report,'scope_lock_migration':'014_required',
            'governance_guard':'SOURCE_PATCH_REHEARSED','wave31_additions':additive['additions']}


def run(repo:Path,bundle:Path,*,apply:bool=False):
    repo=Path(repo).resolve();bundle=Path(bundle).resolve()
    before=preflight31(repo,bundle)
    if not apply:return {**before,'branch_created':False}
    first=run30(repo,bundle,apply=True)
    if first.get('status')!='UNCOMMITTED_LOCAL_BRANCH_TESTED_OFFLINE_ONLY':
        return {'status':'BLOCKED_PARTIAL_BRANCH','stage':'wave3.0','details':first,'uat':'BLOCKED'}
    from install_wave31 import install
    additions=install(bundle,repo,apply=True)
    guard=guard_patch(repo,apply=True)
    # Run against the ACTUAL checked-out source and archived fixtures.
    test=subprocess.run([sys.executable,'-m','tools.amc_release.run_wave31_tests','--root',str(repo)],
                        cwd=repo,capture_output=True,text=True)
    if test.returncode:
        return {'status':'BLOCKED_PARTIAL_BRANCH','stage':'wave3.1 tests',
                'returncode':test.returncode,'stdout_tail':test.stdout[-1000:],
                'stderr_tail':test.stderr[-1000:],'uat':'BLOCKED'}
    return {'status':'LOCAL_BRANCH_UNCOMMITTED_OFFLINE_TESTED_ONLY','branch':BRANCH,
            'verified_base':before['sha'],'additions':additions['status'],
            'guard':guard['status'],'test_summary':test.stdout[-1000:],
            'live_checks':'NOT_RUN','uat':'BLOCKED'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--apply',action='store_true')
    x=p.parse_args()
    try:
        result=run(x.repo,x.bundle,apply=x.apply)
        print(json.dumps(result,indent=2))
        return 0 if not result['status'].startswith('BLOCKED') else 2
    except (Preflight30Error,ValueError,FileExistsError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2

if __name__=='__main__':raise SystemExit(main())
