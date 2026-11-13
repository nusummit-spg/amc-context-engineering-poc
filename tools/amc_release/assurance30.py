"""Source-locked repair of AMC's invalid and misleading assurance workflow.

Only the reviewed amc-dev 2c0415c4 workflow blob is accepted. This does NOT
turn missing staging or telemetry into a PASS: unavailable live checks fail.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from .app_wiring27 import git_blob
from .assurance_ci import harden

SOURCE_BLOB = 'c08a6c0d1ded22d87db0d474d667da8190f2ec4d'
RELATIVE = '.github/workflows/amc-assurance.yml'

class Assurance30Error(ValueError): pass

def render(raw: bytes, *, expected_blob: str = SOURCE_BLOB) -> bytes:
    if git_blob(raw) != expected_blob:
        raise Assurance30Error('AMC Assurance CI source drift: manual re-audit required')
    revised=harden(raw.decode('utf-8'))
    if revised == raw.decode('utf-8'):
        raise Assurance30Error('reviewed broken CI source expected a correction')
    try:
        import yaml
        value=yaml.safe_load(revised)
        if not isinstance(value,dict) or 'jobs' not in value or not isinstance(value['jobs'],dict):
            raise Assurance30Error('missing jobs after workflow correction')
        if 'fault-injection' not in value['jobs']:
            raise Assurance30Error('missing A05 job')
        steps=value['jobs']['fault-injection'].get('steps') or []
        if not any(s.get('name') == 'Run fault injection tests' and 'run' in s for s in steps):
            raise Assurance30Error('A05 run step still missing')
    except ImportError:
        # The release preflight must use YAML validation when PyYAML is installed.
        # GitHub will also parse the workflow on branch upload.
        if '        run: |' not in revised:
            raise Assurance30Error('A05 step is still malformed')
    return revised.encode('utf-8')

def patch(repo: Path, *, apply: bool=False, expected_blob: str=SOURCE_BLOB) -> dict:
    repo=Path(repo).resolve()
    path=repo/RELATIVE
    if not (repo/'.git').is_dir() or not path.is_file() or path.is_symlink():
        raise Assurance30Error('requires safe workflow in an AMC git checkout')
    raw=path.read_bytes()
    modified=render(raw,expected_blob=expected_blob)
    result={'status':'DRY_RUN','original_git_blob':git_blob(raw),
            'before_sha256':hashlib.sha256(raw).hexdigest(),
            'after_sha256':hashlib.sha256(modified).hexdigest(),
            'uat_approved':False,'live_slo_checked':False,'live_canary_checked':False}
    if not apply:return result
    backup=path.with_name(path.name+'.wave30.bak')
    if backup.exists() or backup.is_symlink():
        raise Assurance30Error('backup already exists; refusing overwrite')
    if path.read_bytes()!=raw:raise Assurance30Error('concurrent workflow edit detected')
    shutil.copy2(path,backup)
    try:path.write_bytes(modified)
    except BaseException:
        shutil.copy2(backup,path)
        raise
    return {**result,'status':'APPLIED_REVIEW_REQUIRED'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    try:
        print(json.dumps(patch(args.repo,apply=args.apply),indent=2))
        return 0
    except (Assurance30Error,OSError,UnicodeError,ValueError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2
if __name__=='__main__':raise SystemExit(main())
