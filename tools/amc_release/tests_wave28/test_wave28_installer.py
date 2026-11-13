from pathlib import Path
import pytest
from install_wave28 import install, ADDITIONS
from tools.amc_release.release_audit28 import inspect
ROOT=Path(__file__).resolve().parents[3]

@pytest.fixture
def repo(tmp_path):
    (tmp_path/'.git').mkdir();(tmp_path/'backend').mkdir();(tmp_path/'mf-context-engine').mkdir()
    return tmp_path

def test_installer_additive_and_dry_run(repo):
    report=install(ROOT,repo)
    assert report['status']=='DRY_RUN' and report['wave28_new_files']==len(ADDITIONS)
    assert not (repo/'backend/amc_publication/active_authority28.py').exists()
    result=install(ROOT,repo,apply_changes=True)
    assert result['status']=='ADDITIVE_INSTALLED_NOT_RELEASE_APPROVED'
    assert (repo/'backend/amc_publication/active_authority28.py').exists()
    assert not (repo/'backend/amc_publication/journal.py').exists()
    assert install(ROOT,repo)['wave28_new_files']==0


def test_existing_different_file_refused_without_partial_copy(repo):
    f=repo/'backend/amc_publication/active_authority28.py';f.parent.mkdir(parents=True)
    f.write_text('untrusted source')
    with pytest.raises(FileExistsError):install(ROOT,repo,apply_changes=True)
    assert not (repo/'tools/amc_release/active_cutover28.py').exists()


def test_symlink_escape_refused(repo,tmp_path):
    f=tmp_path.parent/'outside_wave28.txt';f.write_text('sensitive')
    dest=repo/'backend/amc_publication/active_authority28.py'
    dest.parent.mkdir(parents=True)
    try:dest.symlink_to(f)
    except (OSError,NotImplementedError):pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError):install(ROOT,repo,apply_changes=True)
    assert f.read_text()=='sensitive'


def test_install_requires_checkout(tmp_path):
    with pytest.raises(ValueError):install(ROOT,tmp_path)


def test_allowlist_has_no_escape_or_duplicates():
    assert len(ADDITIONS)==len(set(ADDITIONS))
    assert all('..' not in Path(x).parts and not Path(x).is_absolute() for x in ADDITIONS)
    assert all((ROOT/x).exists() for x in ADDITIONS)


def test_source_audit_blocks_missing_integration(repo):
    report=inspect(repo)
    assert report['source_audit']=='BLOCKED' and report['release_gate']=='BLOCKED'
    assert len(report['failures'])>=6


def test_source_audit_never_reports_live_system_pass(repo):
    report=inspect(repo)
    assert report['live_neo4j']=='NOT_RUN' and report['postgresql_concurrency']=='NOT_RUN'
    assert report['uat']=='NOT_RUN'
