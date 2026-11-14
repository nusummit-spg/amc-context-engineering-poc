from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
import install_wave29 as installer


@pytest.fixture
def work(tmp_path,monkeypatch):
    repo=tmp_path/'repo'
    for directory in (repo/'.git',repo/'backend',repo/'mf-context-engine'):
        directory.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).resolve().parents[3]
    fake=SimpleNamespace(install=lambda *args,**kwargs:{'status':'DRY_RUN'})
    monkeypatch.setattr(installer,'_prev',lambda x:fake)
    return source,repo


def test_installer_dry_run_is_nonmutating(work):
    source,repo=work
    data=installer.install(source,repo)
    assert data['new_file_count']==len(installer.ADDITIONS)
    assert data['release_approved'] is False
    assert not (repo/'backend/amc_publication/ingestion_boundary29.py').exists()


def test_installer_creates_only_allowlisted_paths(work):
    source,repo=work
    result=installer.install(source,repo,apply=True)
    assert result['status']=='ADDITIVE_FILES_INSTALLED_SOURCE_PATCH_PENDING'
    for path in installer.ADDITIONS:
        assert (repo/path).read_bytes()==(source/path).read_bytes()
    assert installer.install(source,repo)['new_file_count']==0


def test_installer_refuses_existing_modified_source(work):
    source,repo=work
    target=repo/installer.ADDITIONS[0];target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('tampered')
    with pytest.raises(FileExistsError):installer.install(source,repo,apply=True)
    assert target.read_text()=='tampered'


def test_installer_rejects_symlink_target(work,tmp_path):
    source,repo=work
    out=tmp_path/'outside';out.write_text('hidden')
    target=repo/installer.ADDITIONS[0];target.parent.mkdir(parents=True,exist_ok=True)
    target.symlink_to(out)
    with pytest.raises(ValueError):installer.install(source,repo)
    assert out.read_text()=='hidden'


def test_installer_requires_full_checkout(tmp_path):
    with pytest.raises(ValueError):installer.install(tmp_path,tmp_path)
