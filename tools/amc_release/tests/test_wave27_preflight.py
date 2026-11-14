import subprocess
from pathlib import Path
import pytest
from tools.amc_release import preflight27 as m


def call(repo,*args):
    p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return p.stdout.strip()

@pytest.fixture
def gitrepo(tmp_path):
    call(tmp_path,'init','-q')
    call(tmp_path,'config','user.email','test@example.com')
    call(tmp_path,'config','user.name','Test')
    (tmp_path/'README').write_text('test')
    call(tmp_path,'add','README');call(tmp_path,'commit','-qm','base')
    base=call(tmp_path,'rev-parse','HEAD')
    call(tmp_path,'switch','-qc','feature/amc-release-candidate-hardening')
    return tmp_path,base


def test_nonrepo_is_blocked(tmp_path):
    assert m.assess(tmp_path)['reasons']==['NOT_A_GIT_CHECKOUT']


def test_unintegrated_checkout_reports_missing_all_source(gitrepo):
    root,base=gitrepo
    outcome=m.assess(root,expected_base=base)
    assert outcome['status']=='BLOCK' and len([r for r in outcome['reasons'] if r.startswith('SOURCE_NOT_INTEGRATED')])==len(m.FILES)


def test_main_branch_is_rejected(gitrepo):
    root,base=gitrepo
    call(root,'switch','-q','master')
    assert 'REVIEW_FEATURE_BRANCH_REQUIRED' in m.assess(root,expected_base=base)['reasons']


def test_base_not_ancestor_blocked(gitrepo):
    root,base=gitrepo
    assert 'REVIEWED_BASE_NOT_ANCESTOR_OF_HEAD' in m.assess(root,expected_base='f'*40)['reasons']


def test_source_checks_are_readonly_and_explicit(gitrepo):
    root,base=gitrepo
    for rel,marker in m.FILES.items():
        dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        if rel.endswith('main.py'):dst.write_text('# '+marker+'\n')
        else:dst.write_text('# '+marker+'\n')
    report=m.assess(root,expected_base=base)
    assert report['status']=='SOURCE_REVIEW_REQUIRED'
    assert report['uat']=='BLOCK'
    assert all(report['checks'][rel]=='PRESENT' for rel in m.FILES)
    assert len(report['external_requirements'])==4


def test_syntax_error_blocks_even_with_marker(gitrepo):
    root,base=gitrepo
    rel='backend/amc_publication/worker.py';dst=root/rel;dst.parent.mkdir(parents=True)
    dst.write_text('def broken(\n# '+m.FILES[rel])
    out=m.assess(root,expected_base=base)
    assert out['checks'][rel]=='INVALID_PYTHON'


def test_backup_files_are_rejected(gitrepo):
    root,base=gitrepo
    (root/'worker.py.wave27.bak').write_text('snapshot')
    assert 'SENSITIVE_OR_BACKUP_CHANGE_IN_WORKTREE' in m.assess(root,expected_base=base)['reasons']


def test_does_not_write_git_or_source_files(gitrepo):
    root,base=gitrepo
    before=sorted(root.rglob('*'))
    m.assess(root,expected_base=base)
    assert before==sorted(root.rglob('*'))
