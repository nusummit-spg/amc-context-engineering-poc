#!/usr/bin/env python3
"""One-purpose, reversible source edit for AMC assurance Gitleaks setup.

The gitleaks GitHub Action requires a commercial license for org-owned repos;
the CLI remains usable without that action license. This replaces only the
scanner stanza and keeps scanner failures fatal. Run from repository root.
"""
from pathlib import Path
import sys

PATH = Path('.github/workflows/amc-assurance.yml')
START = '      - name: Scan for secrets\n'
END = '      - name: Audit requirements\n'
REPLACEMENT = '''      - name: Scan for secrets (Gitleaks CLI, organization-compatible)
        run: |
          docker run --rm \\
            -v "${{ github.workspace }}:/repo" \\
            -w /repo \\
            ghcr.io/gitleaks/gitleaks:v8.30.1 \\
            git --redact --exit-code 1 --verbose .

'''


def apply(source: str) -> str:
    if 'name: Scan for secrets (Gitleaks CLI, organization-compatible)' in source:
        return source  # Idempotent.
    i = source.find(START)
    j = source.find(END, i + len(START))
    if i < 0 or j < 0 or j <= i:
        raise ValueError('AMC assurance scan stanza changed; refusing unsafe automated rewrite')
    return source[:i] + REPLACEMENT + source[j:]


def main() -> int:
    if not PATH.exists():
        print('ERROR: Run from repository root; missing ' + str(PATH), file=sys.stderr)
        return 2
    old = PATH.read_text(encoding='utf-8')
    new = apply(old)
    if new == old:
        print('Already uses Gitleaks CLI; no changes')
        return 0
    backup = PATH.with_suffix('.yml.wave19-backup')
    if backup.exists():
        raise RuntimeError('Backup already exists: please review it before rerunning')
    backup.write_text(old, encoding='utf-8')
    PATH.write_text(new, encoding='utf-8')
    print(f'Updated {PATH}; original backed up at {backup}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
