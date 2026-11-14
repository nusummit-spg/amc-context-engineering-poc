"""Cumulative Wave 2.8 installer. Dry-run, source-safe, additive only.

Requires a complete AMC checkout. Actual source modifications are separate
and require the reviewed post-Wave26 source signatures. No implicit commits,
production table creation, or deployment.
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
 'backend/amc_publication/active_authority28.py',
 'backend/amc_publication/serving28.py',
 'backend/amc_publication/vector_bridge28.py',
 'backend/alembic/versions/013_active_receipt_authority_v28.py',
 'tools/amc_release/active_cutover28.py',
 'tools/amc_release/tests_wave28/test_wave28_authority.py',
 'tools/amc_release/tests_wave28/test_wave28_vector_bridge.py',
 'tools/amc_release/tests_wave28/test_wave28_cutover_source.py',
 'tools/amc_release/tests_wave28/test_wave28_migration.py',
 'tools/amc_release/tests_wave28/test_wave28_installer.py',
 'tools/amc_release/release_audit28.py',
 '.github/workflows/amc-wave28-qualification.yml',
 'remediation/wave2_8/IMPLEMENTATION.md',
 'remediation/wave2_8/TEST_EVIDENCE.json',
 'install_wave28.py',
)


def _previous(src:Path):
    spec=importlib.util.spec_from_file_location('amc_wave27_installer',src/'install_wave27.py')
    if not spec or not spec.loader:raise ValueError('Wave27 installer not present')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def install(src:Path,repo:Path,*,apply_changes:bool=False,upgrade_wave24=False,upgrade_wave25=False):
    src=src.resolve();repo=repo.resolve()
    if not (repo/'.git').is_dir() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('complete Git AMC checkout required')
    old=_previous(src)
    prior=old.apply(src,repo,write=False,upgrade_wave24=upgrade_wave24,upgrade_wave25=upgrade_wave25)
    pending=[]
    for rel in ADDITIONS:
        file=src/rel;target=repo/rel
        if (not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(src)
            or not target.resolve().is_relative_to(repo) or target.is_symlink()):
            raise ValueError('unsafe/missing package source or target: '+rel)
        if target.exists():
            if not target.is_file() or target.read_bytes()!=file.read_bytes():
                raise FileExistsError('existing source differs: '+rel)
            continue
        pending.append((file,target))
    report={'status':'DRY_RUN','previous':prior,'wave28_new_files':len(pending),
        'wave28_allowlisted_files':len(ADDITIONS),'source_patch_required':True}
    if not apply_changes:return report
    created=[]
    try:
        for src_file,target in pending:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src_file,target)
            created.append(target)
        old.apply(src,repo,write=True,upgrade_wave24=upgrade_wave24,upgrade_wave25=upgrade_wave25)
    except BaseException:
        for f in reversed(created):f.unlink(missing_ok=True)
        raise
    report['status']='ADDITIVE_INSTALLED_NOT_RELEASE_APPROVED'
    return report


def main():
    ap=argparse.ArgumentParser(description='Wave28 cumulative addition-only installer')
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--upgrade-wave24',action='store_true')
    ap.add_argument('--upgrade-wave25',action='store_true')
    p=ap.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parent,p.repo,apply_changes=p.apply,
          upgrade_wave24=p.upgrade_wave24,upgrade_wave25=p.upgrade_wave25),indent=2))
    except (ValueError,ImportError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','reason':str(ex)}),file=sys.stderr)
        return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
