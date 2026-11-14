"""No branch creation or writes on incomplete/unverified checkouts."""
from pathlib import Path
import pytest
from tools.amc_release.apply_all31 import preflight31,run
from tools.amc_release.governance_guard31 import patch as patch_guard
from install_wave31 import install


def test_no_fake_repo_is_accepted(tmp_path):
    bundle=Path(__file__).resolve().parents[3]
    with pytest.raises((ValueError,OSError)):
        preflight31(tmp_path,bundle)
    with pytest.raises((ValueError,OSError)):
        run(tmp_path,bundle,apply=True)
    assert not (tmp_path/'.git').exists()


def test_guard_does_not_write_if_repo_missing(tmp_path):
    with pytest.raises(ValueError):patch_guard(tmp_path,apply=True)
    assert list(tmp_path.iterdir())==[]


def test_install31_requires_complete_repo_and_no_writes(tmp_path):
    with pytest.raises(ValueError):install(Path(__file__).resolve().parents[3],tmp_path,apply=True)
    assert list(tmp_path.iterdir())==[]


def test_install31_manifest_contains_every_new_component():
    from install_wave31 import ADDITIONS
    bundle=Path(__file__).resolve().parents[3]
    assert len(ADDITIONS)==len(set(ADDITIONS))
    assert all((bundle/path).is_file() for path in ADDITIONS)
    assert 'backend/alembic/versions/014_publication_scope_claim_v31.py' in ADDITIONS
    assert '.github/workflows/amc-wave31-durable-mutation.yml' in ADDITIONS


def test_qualification31_blocks_incomplete_repo(tmp_path):
    from tools.amc_release.qualification31 import inspect
    r=inspect(tmp_path)
    assert r['status']=='BLOCKED' and r['uat']=='BLOCKED'
    assert r['live_postgresql']=='NOT_RUN'


def test_qualification31_detects_missing_legacy_guard(tmp_path):
    from tools.amc_release.qualification31 import inspect
    (tmp_path/'.git').mkdir()
    (tmp_path/'backend/app/api/routes').mkdir(parents=True)
    (tmp_path/'backend/app/api/routes/governance.py').write_text('def promote(): pass')
    r=inspect(tmp_path)
    assert 'backend/app/api/routes/governance.py' in r['wave31_blockers']
