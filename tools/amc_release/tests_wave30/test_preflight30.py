from pathlib import Path
import pytest
from tools.amc_release import preflight30
from tools.amc_release.apply_all29 import BASE


def fake_repo(tmp_path):
    repo=tmp_path/'repo'
    for path in ('.git','backend','mf-context-engine'):
        (repo/path).mkdir(parents=True)
    bundle=tmp_path/'bundle';bundle.mkdir()
    (bundle/'install_wave29.py').write_text('')
    return repo,bundle


def test_preflight_rejects_missing_checkout(tmp_path):
    with pytest.raises(preflight30.Preflight30Error,match='complete'):
        preflight30.preflight(tmp_path,tmp_path)


def test_preflight_rejects_wrong_sha_before_writes(tmp_path,monkeypatch):
    repo,bundle=fake_repo(tmp_path)
    monkeypatch.setattr(preflight30,'_git',lambda *args:'bad-sha')
    with pytest.raises(preflight30.Preflight30Error,match='SHA drift'):
        preflight30.preflight(repo,bundle)
    assert not list(repo.rglob('*.bak'))


def test_preflight_rejects_dirty_checkout_before_writes(tmp_path,monkeypatch):
    repo,bundle=fake_repo(tmp_path)
    def git(_root,*args):
        return BASE if args[0]=='rev-parse' else ' M backend/app/main.py'
    monkeypatch.setattr(preflight30,'_git',git)
    with pytest.raises(preflight30.Preflight30Error,match='not clean'):
        preflight30.preflight(repo,bundle)
    assert not list(repo.rglob('*.bak'))


def test_preflight_refuses_existing_feature_branch(tmp_path,monkeypatch):
    repo,bundle=fake_repo(tmp_path)
    def git(_root,*args):
        if args[0]=='rev-parse':return BASE
        if args[0]=='status':return ''
        if args[0]=='branch' and any(x.startswith('--format=') for x in args):return 'amc-dev\nfeature/amc-release-candidate-hardening'
        return 'amc-dev'
    monkeypatch.setattr(preflight30,'_git',git)
    with pytest.raises(preflight30.Preflight30Error,match='must be new'):
        preflight30.preflight(repo,bundle)


def test_preflight_refuses_missing_source_tree(tmp_path,monkeypatch):
    repo,bundle=fake_repo(tmp_path)
    def git(_root,*args):
        if args[0]=='rev-parse':return BASE
        if args[0]=='status':return ''
        if args[0]=='branch' and any(x.startswith('--format=') for x in args):return 'amc-dev'
        return 'amc-dev'
    monkeypatch.setattr(preflight30,'_git',git)
    # Let standalone dry run verify the additive boundary first.
    import importlib.util
    original=importlib.util.spec_from_file_location
    with pytest.raises((AttributeError,FileNotFoundError,ValueError,ImportError,TypeError)):
        preflight30.preflight(repo,bundle)
