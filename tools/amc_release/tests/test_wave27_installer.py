from pathlib import Path
import pytest
from install_wave27 import apply,NEW

SOURCE=Path(__file__).resolve().parents[3]

@pytest.fixture
def checkout(tmp_path):
    (tmp_path/'.git').mkdir()
    (tmp_path/'backend').mkdir()
    (tmp_path/'mf-context-engine').mkdir()
    return tmp_path


def test_dry_run_has_no_write(checkout):
    before=list(checkout.rglob('*'))
    report=apply(SOURCE,checkout)
    assert report['status']=='DRY_RUN' and report['wave27_new']==len(NEW)
    assert list(checkout.rglob('*'))==before


def test_cumulative_fresh_install(checkout):
    r=apply(SOURCE,checkout,write=True)
    assert r['status']=='ADDITIVE_FILES_APPLIED_REVIEW_REQUIRED'
    assert (checkout/'backend/amc_publication/serving27.py').exists()
    assert (checkout/'tools/amc_release/publication_patch26.py').exists()
    assert (checkout/'.github/workflows/amc-wave27-integration.yml').exists()
    # A cumulative installer MUST NOT silently modify the existing core source.
    assert not (checkout/'backend/amc_publication/worker.py').exists()
    assert not (checkout/'backend/app/main.py').exists()


def test_reinstall_identical_is_idempotent(checkout):
    apply(SOURCE,checkout,write=True)
    r=apply(SOURCE,checkout)
    assert r['wave27_new']==0


def test_unreviewed_existing_file_refuses_all_changes(checkout):
    dest=checkout/'backend/amc_publication/serving27.py'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text('untrusted changes')
    with pytest.raises(FileExistsError):apply(SOURCE,checkout,write=True)
    assert not (checkout/'backend/amc_publication/faiss_reader27.py').exists()


def test_destination_symlink_outside_checkout_refused(checkout,tmp_path):
    target=tmp_path.parent/'outside_amc.test'
    target.write_text('test')
    dest=checkout/'backend/amc_publication/serving27.py'
    dest.parent.mkdir(parents=True,exist_ok=True)
    try: dest.symlink_to(target)
    except (OSError,NotImplementedError):pytest.skip('symlink unavailable on host')
    with pytest.raises(ValueError):apply(SOURCE,checkout,write=True)
    assert target.read_text()=='test'


def test_real_checkout_is_required(tmp_path):
    with pytest.raises(ValueError):apply(SOURCE,tmp_path)


def test_installer_never_changes_current_repo_baseline_source(checkout):
    core=checkout/'backend/amc_publication/worker.py'
    core.parent.mkdir(parents=True,exist_ok=True)
    core.write_text('source protected')
    apply(SOURCE,checkout,write=True)
    assert core.read_text()=='source protected'


def test_all_new_file_destinations_are_unique():
    assert len(NEW)==len(set(NEW))
    assert all('..' not in Path(x).parts for x in NEW)
