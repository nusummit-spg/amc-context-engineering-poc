"""Narrow, non-destructive patch for the observed misindented A05 run step.

Does NOT repair unrelated CI problems or replace the original workflow.
Use --check during review, and apply only to an isolated checkout/branch.
"""
from __future__ import annotations
from pathlib import Path


class CIPatchError(ValueError):
    pass


def fixed_workflow(src: str) -> str:
    before = '      - name: Run fault injection tests\n         run: |'
    after = '      - name: Run fault injection tests\n        run: |'
    if before not in src:
        if after in src:
            return src
        raise CIPatchError('expected A05 workflow anchor not found; refuse blind rewrite')
    if src.count(before) != 1:
        raise CIPatchError('ambiguous A05 workflow anchors')
    return src.replace(before, after)


def apply_workflow(path: str | Path, *, check: bool = True) -> bool:
    p = Path(path)
    original = p.read_text(encoding='utf-8')
    patched = fixed_workflow(original)
    if not check and original != patched:
        # Only used on a disposable local branch. Preserves old content in .bak.
        backup = p.with_suffix(p.suffix + '.bak')
        if backup.exists():
            raise CIPatchError('backup exists: refusing overwrite')
        backup.write_text(original, encoding='utf-8')
        p.write_text(patched, encoding='utf-8')
    return original != patched
