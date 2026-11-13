"""Wave 2.5 cumulative installer: dry-run first, no unknown overwrites.

Installs all unmodified Wave 2.4 files + Wave 2.5 additive files. The only
known overwrite is the Wave 2.4 release matrix, explicitly allowed with
--upgrade-wave24 and its exact old SHA-256. Existing AMC publication sources
are modified separately by SHA-pinned patch_publication25_cli after review.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys

OLD_W24_WORKFLOW_SHA256 = 'd4296e4932e94fa957244ca8b3350eab8b0f8d4d725926abda4098b3bbe5ec5e'
WORKFLOW = '.github/workflows/amc-release-verification.yml'
EXTRAS = (
    'install_wave24.py',
    'install_wave25.py',
    'tools/amc_release/tests/fixtures/wave24_release_verification.yml',
    'backend/amc_publication/approval_adapter.py',
    'tools/amc_release/publication_patch25.py',
    'tools/amc_release/publication_patch25_cli.py',
    'tools/amc_release/sign_corpus25.py',
    'tools/amc_release/tests/test_wave25_adapter.py',
    'tools/amc_release/tests/test_wave25_patcher.py',
    'tools/amc_release/tests/test_wave25_publication_flow.py',
    'tools/amc_release/tests/test_wave25_atomic_recovery.py',
    'tools/amc_release/tests/test_wave25_signer.py',
    'tools/amc_release/tests/test_wave25_installer.py',
    'tools/amc_release/tests/fixtures/journal_reference_1_9.py.txt',
    'remediation/wave2_5/IMPLEMENTATION_HANDOFF.md',
    'remediation/wave2_5/TASK_MATRIX.csv',
    'remediation/wave2_5/TEST_EVIDENCE.json',
)


def _base_files(source: Path):
    spec=importlib.util.spec_from_file_location('amc_wave24_installer',source/'install_wave24.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return list(module.FILES)


def install(source: Path, target: Path, *, apply_changes: bool=False,
            upgrade_wave24: bool=False) -> dict:
    root=target.resolve()
    if not (root/'.git').exists() or not (root/'backend').is_dir() or not (root/'mf-context-engine').is_dir():
        raise ValueError('must install in a real AMC Git checkout with backend and frontend')
    files=list(dict.fromkeys(_base_files(source)+list(EXTRAS)))
    new_files=[]; upgrades=[]; identical=0
    for rel in files:
        src=source/rel; dst=root/rel
        if not src.is_file() or src.is_symlink():
            raise ValueError('package missing/unsafe source: '+rel)
        if not dst.resolve().is_relative_to(root):
            raise ValueError('target symlink/path escapes repo: '+rel)
        if not dst.exists():
            new_files.append((src,dst));continue
        if not dst.is_file() or dst.is_symlink():
            raise ValueError('conflicting target path: '+rel)
        old=dst.read_bytes(); desired=src.read_bytes()
        if old==desired:
            identical+=1;continue
        digest=hashlib.sha256(old).hexdigest()
        if rel!=WORKFLOW or not upgrade_wave24 or digest!=OLD_W24_WORKFLOW_SHA256:
            raise FileExistsError('unknown existing content / refusal to overwrite: '+rel)
        backup=root/(rel+'.wave25.bak')
        if backup.exists():
            raise FileExistsError('prior upgrade backup exists: '+str(backup))
        upgrades.append((src,dst,backup))
    summary={'status':'DRY_RUN' if not apply_changes else 'APPLIED_REVIEW_REQUIRED',
             'files_new':len(new_files),'files_same':identical,
             'known_wave24_upgrade':len(upgrades),'total':len(files)}
    if apply_changes:
        # All paths preflighted before any modification.
        for src,dst in new_files:
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dst)
        for src,dst,backup in upgrades:
            shutil.copy2(dst,backup)
            shutil.copy2(src,dst)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description='Cumulative AMC Wave 2.5 source-safe overlay (dry-run by default)')
    p.add_argument('--repo',required=True)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--upgrade-wave24',action='store_true',help='allow only pinned Wave 2.4 matrix upgrade')
    args=p.parse_args(argv)
    try:
        outcome=install(Path(__file__).resolve().parent,Path(args.repo),
                        apply_changes=args.apply,upgrade_wave24=args.upgrade_wave24)
    except (OSError,ValueError,ImportError) as ex:
        print(json.dumps({'status':'BLOCK','reason':str(ex)},indent=2),file=sys.stderr)
        return 2
    print(json.dumps(outcome,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
