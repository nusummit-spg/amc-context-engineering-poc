"""Targeted, review-only hardening of known unsafe AMC Assurance CI patterns.

Transforms only exact observed anchors of amc-dev at 2c0415c4; fails closed
on changed workflow instead of pretending to fix an unknown future version.
Never overwrites a file without explicit --apply and a .bak file.
"""
from __future__ import annotations
from pathlib import Path
from .patch_ci import fixed_workflow


class AssuranceHardeningError(ValueError):
    pass


def harden(source: str) -> str:
    out = fixed_workflow(source)
    replacements = [
        ('python -m pytest tests/ --collect-only -q 2>&1 | tail -20 || true',
         'python -m pytest tests/ --collect-only -q'),
        ('echo "Checking SLO metrics (placeholder - requires actual metrics collection)"',
         'echo "FB05: live 1h/24h telemetry proof not configured; release BLOCKED"\n          exit 1'),
        ('echo "Canary deployment requires a real staging environment."',
         'echo "GATE05: real canary not configured; release BLOCKED"\n          exit 1'),
    ]
    for old,new in replacements:
        if out.count(old) == 1:
            out = out.replace(old,new,1)
        elif out.count(new) == 1:
            continue  # idempotent after reviewed application
        else:
            raise AssuranceHardeningError(f'unknown workflow: missing/duplicate anchor {old[:70]}')
    return out


def apply(path: str | Path, *, check: bool = True) -> dict:
    p = Path(path)
    src = p.read_text(encoding='utf-8')
    revised = harden(src)
    changed = revised != src
    if changed and not check:
        backup = p.with_name(p.name+'.bak')
        if backup.exists():
            raise AssuranceHardeningError('workflow backup already exists')
        backup.write_text(src,encoding='utf-8')
        p.write_text(revised,encoding='utf-8')
    return {'status':'PASS','changed':changed,'dry_run':check,'requires_live_services':True,
            'note':'This fixes CI presentation but intentionally blocks absent SLO/canary.'}
