"""Manual-only, non-activating import of canonical chunk candidates into quarantine.

Example: python -m tools.amc_release.quarantine29 --source candidate.json --root ./data/quarantine [--apply]
The actor and count in an input file are NOT independently authenticated;
this is staging evidence, not publication approval or a canonical catalog.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from amc_publication.ingestion_boundary29 import (ImmutableIngestionQuarantine29,
    IngestionQuarantineError, _strict_documents)
from amc_publication.types import canonical_bytes


def run(source:Path,root:Path,*,apply:bool=False) -> dict:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 50*1024*1024:
        raise IngestionQuarantineError('regular bounded input file required')
    try:
        obj=json.loads(source.read_bytes())
    except (ValueError,UnicodeDecodeError) as ex:
        raise IngestionQuarantineError('invalid input JSON') from ex
    if not isinstance(obj,dict) or set(obj)!={'tenant','source_version','batch_id','submitted_by','documents'}:
        raise IngestionQuarantineError('expected exact candidate record shape')
    docs=_strict_documents(obj['tenant'],obj['documents'])
    if any(d['source_version']!=obj['source_version'] for d in docs):
        raise IngestionQuarantineError('mixed source versions')
    if not apply:
        if not all(isinstance(obj[k],str) and obj[k].strip() and len(obj[k])<=256
                   for k in ('source_version','batch_id','submitted_by')):
            raise IngestionQuarantineError('batch/actor/version required')
        return {'state':'DRY_RUN_VALIDATED_UNAPPROVED', 'count':len(docs),
                'tenant':obj['tenant'], 'no_publication_side_effect':True}
    return ImmutableIngestionQuarantine29(root).stage(**obj)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--source',required=True,type=Path)
    cli.add_argument('--root',required=True,type=Path)
    cli.add_argument('--apply',action='store_true',help='write unapproved immutable quarantine candidate')
    args=cli.parse_args()
    try:
        print(json.dumps(run(args.source,args.root,apply=args.apply),indent=2))
        return 0
    except (IngestionQuarantineError,OSError,TypeError,ValueError) as ex:
        print(json.dumps({'state':'BLOCKED','error':str(ex)}))
        return 2
if __name__=='__main__':raise SystemExit(main())
