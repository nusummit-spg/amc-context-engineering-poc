from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from tools.amc_release import apply_all29 as b


def test_single_combined_source_patch_no_duplicate_wave25():
    keys=[name for name,_ in b.STEPS]
    assert keys==['install','combined_25_26','route_27','authority_28','ingress_29','compile','tests_29']
    assert all('publication_patch25_cli' not in ' '.join(args) for _,args in b.STEPS)


def test_missing_real_checkout_is_refused(tmp_path):
    with pytest.raises(ValueError):b.run(tmp_path,tmp_path)


def test_refuses_unreviewed_commit(tmp_path,monkeypatch):
    repo=tmp_path/'repo'
    for d in (repo/'.git',repo/'backend',repo/'mf-context-engine'):d.mkdir(parents=True)
    bundle=tmp_path/'bundle';bundle.mkdir();(bundle/'install_wave29.py').write_text('')
    monkeypatch.setattr(b.subprocess,'check_output',lambda *a,**k:'wrong-sha\n')
    with pytest.raises(ValueError,match='differs'):b.run(repo,bundle)


def test_refuses_dirty_checkout(tmp_path,monkeypatch):
    repo=tmp_path/'repo'
    for d in (repo/'.git',repo/'backend',repo/'mf-context-engine'):d.mkdir(parents=True)
    bundle=tmp_path/'bundle';bundle.mkdir();(bundle/'install_wave29.py').write_text('')
    def fake(command,**kwargs):
        if command[3]=='rev-parse':return b.BASE
        if command[3]=='status':return ' M backend/app/main.py'
        return ''
    monkeypatch.setattr(b.subprocess,'check_output',fake)
    with pytest.raises(ValueError,match='uncommitted'):b.run(repo,bundle)
