"""Standalone safe-installer regression for fresh and Wave 2.5 existing checkouts."""
import pytest
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('install_wave26', ROOT/'install_wave26.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

@pytest.fixture
def checkout(tmp_path):
    (tmp_path/'.git').mkdir();(tmp_path/'backend').mkdir();(tmp_path/'mf-context-engine').mkdir()
    return tmp_path


def test_fresh_install_dry_run_and_apply(checkout):
    first=mod.install(ROOT,checkout)
    assert first['status']=='DRY_RUN' and first['new']>30
    assert not (checkout/'backend/amc_publication/catalog26.py').exists()
    result=mod.install(ROOT,checkout,apply_changes=True)
    assert result['new']==first['new']
    assert (checkout/'backend/amc_publication/catalog26.py').exists()
    assert (checkout/'tools/amc_release/publication_patch26.py').exists()
    assert mod.install(ROOT,checkout)['same']==first['new']


def test_previously_installed_wave25_upgrades_are_explicit(checkout):
    mod.install(ROOT,checkout,apply_changes=True)
    path=checkout/'tools/amc_release/tests/test_wave25_adapter.py'
    prior=ROOT/'test_support/prior_wave25/test_wave25_adapter.py'
    assert prior.is_file()
    path.write_bytes(prior.read_bytes())
    with pytest.raises(FileExistsError):mod.install(ROOT,checkout)
    dry=mod.install(ROOT,checkout,upgrade_wave25=True)
    assert dry['status']=='DRY_RUN' and dry['upgrades']==1
    assert not Path(str(path)+'.wave26.bak').exists()
    applied=mod.install(ROOT,checkout,apply_changes=True,upgrade_wave25=True)
    assert applied['upgrades']==1
    assert path.read_bytes()==(ROOT/'tools/amc_release/tests/test_wave25_adapter.py').read_bytes()
    assert Path(str(path)+'.wave26.bak').read_bytes()==prior.read_bytes()


def test_any_unreviewed_conflicting_source_fails_closed(checkout):
    dst=checkout/'backend/amc_publication/catalog26.py';dst.parent.mkdir(parents=True)
    dst.write_text('unsafe external version')
    with pytest.raises(FileExistsError):mod.install(ROOT,checkout,apply_changes=True)
    assert not (checkout/'tools/amc_release/publication_patch26.py').exists()


def test_refuse_symlink_parent(checkout,tmp_path):
    outside=tmp_path.parent/'amc-wave26-outside';outside.mkdir(exist_ok=True)
    (checkout/'tools').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):mod.install(ROOT,checkout,apply_changes=True)


def test_missing_checkout_refused(tmp_path):
    with pytest.raises(ValueError):mod.install(ROOT,tmp_path)
