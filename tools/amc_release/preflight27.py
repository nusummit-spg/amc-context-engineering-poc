"""Read-only branch-ready AMC source validation. Does not grant UAT approval.

Uses actual Git data rather than a source filename or operator-supplied success
flag; records missing integrations as BLOCK. No mutation or network access.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import json
import re
import ast

REVIEWED_BASE='2c0415c4d23a3338428c8314c869299aa0ab771f'
FILES={
 'backend/amc_publication/worker.py':'W26_DURABLE_GRAPH_PREIMAGE',
 'backend/amc_publication/journal.py':'W26_POINTER_ROW_LOCK',
 'backend/app/api/routes/governance.py':'W26_ACCEPTED_JSON',
 'backend/amc_publication/faiss_artifacts.py':'W26_FAISS_WINDOWS_PORTABLE',
 'backend/amc_publication/status_route.py':'W26_TENANT_SCOPED_STATUS',
 'backend/app/main.py':'W27_PUBLICATION_STATUS_ROUTER',
 'backend/amc_publication/serving27.py':'class VerifiedGenerationResolver',
 'backend/amc_publication/faiss_reader27.py':'class VerifiedFaissRetriever',
 'backend/amc_publication/reconcile27.py':'def inspect(',
}


def _git(repo:Path,*args:str)->str:
    p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,timeout=12)
    if p.returncode!=0:raise RuntimeError('Git inspection unavailable: '+' '.join(args))
    return p.stdout.strip()


def assess(repo:Path,*,expected_base:str=REVIEWED_BASE)->dict:
    root=Path(repo).resolve()
    fail=[]
    out={'schema':'amc-wave27-source-preflight-v1','reviewed_base':expected_base,'checks':{},'uat':'BLOCK'}
    if not (root/'.git').exists():
        return {**out,'status':'BLOCK','reasons':['NOT_A_GIT_CHECKOUT']}
    try:
        sha=_git(root,'rev-parse','HEAD')
        branch=_git(root,'branch','--show-current')
    except (OSError,RuntimeError):
        return {**out,'status':'BLOCK','reasons':['GIT_STATE_UNREADABLE']}
    out.update({'head':sha,'branch':branch})
    if not re.fullmatch('[0-9a-f]{40}',sha):fail.append('INVALID_COMMIT_SHA')
    if branch in ('','main','master','amc-dev'):
        fail.append('REVIEW_FEATURE_BRANCH_REQUIRED')
    if not re.fullmatch('[0-9a-f]{40}',expected_base):
        fail.append('INVALID_REVIEWED_BASE')
    try:
        if _git(root,'cat-file','-t',expected_base)!='commit':
            fail.append('BASE_COMMIT_NOT_FOUND')
        elif _git(root,'merge-base','--is-ancestor',expected_base,'HEAD')!='':
            # When ancestor, this command prints nothing and exits zero.
            pass
    except (OSError,RuntimeError):
        fail.append('REVIEWED_BASE_NOT_ANCESTOR_OF_HEAD')
    # Never parse Git porcelain output into false success; ensure no accidental
    # backup/secret/source-corpus files are among the changes to be committed.
    try:
        changes=_git(root,'status','--porcelain','--untracked-files=all').splitlines()
    except (OSError,RuntimeError):
        fail.append('GIT_STATUS_UNREADABLE');changes=[]
    forbidden=('wave25.bak','wave26.bak','wave27.bak','.env','signing_key','private_key','.pem','.uat-session.json','test_support/')
    for line in changes:
        file=line[3:] if len(line)>3 else line
        if any(x in file for x in forbidden):
            fail.append('SENSITIVE_OR_BACKUP_CHANGE_IN_WORKTREE')
            break
    out['checks']['changed_files']=len(changes)
    for rel,marker in FILES.items():
        file=root/rel
        status='MISSING'
        if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(root):
            text=file.read_text(encoding='utf-8')
            status='PRESENT' if marker in text else 'UNPATCHED'
            if status=='PRESENT' and file.suffix=='.py':
                try: ast.parse(text,filename=rel)
                except SyntaxError:status='INVALID_PYTHON'
        out['checks'][rel]=status
        if status!='PRESENT':fail.append('SOURCE_NOT_INTEGRATED:'+rel)
    # The release gate still requires external job, service and reviewer proofs.
    out['reasons']=sorted(set(fail))
    out['status']='SOURCE_REVIEW_REQUIRED' if not fail else 'BLOCK'
    out['external_requirements']=['EXACT_SHA_CI_NOT_VERIFIED','POSTGRES_NEO4J_FAISS_NOT_VERIFIED',
                                   'STAGING_BROWSER_SLO_CANARY_NOT_VERIFIED','INDEPENDENT_UAT_SIGNOFF_MISSING']
    return out


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Wave2.7 read-only integration preflight')
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--expected-base',default=REVIEWED_BASE)
    args=parser.parse_args(argv)
    result=assess(args.repo,expected_base=args.expected_base)
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='SOURCE_REVIEW_REQUIRED' else 2

if __name__=='__main__':raise SystemExit(main())
