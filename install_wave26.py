"""Wave 2.6 cumulative branch-ready installer, dry-run by default.

Installs Wave 2.3-2.6 additive source files and a narrowly allowlisted set of
unmodified Wave 2.5 upgrades. Never changes original AMC publication worker,
journal, governance or FAISS source: use the separately pinned patch26 CLI.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys

KNOWN_WAVE25_SHA256 = {
    '.github/workflows/amc-release-verification.yml': 'df62b27e09503ec8c705bb942a2a99b7d896815a9fcfd950f1ac0c548199a1ad',
    'tools/amc_release/tests/test_wave25_adapter.py': '41c72fa5aaa4580281b52563075c253ebf08d57a1b1b75845e7f4673130051c9',
    'tools/amc_release/tests/test_wave25_atomic_recovery.py': '5523dc68d89d36233688041a4762212974cfcd15ddf33ea81ef0df5db2dcd287',
    'tools/amc_release/tests/test_wave25_publication_flow.py': '0a04d692a7dc5695a89a670a5cc46f5ab03d88841837d8d2bdd5639f6b4deead',
    'tools/amc_release/tests/test_wave25_signer.py': '135c32b184183acb6ee35dac1dc4ac3838071e95c5e1ab6a4b11927e882dc01e',
}

EXTRA = (
    'install_wave26.py',
    'backend/amc_publication/catalog26.py',
    'backend/amc_publication/approval_catalog26.py',
    'tools/amc_release/publication_patch26.py',
    'tools/amc_release/publication_patch26_cli.py',
    'tools/amc_release/source_catalog26.py',
    'tools/amc_release/tests/conftest.py',
    'tools/amc_release/tests/test_wave26_patch.py',
    'tools/amc_release/tests/test_wave26_journal_sql.py',
    'tools/amc_release/tests/test_wave26_catalog.py',
    'tools/amc_release/tests/test_wave26_faiss_windows.py',
    'tools/amc_release/tests/test_wave26_status_scope.py',
    'tools/amc_release/tests/test_wave26_catalog_builder.py',
    'tools/amc_release/tests/test_wave26_installer.py',
    'remediation/wave2_6/IMPLEMENTATION_HANDOFF.md',
    'remediation/wave2_6/TEST_EVIDENCE.json',
    'remediation/wave2_6/RELEASE_READINESS.json',
)


def _base_files(source: Path) -> list[str]:
    spec=importlib.util.spec_from_file_location('wave25_bootstrap',source/'install_wave25.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(dict.fromkeys(module._base_files(source)+list(module.EXTRAS)+list(EXTRA)))


def install(source: Path, repo: Path, *, apply_changes=False, upgrade_wave25=False, upgrade_wave24=False) -> dict:
    source=source.resolve();root=repo.resolve()
    if not (root/'.git').exists() or not (root/'backend').is_dir() or not (root/'mf-context-engine').is_dir():
        raise ValueError('requires an AMC Git checkout containing backend and mf-context-engine')
    plan=[]
    for relative in _base_files(source):
        src=source/relative;dst=root/relative
        if src.is_symlink() or not src.is_file():
            raise ValueError('missing/unsafe package file: '+relative)
        if not dst.resolve().is_relative_to(root):
            raise ValueError('refuse installation through symlink outside repo: '+relative)
        if not dst.exists():
            plan.append(('new',src,dst,None));continue
        if dst.is_symlink() or not dst.is_file():
            raise ValueError('existing file is unsafe: '+relative)
        old=dst.read_bytes();desired=src.read_bytes()
        if old==desired:
            plan.append(('same',src,dst,None));continue
        actual=hashlib.sha256(old).hexdigest()
        authorized = (upgrade_wave25 and KNOWN_WAVE25_SHA256.get(relative)==actual)
        if not authorized and relative=='.github/workflows/amc-release-verification.yml' and upgrade_wave24:
            spec=importlib.util.spec_from_file_location('wave25_old',source/'install_wave25.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            authorized = actual==mod.OLD_W24_WORKFLOW_SHA256
        if not authorized:
            raise FileExistsError('unknown prior content; do not overwrite: '+relative)
        backup=root/(relative+'.wave26.bak')
        if backup.exists():
            raise FileExistsError('prior backup exists: '+relative)
        plan.append(('upgrade',src,dst,backup))
    counts={'new':sum(x[0]=='new' for x in plan),
            'same':sum(x[0]=='same' for x in plan),
            'upgrades':sum(x[0]=='upgrade' for x in plan),
            'total':len(plan)}
    if not apply_changes:
        return {'status':'DRY_RUN',**counts}
    # Source and target validation finished; now copy. On any I/O exception,
    # revert changed files using backups, and delete newly created files.
    completed=[]
    try:
        for mode,src,dst,backup in plan:
            if mode=='same':continue
            dst.parent.mkdir(parents=True,exist_ok=True)
            if mode=='upgrade':
                shutil.copy2(dst,backup)
            # Record before copying: permits restoration if copy2 itself fails.
            completed.append((mode,dst,backup))
            shutil.copy2(src,dst)
    except Exception:
        for mode,dst,backup in reversed(completed):
            if mode=='new':
                dst.unlink(missing_ok=True)
            elif backup and backup.exists():
                shutil.copy2(backup,dst)
        raise
    return {'status':'APPLIED_REVIEW_REQUIRED',**counts}


def main(argv=None):
    p=argparse.ArgumentParser(description='Wave 2.6 cumulative offline overlay; dry-run default')
    p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--upgrade-wave25',action='store_true')
    p.add_argument('--upgrade-wave24',action='store_true')
    args=p.parse_args(argv)
    try:
        result=install(Path(__file__).resolve().parent,args.repo,apply_changes=args.apply,
                       upgrade_wave25=args.upgrade_wave25,upgrade_wave24=args.upgrade_wave24)
        print(json.dumps(result,indent=2))
        return 0
    except (OSError,ValueError,ImportError) as ex:
        print(json.dumps({'status':'BLOCK','reason':str(ex)},indent=2),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
