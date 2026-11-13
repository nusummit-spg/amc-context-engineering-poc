"""Install Wave 2.4 additive files into an AMC checkout, without overwrites.

Default mode dry-runs; --apply required for copying. Only predefined files
are copied. Existing identical files are skipped; changed files fail closed.
Existing amc-assurance.yml is never overwritten (use narrow patch separately).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys

FILES = [
    '.github/workflows/amc-release-verification.yml',
    'mf-context-engine/playwright.uat.config.mjs',
    'mf-context-engine/tests/feedback_uat.spec.mjs',
    'tools/amc_release/__init__.py',
    'tools/amc_release/common.py',
    'tools/amc_release/ledger.py',
    'tools/amc_release/slo.py',
    'tools/amc_release/counts.py',
    'tools/amc_release/gate.py',
    'tools/amc_release/canary.py',
    'tools/amc_release/patch_ci.py',
    'tools/amc_release/github_ci.py',
    'tools/amc_release/cli.py',
    'tools/amc_release/tests/__init__.py',
    'tools/amc_release/tests/test_release_core.py',
    'tools/amc_release/tests/test_uat_gate.py',
    'tools/amc_release/tests/test_github_ci.py',
    'tools/amc_release/tests/test_wave24_hardening.py',
    'tools/amc_release/tests/test_composition.py',
    'tools/amc_release/composition.py',
    'tools/amc_release/rollback.py',
    'tools/amc_release/assurance_ci.py',
    'tools/amc_release/tests/test_assurance_ci.py',
    'tools/amc_release/tests/test_wave24_rollback.py',
    'tools/amc_release/tests/test_wave24_slo_freshness.py',
    'mf-context-engine/src/services/api.contract.test.js',
    'remediation/wave2_3/IMPLEMENTATION_UAT_HANDOFF.md',
    'remediation/wave2_3/UAT_STATUS.json',
    'remediation/wave2_3/TEST_EVIDENCE.json',
    'examples/uat_evidence_blocked.json',
    'remediation/wave2_4/IMPLEMENTATION_PROGRESS.md',
    'remediation/wave2_4/UAT_ACCEPTANCE_MATRIX.csv',
    'remediation/wave2_4/LOCAL_TEST_EVIDENCE.json',
]


def install(source: Path, target: Path, *, apply: bool = False) -> dict:
    if not (target / '.git').exists() or not (target / 'backend').is_dir() or not (target / 'mf-context-engine').is_dir():
        raise ValueError('target must be an AMC Git checkout with backend and mf-context-engine')
    counts = {'new': 0, 'same': 0, 'conflicts': 0, 'applied': 0, 'dry_run': not apply}
    pending = []
    for relative in FILES:
        src = source / relative
        dest = target / relative
        # Guard against pre-existing symlinked parent directories escaping checkout.
        try:
            dest.resolve().relative_to(target.resolve())
        except ValueError as ex:
            raise ValueError(f'install destination escapes repository: {relative}') from ex
        if not src.is_file():
            raise FileNotFoundError(f'package missing {relative}')
        if dest.exists():
            if dest.is_file() and src.read_bytes() == dest.read_bytes():
                counts['same'] += 1
            else:
                counts['conflicts'] += 1
                raise FileExistsError(f'conflicting existing target (never overwritten): {relative}')
        else:
            counts['new'] += 1
            pending.append((src, dest))
    if apply:
        for src, dest in pending:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            counts['applied'] += 1
    return counts


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', required=True)
    p.add_argument('--apply', action='store_true', help='copy new files; default is dry run')
    args = p.parse_args()
    import json
    try:
        out = install(Path(__file__).resolve().parent, Path(args.repo).resolve(), apply=args.apply)
    except (OSError, ValueError) as ex:
        print(json.dumps({'status': 'BLOCK', 'reason': str(ex)}), file=sys.stderr)
        return 2
    print(json.dumps({'status': 'OK', **out}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
