from pathlib import Path
from tools.amc_release import app_wiring27 as m
import pytest

APP='''from fastapi import FastAPI

def create_app():
    app = FastAPI()
    app.include_router(audit.router, prefix="/api")
    return app
'''


def test_status_router_is_registered_once_without_extra_prefix():
    out=m.render(APP)
    assert 'app.include_router(publication_status_router)' in out
    assert 'app.include_router(publication_status_router, prefix="/api")' not in out
    assert out.count('app.include_router(audit.router')==1


def test_insertion_is_after_audit_router_registration():
    out=m.render(APP)
    assert out.index('app.include_router(audit.router')<out.index('app.include_router(publication_status_router)')<out.index('return app')


def test_second_application_patch_refused():
    with pytest.raises(m.SourceDrift):m.render(m.render(APP))


def test_missing_or_ambiguous_anchor_refused():
    for source in (APP.replace(m.ANCHOR,''),APP.replace(m.ANCHOR,m.ANCHOR*2)):
        with pytest.raises(m.SourceDrift):m.render(source)


def test_patcher_requires_git_checkout(tmp_path):
    p=tmp_path/'backend/app';p.mkdir(parents=True)
    (p/'main.py').write_text(APP)
    with pytest.raises(m.SourceDrift):m.patch(tmp_path)


def test_explicit_blob_check_and_backup(tmp_path):
    (tmp_path/'.git').mkdir()
    p=tmp_path/'backend/app';p.mkdir(parents=True)
    main=p/'main.py';main.write_text(APP)
    observed=m.git_blob(main.read_bytes())
    dry=m.patch(tmp_path,expected_blob=observed)
    assert dry['status']=='DRY_RUN' and main.read_text()==APP
    done=m.patch(tmp_path,apply=True,expected_blob=observed)
    assert done['status']=='APPLIED_REVIEW_REQUIRED'
    assert (p/'main.py.wave27.bak').read_text()==APP
    assert 'W27_PUBLICATION_STATUS_ROUTER' in main.read_text()


def test_repatch_or_drift_is_blocked(tmp_path):
    (tmp_path/'.git').mkdir()
    p=tmp_path/'backend/app';p.mkdir(parents=True)
    main=p/'main.py';main.write_text(APP)
    observed=m.git_blob(main.read_bytes())
    main.write_text(APP+'# unexpected edit\n')
    with pytest.raises(m.SourceDrift,match='source drift'):m.patch(tmp_path,expected_blob=observed)


def test_crlf_fails_closed(tmp_path):
    (tmp_path/'.git').mkdir()
    p=tmp_path/'backend/app';p.mkdir(parents=True)
    main=p/'main.py';main.write_bytes(APP.replace('\n','\r\n').encode())
    with pytest.raises(m.SourceDrift,match='CRLF'):m.patch(tmp_path,expected_blob=m.git_blob(main.read_bytes()))
