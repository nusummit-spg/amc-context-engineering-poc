"""Read-only post-install source audit; never claims live-system or UAT PASS.

Designed to run on the exact feature branch SHA *after* the source-locked edits
have been applied. Missing markers, migration, or source path fails closed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REQUIRED={
 'backend/amc_publication/journal.py':['W28_ACTIVE_RECEIPT_AUTHORITY','bind_published(','restore_after_rollback('],
 'backend/app/vector/client.py':['W28_VERIFIED_READ_CUTOVER','legacy FAISS read forbidden','create_verified_vector_store'],
 'backend/app/retrieval/orchestrator.py':['W28_ORCHESTRATOR_AUTHORITY','unverified fast-path disabled','cached_entry = (cache.lookup'],
 'backend/app/api/routes/query.py':['W28_TRADITIONAL_TENANT_SCOPE','current_user.tenant_id'],
 'backend/app/main.py':['W27_PUBLICATION_STATUS_ROUTER'],
 'backend/amc_publication/status_route.py':['CurrentUser'],
 'backend/alembic/versions/013_active_receipt_authority_v28.py':['down_revision','publication_active_authority_v28'],
 'backend/amc_publication/serving28.py':['ActiveReceiptResolver','current_binding'],
 'backend/amc_publication/vector_bridge28.py':['VerifiedVectorBridge','verified_mode'],
}


def inspect(repo:Path):
    repo=repo.resolve()
    failures=[];inventory={}
    if not (repo/'.git').is_dir():failures.append('NOT_A_GIT_CHECKOUT')
    for rel,markers in REQUIRED.items():
        file=repo/rel
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(repo):
            failures.append('MISSING_OR_UNSAFE:'+rel)
            continue
        data=file.read_bytes()
        text=data.decode('utf-8',errors='replace')
        absent=[m for m in markers if m not in text]
        if absent:failures.append('MISSING_MARKERS:'+rel+':'+','.join(absent))
        inventory[rel]=hashlib.sha256(data).hexdigest()
    sha=None
    if (repo/'.git').exists():
        cp=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True)
        if cp.returncode==0:sha=cp.stdout.strip()
        else:failures.append('UNREADABLE_GIT_HEAD')
        state=subprocess.run(['git','status','--porcelain'],cwd=repo,capture_output=True,text=True)
        if state.returncode or state.stdout.strip():failures.append('UNCOMMITTED_CHANGES_OR_UNREADABLE_STATUS')
    return {'repository_sha':sha,'source_audit':'PASS' if not failures else 'BLOCKED',
            'release_gate':'BLOCKED','live_neo4j':'NOT_RUN','live_faiss':'NOT_RUN',
            'postgresql_concurrency':'NOT_RUN','windows_ci':'NOT_RUN','uat':'NOT_RUN',
            'failures':failures,'file_sha256':inventory}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True,type=Path)
    x=ap.parse_args();r=inspect(x.repo);print(json.dumps(r,indent=2))
    return 0 if r['source_audit']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
