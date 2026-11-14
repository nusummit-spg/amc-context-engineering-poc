"""CLI for single-pass baseline-locked Wave 2.5+2.6 patch composition."""
import argparse
import json
from pathlib import Path
from .publication_patch26 import apply, SourceDrift


def main(argv=None):
    parser=argparse.ArgumentParser(description='Apply Wave 2.5 + 2.6 verified publication fixes')
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='perform writes; default is dry run')
    ns=parser.parse_args(argv)
    try:
        out=apply(ns.repo,apply_changes=ns.apply)
        print(json.dumps(out,indent=2))
        return 0
    except (OSError,SourceDrift,ValueError) as ex:
        print(json.dumps({'status':'BLOCK','reason':str(ex)},indent=2))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
