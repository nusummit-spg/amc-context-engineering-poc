from pathlib import Path
from types import SimpleNamespace
import pytest
import install_wave30 as inst
from tools.amc_release import apply_all30


def repo_tree(tmp_path):
    repo=tmp_path/'repo'
    for p in ('.git','backend','mf-context-engine'):(repo/p).mkdir(parents=True)
    return repo


def test_invalid_repo_cannot_install(tmp_path):
    with pytest.raises(ValueError,match='actual AMC'):
        inst.install(tmp_path,tmp_path)


def test_installer_never_overwrites_existing_target(tmp_path,monkeypatch):
    repo=repo_tree(tmp_path)
    bundle=tmp_path/'bundle';bundle.mkdir()
    for rel in inst.ADDITIONS:
        p=bundle/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('file')
    target=repo/inst.ADDITIONS[0];target.parent.mkdir(parents=True,exist_ok=True);target.write_text('different')
    monkeypatch.setattr(inst,'_prior',lambda bundle:SimpleNamespace(install=lambda *a,**kw:{'status':'DRY_RUN'}))
    with pytest.raises(FileExistsError,match='refuse overwrite'):
        inst.install(bundle,repo)
    assert target.read_text()=='different'


def test_installer_dry_run_is_non_destructive(tmp_path,monkeypatch):
    repo=repo_tree(tmp_path)
    bundle=tmp_path/'bundle';bundle.mkdir()
    for rel in inst.ADDITIONS:
        p=bundle/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('file')
    monkeypatch.setattr(inst,'_prior',lambda bundle:SimpleNamespace(install=lambda *a,**kw:{'status':'DRY_RUN'}))
    out=inst.install(bundle,repo)
    assert out['status']=='DRY_RUN' and out['new_files']==len(inst.ADDITIONS)
    assert not any((repo/rel).exists() for rel in inst.ADDITIONS)


def test_bootstrap_allows_dry_run_without_mutation(tmp_path,monkeypatch):
    expected={'status':'ALL_SOURCE_PATCHES_REHEARSED_NO_WRITES','sha':'X'}
    monkeypatch.setattr(apply_all30,'preflight',lambda *a,**k:expected)
    assert apply_all30.run(tmp_path,tmp_path)==expected


def test_bootstrap_partial_prior_failure_does_not_claim_release(tmp_path,monkeypatch):
    monkeypatch.setattr(apply_all30,'preflight',lambda *a,**k:{'sha':'base'})
    monkeypatch.setattr(apply_all30,'run29',lambda *a,**k:{'status':'BLOCKED_PARTIAL_LOCAL_BRANCH'})
    report=apply_all30.run(tmp_path,tmp_path,apply=True)
    assert report['release']=='BLOCKED'
    assert report['status']=='BLOCKED_PARTIAL_BRANCH'


def test_qualification_fails_closed_on_unpatched_repository(tmp_path):
    from tools.amc_release.qualification30 import inspect
    report=inspect(tmp_path)
    assert report['status']=='BLOCKED'
    assert report['release_decision']=='BLOCKED'
    assert not report['uat_authorized']
    assert 'backend/amc_publication/worker.py' in report['source_blockers']


def test_qualification_never_invents_live_results(tmp_path):
    from tools.amc_release.qualification30 import inspect
    report=inspect(tmp_path)
    assert all(v=='NOT_RUN' for v in report['unexecuted_gates'].values())
    assert 'canary_rollback' in report['unexecuted_gates']
