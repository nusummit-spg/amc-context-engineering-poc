"""Cross-platform exact inventory of required Wave 2.7 + historical contract tests.

Windows PowerShell does not reliably expand wildcard native-command arguments.
This runner deliberately refuses missing categories and zero-item suites.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import json

REQUIRED = {
 'wave27': 'tools/amc_release/tests/test_wave27_*.py',
 'wave19': 'backend/tests/test_wave19_*.py',
 'wave20': 'backend/tests/test_wave20_*.py',
}


def selected(repo:Path) -> dict[str,list[Path]]:
    root=repo.resolve()
    groups={}
    for key,pattern in REQUIRED.items():
        files=sorted(p for p in root.glob(pattern) if p.is_file() and not p.is_symlink())
        if not files:
            raise ValueError('missing required nonempty test category: '+key)
        groups[key]=files
    return groups


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description='Cross-platform AMC release test inventory and runner')
    p.add_argument('--repo',type=Path,default=Path('.'))
    p.add_argument('--report',default='wave27-matrix.xml')
    p.add_argument('--list-only',action='store_true')
    args=p.parse_args(argv)
    root=args.repo.resolve()
    try:
        groups=selected(root)
        inventory={k:[x.relative_to(root).as_posix() for x in v] for k,v in groups.items()}
        print(json.dumps({'status':'INVENTORY_PRESENT','counts':{k:len(v) for k,v in inventory.items()},
                          'files':inventory},indent=2))
        if args.list_only:return 0
        import pytest
        paths=[str(file) for g in groups.values() for file in g]
        report=root/args.report
        if not report.resolve().is_relative_to(root):
            raise ValueError('report must be inside repository')
        return int(pytest.main(['-q','--strict-markers','--tb=short',*paths,
                                 '--junitxml='+str(report)]))
    except (ValueError,OSError) as exc:
        print(json.dumps({'status':'BLOCK','reason':str(exc)},indent=2))
        return 2

if __name__=='__main__':raise SystemExit(main())
