"""One-command local AMC Wave 2.9 branch preparation.

Wave2.6 COMPOSES Wave2.5 and Wave2.6 from original source; do NOT apply
Wave2.5 separately before running it. This script never commits, pushes,
runs migrations, deploys, or authorizes UAT. User must inspect git diff.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

BASE='2c0415c4d23a3338428c8314c869299aa0ab771f'
BRANCH='feature/amc-release-candidate-hardening'
STEPS=[
 ('install', ['install_wave29.py','--repo','{repo}','--apply']),
 ('combined_25_26', ['-m','tools.amc_release.publication_patch26_cli','--repo','{repo}','--apply']),
 ('route_27', ['-m','tools.amc_release.app_wiring27_cli','--repo','{repo}','--apply']),
 ('authority_28', ['-m','tools.amc_release.active_cutover28','--repo','{repo}','--apply']),
 ('ingress_29', ['-m','tools.amc_release.ingest_cutover29','--repo','{repo}','--apply']),
 ('compile', ['-m','compileall','-q','backend/amc_publication','backend/app/vector','backend/app/ingestion','backend/app/api']),
 ('tests_29', ['-m','pytest','-q','tools/amc_release/tests_wave29']),
]


def run(repo:Path, bundle:Path, *, apply:bool=False, branch:str=BRANCH, python_bin:str=sys.executable) -> dict:
    repo=Path(repo).resolve(); bundle=Path(bundle).resolve()
    if not (repo/'.git').is_dir() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('requires real Git checkout')
    if not (bundle/'install_wave29.py').is_file():
        raise ValueError('cumulative Wave2.9 source bundle required')
    def git(*args):
        return subprocess.check_output(['git','-C',str(repo),*args],text=True,stderr=subprocess.STDOUT).strip()
    current=git('rev-parse','HEAD')
    if current!=BASE:
        raise ValueError('repository commit differs from reviewed base; re-audit before patching')
    if git('status','--porcelain'):
        raise ValueError('uncommitted changes present; refuse branch integration')
    name=git('branch','--show-current')
    if not isinstance(branch,str) or not branch.startswith('feature/') or branch==name:
        raise ValueError('new feature branch required')
    if branch in git('branch','--format=%(refname:short)').splitlines():
        raise ValueError('feature branch already exists; refuse overwrite')
    from install_wave29 import install
    additive=install(bundle,repo,apply=False)
    if not apply:
        return {'status':'DRY_RUN_BASE_VERIFIED','base':current,'current_branch':name,
                'target_branch':branch,'additive':additive,
                'warning':'subsequent source patches require sequential transformation; inspect final diff'}
    git('switch','-c',branch)
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join(filter(None,[str(repo),str(repo/'backend'),env.get('PYTHONPATH','')]))
    completed=[]
    for label,args in STEPS:
        cmd=[python_bin]+[item.replace('{repo}',str(repo)) for item in args]
        if label=='install':
            cmd=[python_bin,str(bundle/'install_wave29.py'),'--repo',str(repo),'--apply']
        result=subprocess.run(cmd,cwd=repo,env=env,text=True,capture_output=True)
        if result.returncode!=0:
            return {'status':'BLOCKED_PARTIAL_LOCAL_BRANCH','branch':branch,
                    'failed_step':label,'passed_steps':completed,'exit_code':result.returncode,
                    'stdout_tail':result.stdout[-1500:],'stderr_tail':result.stderr[-1500:],
                    'manual_action':'Review git diff/backups; do not publish or merge'}
        completed.append(label)
    return {'status':'LOCAL_BRANCH_UNCOMMITTED_TESTED_WAVE29_ONLY','branch':branch,
            'base':current,'steps':completed,
            'manual_action':'Review git diff; run full backend and live qualification before UAT'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',required=True,type=Path)
    ap.add_argument('--bundle',default=Path(__file__).resolve().parents[2],type=Path)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--branch',default=BRANCH)
    a=ap.parse_args()
    try:
        print(json.dumps(run(a.repo,a.bundle,apply=a.apply,branch=a.branch),indent=2))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as ex:
        print(json.dumps({'status':'BLOCK','reason':str(ex)}))
        return 2
if __name__=='__main__':raise SystemExit(main())
