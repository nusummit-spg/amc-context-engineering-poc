"""Wave 3.0 full branch integration. Requires preflight before first branch write.

Never commits/pushes, never runs migrations, never deploys, never marks UAT ready.
The legacy chain remains source-locked; any failure returns BLOCKED with branch
left for explicit manual review, not an unsafe automatic reset.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from .preflight30 import preflight, Preflight30Error
from .apply_all29 import run as run29, BRANCH
from .assurance30 import patch as patch_assurance30
from . import preflight30

def run(repo:Path,bundle:Path,*,apply:bool=False):
    repo=Path(repo).resolve();bundle=Path(bundle).resolve()
    before=preflight(repo,bundle)
    if not apply:return before
    # Phase 1: create a local branch and execute reviewed Waves 2.3–2.9.
    result=run29(repo,bundle,apply=True)
    if result.get('status') != 'LOCAL_BRANCH_UNCOMMITTED_TESTED_WAVE29_ONLY':
        return {'status':'BLOCKED_PARTIAL_BRANCH','first_stage':result,'release':'BLOCKED'}
    # Phase 2: add Wave 3.0 source/test files and harden the original CI YAML.
    from install_wave30 import install
    addition=install(bundle,repo,apply=True)
    assurance=patch_assurance30(repo,apply=True)
    # Phase 3: run actual checked-out W30 regressions, not only package fixtures.
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join(filter(None,[str(repo/'backend'),str(repo),env.get('PYTHONPATH','')]))
    commands=[
        [sys.executable,'-m','compileall','-q','backend/amc_publication','backend/app/vector',
         'backend/app/ingestion','backend/app/api'],
        [sys.executable,'-m','pytest','-q','tools/amc_release/tests_wave28',
         'tools/amc_release/tests_wave29','tools/amc_release/tests_wave30'],
    ]
    check=[]
    for cmd in commands:
        completed=subprocess.run(cmd,cwd=repo,env=env,text=True,capture_output=True)
        check.append({'command':cmd,'exit_code':completed.returncode,
                      'stdout_tail':completed.stdout[-800:],'stderr_tail':completed.stderr[-800:]})
        if completed.returncode:
            return {'status':'BLOCKED_PARTIAL_BRANCH','branch':BRANCH,
                    'phase':'Wave3.0 qualification','test_evidence':check,
                    'release':'BLOCKED', 'manual_action':'Inspect branch diff and failures; do not push to UAT'}
    return {'status':'UNCOMMITTED_LOCAL_BRANCH_TESTED_OFFLINE_ONLY',
        'branch':BRANCH,'reviewed_base':before['sha'],
        'installed':addition['status'],'assurance':assurance['status'],
        'test_evidence':check,'release':'BLOCKED',
        'missing':'full backend PostgreSQL, Neo4j, FAISS, Windows CI, staging and independent UAT'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument('--apply',action='store_true')
    opts=ap.parse_args()
    try:
        print(json.dumps(run(opts.repo,opts.bundle,apply=opts.apply),indent=2))
        return 0
    except (Preflight30Error,ValueError,FileExistsError,OSError,subprocess.CalledProcessError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)}))
        return 2
if __name__=='__main__':raise SystemExit(main())
