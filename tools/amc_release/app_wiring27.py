"""Minimal source-locked activation of the publication status router in FastAPI.

Does not change existing governance, database or retrieval routes. Does not
claim that the legacy vector reader uses VerifiedFaissRetriever yet.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import difflib
import shutil

REVIEWED_APP_MAIN_BLOB = 'ab3722cda2823b54ab62ceef253b5efd428f2095'
RELATIVE = 'backend/app/main.py'
ANCHOR = '    app.include_router(audit.router, prefix="/api")\n'
INJECTION = '''    # W27_PUBLICATION_STATUS_ROUTER: path already includes /api/publication.
    # JWT/tenant checks are enforced by the Wave 2.6 status route itself.
    from amc_publication.status_route import router as publication_status_router
    app.include_router(publication_status_router)
'''

class SourceDrift(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def render(original: str) -> str:
    if 'W27_PUBLICATION_STATUS_ROUTER' in original:
        raise SourceDrift('application router already patched')
    if original.count(ANCHOR) != 1:
        raise SourceDrift('expected unique app startup router registration')
    newer=original.replace(ANCHOR,ANCHOR+INJECTION,1)
    compile(newer,RELATIVE,'exec')
    return newer


def patch(repo: Path, *, apply: bool = False, expected_blob: str = REVIEWED_APP_MAIN_BLOB) -> dict:
    root=Path(repo).resolve()
    file=root/RELATIVE
    if not (root/'.git').is_dir() or not file.is_file() or file.is_symlink():
        raise SourceDrift('requires real Git checkout with safe app.main')
    data=file.read_bytes()
    observed=git_blob(data)
    if observed != expected_blob:
        raise SourceDrift(f'app.main source drift; expected {expected_blob} observed {observed}')
    # Preserve all original bytes, no implicit reformatting or newline conversion.
    if b'\r\n' in data:
        raise SourceDrift('unexpected CRLF main.py; review before applying')
    old=data.decode('utf-8')
    new=render(old)
    backup=file.with_name(file.name+'.wave27.bak')
    if apply:
        if backup.exists():
            raise SourceDrift('prior backup exists; refusing overwrite')
        shutil.copy2(file,backup)
        try:
            file.write_bytes(new.encode('utf-8'))
        except BaseException:
            shutil.copy2(backup,file)
            raise
    return {'status':'APPLIED_REVIEW_REQUIRED' if apply else 'DRY_RUN',
            'source_git_blob':observed,
            'target_sha256':hashlib.sha256(new.encode()).hexdigest(),
            'diff':''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
                      fromfile='a/'+RELATIVE,tofile='b/'+RELATIVE))}
