from pathlib import Path
import argparse
import json
from .app_wiring27 import patch,SourceDrift

def main():
    parser=argparse.ArgumentParser(description='Wave27 audited FastAPI status route wiring; dry-run by default')
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        print(json.dumps(patch(args.repo,apply=args.apply),indent=2))
        return 0
    except (SourceDrift,OSError,ValueError) as exc:
        print(json.dumps({'status':'BLOCK','reason':str(exc)},indent=2))
        return 2
if __name__=='__main__':raise SystemExit(main())
