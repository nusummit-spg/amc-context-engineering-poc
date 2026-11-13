from pathlib import Path
import importlib.util
import shutil
import hashlib
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('install_wave25',ROOT/'install_wave25.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

@pytest.fixture
def repo(tmp_path):
    (tmp_path/'.git').mkdir()
    (tmp_path/'backend').mkdir()
    (tmp_path/'mf-context-engine').mkdir()
    return tmp_path

def test_fresh_install_dry_run_then_apply(repo):
    first=installer.install(ROOT,repo)
    assert first['status']=='DRY_RUN' and first['files_new']>20
    assert not (repo/'tools/amc_release/publication_patch25.py').exists()
    applied=installer.install(ROOT,repo,apply_changes=True)
    assert applied['files_new']==first['files_new']
    assert (repo/'backend/amc_publication/approval_adapter.py').is_file()
    assert (repo/'tools/amc_release/publication_patch25_cli.py').is_file()
    assert installer.install(ROOT,repo)['files_same']==first['files_new']

def test_pinned_wave24_upgrade_preserves_backup(repo):
    installer.install(ROOT,repo,apply_changes=True)
    workflow=repo/installer.WORKFLOW
    old=ROOT/'tools/amc_release/tests/fixtures/wave24_release_verification.yml'
    assert hashlib.sha256(old.read_bytes()).hexdigest()==installer.OLD_W24_WORKFLOW_SHA256
    shutil.copy2(old,workflow)
    with pytest.raises(FileExistsError):installer.install(ROOT,repo)
    summary=installer.install(ROOT,repo,upgrade_wave24=True)
    assert summary['known_wave24_upgrade']==1 and not (repo/(installer.WORKFLOW+'.wave25.bak')).exists()
    installer.install(ROOT,repo,apply_changes=True,upgrade_wave24=True)
    assert (repo/(installer.WORKFLOW+'.wave25.bak')).read_bytes()==old.read_bytes()
    assert workflow.read_bytes()==(ROOT/installer.WORKFLOW).read_bytes()

def test_unrecognized_workflow_never_overwritten(repo):
    installer.install(ROOT,repo,apply_changes=True)
    workflow=repo/installer.WORKFLOW
    workflow.write_text('unrecognized file')
    with pytest.raises(FileExistsError):installer.install(ROOT,repo,apply_changes=True,upgrade_wave24=True)
    assert workflow.read_text()=='unrecognized file'

def test_preflight_all_files_before_writes(repo):
    target=repo/'tools/amc_release/ledger.py'
    target.parent.mkdir(parents=True)
    target.write_text('conflicting version')
    with pytest.raises(FileExistsError):installer.install(ROOT,repo,apply_changes=True)
    assert not (repo/'backend/amc_publication/approval_adapter.py').exists()

def test_missing_git_checkout_refused(tmp_path):
    (tmp_path/'backend').mkdir();(tmp_path/'mf-context-engine').mkdir()
    with pytest.raises(ValueError):installer.install(ROOT,tmp_path)

def test_symlink_escape_refused(repo,tmp_path):
    outside=tmp_path.parent/'escape-outside'
    outside.mkdir(exist_ok=True)
    try:
        (repo/'tools').symlink_to(outside,target_is_directory=True)
    except OSError:
        pytest.skip('Host does not permit directory symlink creation')
    with pytest.raises(ValueError):installer.install(ROOT,repo,apply_changes=True)
