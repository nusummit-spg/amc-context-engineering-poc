"""Run reviewed, SHA-pinned Wave 2.5 publication source correction.

Run on a new feature branch; never changes GitHub or deploys.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .publication_patch25 import apply, SourceDrift


def main(argv=None):
    ap=argparse.ArgumentParser(description='Wave 2.5 source-aware local patch; dry-run by default')
    ap.add_argument('--repo',required=True)
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args(argv)
    try:
        result=apply(Path(args.repo),apply_changes=args.apply)
    except (SourceDrift, OSError, SyntaxError) as exc:
        print(json.dumps({'status':'BLOCK','error':str(exc)},indent=2))
        return 2
    # Do not print complete source diffs into logs by default. Output SHA and
    # anchor-reviewed patch summary for local review; inspect with git diff.
    compact={'status':result['status'],
             'files':{name:{k:v for k,v in meta.items() if k != 'diff'}
                      for name,meta in result['files'].items()}}
    print(json.dumps(compact,indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
