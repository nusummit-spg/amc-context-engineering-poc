"""Wave 2.7 cumulative installer: no destructive source editing, dry-run default.

Installs Wave 2.3–2.7 additive files from a validated extracted package.
The source-locked app_main and Wave2.6 patches are separate explicit steps.
"""
from __future__ import annotations
from pathlib import Path
import importlib.util
import hashlib
import argparse
import json
import shutil
import sys

NEW = (
 'install_wave27.py',
 'tools/amc_release/tests/test_wave27_installer.py',
 'backend/amc_publication/serving27.py',
 'backend/amc_publication/faiss_reader27.py',
 'backend/amc_publication/reconcile27.py',
 'tools/amc_release/app_wiring27.py',
 'tools/amc_release/app_wiring27_cli.py',
 'tools/amc_release/preflight27.py',
 'tools/amc_release/pytest_matrix27.py',
 'tools/amc_release/demo27.py',
 'tools/amc_release/tests/test_wave27_demo.py',
 'tools/amc_release/tests/test_wave27_matrix.py',
 'tools/amc_release/tests/test_wave27_serving.py',
 'tools/amc_release/tests/test_wave27_reconcile.py',
 'tools/amc_release/tests/test_wave27_faiss_reader.py',
 'tools/amc_release/tests/test_wave27_wiring.py',
 'tools/amc_release/tests/test_wave27_preflight.py',
 '.github/workflows/amc-wave27-integration.yml',
 'remediation/wave2_7/IMPLEMENTATION.md',
 'remediation/wave2_7/TEST_EVIDENCE.json',
)


def _load_previous(src:Path):
    spec=importlib.util.spec_from_file_location('amc_wave26_installer',src/'install_wave26.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply(src:Path, repo:Path, *, write=False, upgrade_wave24=False,upgrade_wave25=False) -> dict:
    src=src.resolve();repo=repo.resolve()
    if not (repo/'.git').exists() or not (repo/'backend').is_dir() or not (repo/'mf-context-engine').is_dir():
        raise ValueError('requires full AMC Git checkout with backend and mf-context-engine')
    old=_load_previous(src)
    plan = old.install(src,repo,apply_changes=False,upgrade_wave25=upgrade_wave25,upgrade_wave24=upgrade_wave24)
    new=[]
    for rel in NEW:
        frm=src/rel;to=repo/rel
        if not frm.is_file() or frm.is_symlink() or not frm.resolve().is_relative_to(src):
            raise ValueError('missing or unsafe source file '+rel)
        if not to.resolve().is_relative_to(repo) or to.is_symlink():
            raise ValueError('unsafe destination '+rel)
        if to.exists():
            if not to.is_file() or to.read_bytes()!=frm.read_bytes():
                raise FileExistsError('different file already exists: '+rel)
            continue
        new.append((frm,to))
    report={'status':'DRY_RUN', 'prior':plan,'wave27_new':len(new),'wave27_total':len(NEW)}
    if not write:return report
    # Apply new additions first; only after all source checks from Wave26 have
    # passed. On an I/O failure remove only paths created here.
    created=[]
    try:
        for frm,to in new:
            to.parent.mkdir(parents=True,exist_ok=True)
            created.append(to)
            shutil.copy2(frm,to)
        old.install(src,repo,apply_changes=True,upgrade_wave25=upgrade_wave25,upgrade_wave24=upgrade_wave24)
    except BaseException:
        for file in reversed(created):file.unlink(missing_ok=True)
        raise
    return {**report,'status':'ADDITIVE_FILES_APPLIED_REVIEW_REQUIRED'}


def main():
    ap=argparse.ArgumentParser(description='Wave2.7 cumulative installer; dry run first')
    ap.add_argument('--repo',required=True,type=Path)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--upgrade-wave24',action='store_true')
    ap.add_argument('--upgrade-wave25',action='store_true')
    opts=ap.parse_args()
    try:
        print(json.dumps(apply(Path(__file__).resolve().parent,opts.repo,write=opts.apply,
             upgrade_wave24=opts.upgrade_wave24,upgrade_wave25=opts.upgrade_wave25),indent=2))
        return 0
    except (ValueError,OSError,ImportError) as ex:
        print(json.dumps({'status':'BLOCK','reason':str(ex)},indent=2),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
