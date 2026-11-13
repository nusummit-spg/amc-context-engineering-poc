"""Wave 3.1 full-source presence audit. Read-only, never approves UAT."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .qualification30 import inspect as inspect30

CHECKS={
 'backend/amc_publication/active_authority28.py':['W31_SCOPE_CLAIM','class PublicationScopeClaim31'],
 'backend/alembic/versions/014_publication_scope_claim_v31.py':['014_publication_scope_claim_v31','013_active_receipt_authority_v28'],
 'backend/app/api/routes/governance.py':['W31_DISABLE_LEGACY_DIRECT_PROMOTE'],
 'backend/amc_publication/scope_audit31.py':['def audit_scope_claims('],
 'tools/amc_release/tests_wave31/test_scope_claim31.py':['test_second_journal_graph_preparation_cannot_mutate_same_tenant'],
 '.github/workflows/amc-wave31-durable-mutation.yml':['workflow_dispatch'],
}


def inspect(repo:Path) -> dict:
    root=Path(repo).resolve()
    base=inspect30(root)
    found={}
    for rel,needles in CHECKS.items():
        file=root/rel
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):
            found[rel]={'status':'BLOCKED','missing':needles}
            continue
        source=file.read_text(encoding='utf-8')
        missing=[x for x in needles if x not in source]
        if not missing and rel.endswith('.py'):
            try:compile(source,rel,'exec')
            except SyntaxError:missing=['COMPILE_FAILURE']
        found[rel]={'status':'PASS' if not missing else 'BLOCKED','missing':missing}
    blocked=[k for k,v in found.items() if v['status']!='PASS']
    return {'schema':'amc-wave31-qualification-v1',
            'status':'SOURCE_REVIEW_ONLY' if base['status']=='PASS_OFFLINE_SOURCE_ONLY' and not blocked else 'BLOCKED',
            'wave30_status':base['status'],'wave31_checks':found,'wave31_blockers':blocked,
            'live_postgresql':'NOT_RUN','live_graph_faiss':'NOT_RUN',
            'exact_sha_ci':'NOT_RUN','staging_canary':'NOT_RUN','uat':'BLOCKED'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--out',type=Path)
    x=p.parse_args()
    r=inspect(x.repo)
    if x.out:
        x.out.parent.mkdir(parents=True,exist_ok=True)
        x.out.write_text(json.dumps(r,indent=2),encoding='utf-8')
    print(json.dumps(r,indent=2))
    return 0 if r['status']=='SOURCE_REVIEW_ONLY' else 2

if __name__=='__main__':raise SystemExit(main())
