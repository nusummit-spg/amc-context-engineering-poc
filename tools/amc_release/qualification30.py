"""Read-only technical qualification of an integrated AMC Wave 3.0 checkout.

Exposes explicit NOT_RUN on infrastructure. Never treats a passing offline
unit suite as a signed release or an actual canary. Emits a machine-readable
report for engineering and UAT reviewers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from .apply_all29 import BASE

REQUIRED_MARKERS={
 'backend/amc_publication/worker.py':('W25_FROZEN_VECTOR_PREIMAGE','W26_DURABLE_GRAPH_PREIMAGE'),
 'backend/amc_publication/journal.py':('W25_NONEMPTY_CORPUS','W26_POINTER_ROW_LOCK','W28_ACTIVE_RECEIPT_AUTHORITY'),
 'backend/app/main.py':('W27_PUBLICATION_STATUS_ROUTER',),
 'backend/app/vector/client.py':('W28_VERIFIED_READ_CUTOVER','W29_RAW_VECTOR_WRITE_GUARD'),
 'backend/app/retrieval/orchestrator.py':('W28_ORCHESTRATOR_AUTHORITY',),
 'backend/app/api/routes/query.py':('W28_TRADITIONAL_TENANT_SCOPE',),
 'backend/app/api/deps.py':('W29_SPLIT_INGESTION_AND_READS',),
 'backend/app/ingestion/pipeline.py':('W29_PIPELINE_EARLY_BLOCK',),
 'backend/app/api/routes/ingest.py':('W29_INGEST_HTTP_GUARD',),
 'backend/amc_publication/status_route.py':('W26_TENANT_SCOPED_STATUS',),
 'backend/amc_publication/active_authority28.py':('W30: On crash replay',),
 'backend/amc_publication/faiss_reader27.py':('W30: The pointer/receipt',),
 'backend/amc_publication/vector_bridge28.py':('W30: pin current authority',),
}
REQUIRED_NEW=[
 'backend/alembic/versions/013_active_receipt_authority_v28.py',
 'tools/amc_release/preflight30.py',
 'tools/amc_release/assurance30.py',
 'tools/amc_release/tests_wave30/test_active_races30.py',
 '.github/workflows/amc-wave30-qualification.yml',
]


def inspect(repo:Path) -> dict:
    root=Path(repo).resolve()
    checks={}
    for rel,markers in REQUIRED_MARKERS.items():
        p=root/rel
        present=p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root)
        content=p.read_text(encoding='utf-8') if present else ''
        checks[rel]={'status':'PASS' if present and all(m in content for m in markers) else 'BLOCKED',
                     'missing_markers':[m for m in markers if m not in content],
                     'sha256':hashlib.sha256(content.encode()).hexdigest() if present else None}
        if present and rel.endswith('.py'):
            try:compile(content,rel,'exec')
            except (SyntaxError,ValueError) as exc:
                checks[rel]['status']='BLOCKED'
                checks[rel]['syntax_error']=str(exc)
    for rel in REQUIRED_NEW:
        p=root/rel
        checks[rel]={'status':'PASS' if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root) else 'BLOCKED'}
    workflow=root/'.github/workflows/amc-assurance.yml'
    if workflow.is_file():
        value=workflow.read_text(encoding='utf-8')
        checks['assurance-ci-yaml']={'status':'BLOCKED' if '         run: |' in value or '|| true' in value else 'PASS',
                                    'reason':'A05 malformed or pytest collection masked' if '         run: |' in value or '|| true' in value else ''}
        try:
            import yaml
            tree=yaml.safe_load(value)
            if not isinstance(tree,dict) or not isinstance(tree.get('jobs'),dict):
                checks['assurance-ci-yaml']['status']='BLOCKED'
        except Exception as ex:
            checks['assurance-ci-yaml']['status']='BLOCKED';checks['assurance-ci-yaml']['reason']=str(ex)
    else:checks['assurance-ci-yaml']={'status':'BLOCKED','reason':'missing workflow'}
    backups=sorted(str(x.relative_to(root)) for x in root.rglob('*.wave*.bak')
                   if x.is_file() and x.resolve().is_relative_to(root))
    checks['source-backup-hygiene']={'status':'BLOCKED' if backups else 'PASS',
                                     'backups':backups[:30], 'count':len(backups)}
    try:
        sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True,stderr=subprocess.STDOUT).strip()
        branch=subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True,stderr=subprocess.STDOUT).strip()
    except (OSError,subprocess.CalledProcessError):
        sha=None;branch=None
    checks['git-checkout']={'status':'PASS' if sha and branch and branch!='main' else 'BLOCKED',
                            'sha':sha, 'branch':branch,'reviewed_base':BASE}
    blockers=[k for k,v in checks.items() if v['status']!='PASS']
    return {'schema':'amc-wave30-offline-qualification-v1',
            'status':'PASS_OFFLINE_SOURCE_ONLY' if not blockers else 'BLOCKED',
            'check_count':len(checks), 'source_blockers':blockers,
            'checks':checks,
            'unexecuted_gates':{
              'full_application_pytest':'NOT_RUN',
              'postgres_concurrency':'NOT_RUN',
              'neo4j_mutation_readback':'NOT_RUN',
              'faiss_real_binary_serving':'NOT_RUN',
              'windows_linux_ci_exact_sha':'NOT_RUN',
              'staging_browser_automation':'NOT_RUN',
              'slo_1h_24h':'NOT_RUN',
              'canary_rollback':'NOT_RUN',
              'reviewer_security_signoff':'NOT_RUN'},
            'release_decision':'BLOCKED', 'uat_authorized':False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    report=inspect(args.repo)
    rendered=json.dumps(report,indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(rendered,encoding='utf-8')
    print(rendered)
    return 0 if report['status']=='PASS_OFFLINE_SOURCE_ONLY' else 2
if __name__=='__main__':raise SystemExit(main())
