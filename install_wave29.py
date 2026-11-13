"""Wave 2.9 cumulative installer. Dry-run and additive only; separate source patcher.

Run from an extracted, reviewed Wave2.9 bundle. Never overwrites existing files,
never modifies Git refs, never executes an Alembic migration, never deploys.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ADDITIONS=(
    'backend/amc_publication/ingestion_boundary29.py',
    'backend/amc_publication/request_fence29.py',
    'tools/amc_release/ingest_cutover29.py',
    'tools/amc_release/quarantine29.py',
    'tools/amc_release/apply_all29.py',
    'tools/amc_release/tests_wave29/test_cutover29.py',
    'tools/amc_release/tests_wave29/test_quarantine29.py',
    'tools/amc_release/tests_wave29/test_request_fence29.py',
    'tools/amc_release/tests_wave29/test_quarantine_cli29.py',
    'tools/amc_release/tests_wave29/test_boundary_e2e29.py',
    'tools/amc_release/tests_wave29/test_install29.py',
    'tools/amc_release/tests_wave29/test_bootstrap29.py',
    '.github/workflows/amc-wave29-integration.yml',
    'remediation/wave2_9/IMPLEMENTATION.md',
    'remediation/wave2_9/TEST_EVIDENCE.json',
    'install_wave29.py',
)


def _prev(root):
    spec=importlib.util.spec_from_file_location('wave28_installer',root/'install_wave28.py')
    if spec is None or spec.loader is None:raise ValueError('Wave2.8 installer required')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def install(src:Path,repo:Path,*,apply:bool=False,upgrade_wave24:bool=False,upgrade_wave25:bool=False):
    src=src.resolve();repo=repo.resolve()
    if not (repo/'.git').is_dir() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('full AMC Git checkout required; no standalone mock checkout accepted')
    prior=_prev(src).install(src,repo,apply_changes=False,upgrade_wave24=upgrade_wave24,upgrade_wave25=upgrade_wave25)
    pending=[];present=[]
    for rel in ADDITIONS:
        source=src/rel;target=repo/rel
        if (not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(src)
            or not target.resolve().is_relative_to(repo) or target.is_symlink()):
            raise ValueError('unsafe/missing source or target: '+rel)
        if target.exists():
            if not target.is_file() or target.read_bytes()!=source.read_bytes():
                raise FileExistsError('refuse changed existing target '+rel)
            present.append(rel)
        else:pending.append((source,target))
    result={'status':'DRY_RUN','reviewed_base':'2c0415c4d23a3338428c8314c869299aa0ab771f',
            'previous':prior,'new_file_count':len(pending),'already_present_count':len(present),
            'source_patcher':'python -m tools.amc_release.ingest_cutover29 --repo . [--apply]',
            'release_approved':False}
    if not apply:return result
    created=[]
    try:
        for source,target in pending:
            target.parent.mkdir(parents=True,exist_ok=True)
            # exclusive create: no concurrent overwrite between preflight and write
            with target.open('xb') as f:
                f.write(source.read_bytes());f.flush()
                import os
                os.fsync(f.fileno())
            created.append(target)
        _prev(src).install(src,repo,apply_changes=True,
                           upgrade_wave24=upgrade_wave24,upgrade_wave25=upgrade_wave25)
    except BaseException:
        for file in created:file.unlink(missing_ok=True)
        raise
    result['status']='ADDITIVE_FILES_INSTALLED_SOURCE_PATCH_PENDING'
    return result


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--repo',required=True,type=Path)
    cli.add_argument('--apply',action='store_true')
    cli.add_argument('--upgrade-wave24',action='store_true')
    cli.add_argument('--upgrade-wave25',action='store_true')
    p=cli.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parent,p.repo,apply=p.apply,
            upgrade_wave24=p.upgrade_wave24,upgrade_wave25=p.upgrade_wave25),indent=2))
        return 0
    except (OSError,ValueError,FileExistsError) as ex:
        print(json.dumps({'status':'BLOCKED','error':str(ex)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
