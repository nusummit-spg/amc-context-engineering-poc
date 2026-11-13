"""Cumulative Wave 3.0 additive-only installer, then run apply_all30 separately.

Existing source changes are intentionally NOT performed by this installer.
A branch-integrated source preflight and source-locked patch run are required.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ADDITIONS=(
    'tools/amc_release/assurance30.py',
    'tools/amc_release/preflight30.py',
    'tools/amc_release/apply_all30.py',
    'tools/amc_release/qualification30.py',
    'tools/amc_release/tests_wave30/test_active_races30.py',
    'tools/amc_release/tests_wave30/test_preflight30.py',
    'tools/amc_release/tests_wave30/test_assurance30.py',
    'tools/amc_release/tests_wave30/test_installer30.py',
    '.github/workflows/amc-wave30-qualification.yml',
    'remediation/wave3_0/IMPLEMENTATION.md',
    'remediation/wave3_0/TEST_EVIDENCE.json',
    'install_wave30.py',
)

def _prior(bundle:Path):
    spec=importlib.util.spec_from_file_location('amc_install_wave29',bundle/'install_wave29.py')
    if not spec or not spec.loader:raise ValueError('Wave 2.9 cumulative installer required')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def install(bundle:Path,repo:Path,*,apply:bool=False):
    bundle=Path(bundle).resolve();repo=Path(repo).resolve()
    if not (repo/'.git').is_dir() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('actual AMC checkout with .git, backend and frontend required')
    previous=_prior(bundle).install(bundle,repo,apply=False)
    pending=[];present=[]
    for rel in ADDITIONS:
        source=bundle/rel; target=repo/rel
        if (not source.is_file() or source.is_symlink() or
            not source.resolve().is_relative_to(bundle) or target.is_symlink() or
            not target.resolve().is_relative_to(repo)):
            raise ValueError('unsafe or absent source/target: '+rel)
        if target.exists():
            if not target.is_file() or target.read_bytes()!=source.read_bytes():
                raise FileExistsError('refuse overwrite of existing file '+rel)
            present.append(rel)
        else:pending.append((source,target))
    result={'status':'DRY_RUN','prior':previous,'new_files':len(pending),
            'already_present':len(present),'source_patches_applied':False,
            'release':'BLOCKED'}
    if not apply:return result
    created=[]
    try:
        for source,target in pending:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:
                f.write(source.read_bytes())
            created.append(target)
        _prior(bundle).install(bundle,repo,apply=True)
    except BaseException:
        for f in reversed(created):f.unlink(missing_ok=True)
        raise
    return {**result,'status':'ADDITIVE_INSTALLED_SOURCE_PATCH_PENDING'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    opts=ap.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parent,opts.repo,apply=opts.apply),indent=2))
        return 0
    except (ValueError,FileExistsError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','reason':str(ex)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
