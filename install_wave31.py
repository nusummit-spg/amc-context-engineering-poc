"""Wave 3.1 cumulative additive installer, after exact-SHA source preflight.

Does not modify source files, Git refs, or deployment. Existing Wave 3.0
installer composes Waves 2.3-3.0 and copies the updated active authority
module from this cumulative bundle at initial installation.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ADDITIONS=(
    'backend/alembic/versions/014_publication_scope_claim_v31.py',
    'backend/amc_publication/scope_audit31.py',
    'tools/amc_release/governance_guard31.py',
    'tools/amc_release/apply_all31.py',
    'tools/amc_release/qualification31.py',
    'tools/amc_release/run_wave31_tests.py',
    'tools/amc_release/tests_wave31/test_scope_claim31.py',
    'tools/amc_release/tests_wave31/test_scope_migration31.py',
    'tools/amc_release/tests_wave31/test_scope_audit31.py',
    'tools/amc_release/tests_wave31/test_governance_guard31.py',
    'tools/amc_release/tests_wave31/test_apply31.py',
    '.github/workflows/amc-wave31-durable-mutation.yml',
    'remediation/wave3_1/IMPLEMENTATION.md',
    'install_wave31.py',
)


def _previous(bundle):
    spec=importlib.util.spec_from_file_location('wave30_installer_for31',bundle/'install_wave30.py')
    if not spec or not spec.loader:raise ValueError('Wave3.0 cumulative installer absent')
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
    return x


def install(bundle:Path,repo:Path,*,apply:bool=False):
    bundle=Path(bundle).resolve();repo=Path(repo).resolve()
    if not (repo/'.git').is_dir() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('actual AMC Git checkout required')
    previous=_previous(bundle).install(bundle,repo,apply=False)
    pending=[];already=[]
    for rel in ADDITIONS:
        src=bundle/rel; dst=repo/rel
        if not src.is_file() or src.is_symlink() or not src.resolve().is_relative_to(bundle) or dst.is_symlink() or not dst.resolve().is_relative_to(repo):
            raise ValueError('unsafe or missing additive file '+rel)
        if dst.exists():
            if not dst.is_file() or dst.read_bytes()!=src.read_bytes():
                raise FileExistsError('existing Wave31 destination differs '+rel)
            already.append(rel)
        else:pending.append((src,dst))
    outcome={'status':'DRY_RUN','prior_status':previous['status'],
             'additions':len(pending),'identical_existing':len(already),
             'production_release':'BLOCKED'}
    if not apply:return outcome
    created=[]
    try:
        # First apply cumulative previous additions, including modified authority.
        _previous(bundle).install(bundle,repo,apply=True)
        for src,dst in pending:
            dst.parent.mkdir(parents=True,exist_ok=True)
            with dst.open('xb') as h:h.write(src.read_bytes())
            created.append(dst)
    except BaseException:
        for dst in reversed(created):dst.unlink(missing_ok=True)
        raise
    return {**outcome,'status':'ADDITIVE_INSTALLED_SOURCE_PATCH_PENDING'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    x=p.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parent,x.repo,apply=x.apply),indent=2))
        return 0
    except (FileExistsError,ValueError,OSError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)}))
        return 2

if __name__=='__main__':raise SystemExit(main())
