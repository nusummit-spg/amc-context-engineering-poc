from pathlib import Path
import pytest
from tools.amc_release import assurance30
from tools.amc_release.app_wiring27 import git_blob

BROKEN='''name: AMC Assurance Pipeline
on: [push]
jobs:
  fault-injection:
    runs-on: ubuntu-latest
    steps:
      - name: Run fault injection tests
         run: |
          echo test
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Collect
        run: |
          python -m pytest tests/ --collect-only -q 2>&1 | tail -20 || true
      - name: SLO
        run: |
          echo "Checking SLO metrics (placeholder - requires actual metrics collection)"
      - name: Canary
        run: |
          echo "Canary deployment requires a real staging environment."
'''


def test_assurance_repairs_real_root_cause_and_masks():
    raw=BROKEN.encode()
    result=assurance30.render(raw,expected_blob=git_blob(raw)).decode()
    assert '      - name: Run fault injection tests\n        run: |' in result
    assert '|| true' not in result
    assert 'FB05: live 1h/24h telemetry proof not configured' in result
    assert 'GATE05: real canary not configured' in result
    assert result.count('exit 1')==2


def test_assurance_rejects_unknown_or_modified_workflow():
    with pytest.raises(assurance30.Assurance30Error,match='drift'):
        assurance30.render(BROKEN.encode())


def test_assurance_without_repo_is_rejected(tmp_path):
    with pytest.raises(assurance30.Assurance30Error,match='checkout'):
        assurance30.patch(tmp_path)


def test_assurance_patch_dry_run_does_not_change(tmp_path):
    (tmp_path/'.git').mkdir()
    target=tmp_path/assurance30.RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text(BROKEN,newline='\n')
    info=assurance30.patch(tmp_path,expected_blob=git_blob(BROKEN.encode()))
    assert info['status']=='DRY_RUN'
    assert target.read_text()==BROKEN
    assert not target.with_name(target.name+'.wave30.bak').exists()


def test_assurance_patch_can_apply_and_backup(tmp_path):
    (tmp_path/'.git').mkdir()
    target=tmp_path/assurance30.RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text(BROKEN,newline='\n')
    info=assurance30.patch(tmp_path,apply=True,expected_blob=git_blob(BROKEN.encode()))
    assert info['status']=='APPLIED_REVIEW_REQUIRED'
    assert target.with_name(target.name+'.wave30.bak').read_text()==BROKEN
    assert '|| true' not in target.read_text()
    with pytest.raises(assurance30.Assurance30Error):
        assurance30.patch(tmp_path,apply=True,expected_blob=git_blob(BROKEN.encode()))
