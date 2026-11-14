from pathlib import Path
import pytest
from tools.amc_release.pytest_matrix27 import selected,main


def scaffold(tmp_path):
    for rel in ('tools/amc_release/tests/test_wave27_one.py',
                'backend/tests/test_wave19_one.py','backend/tests/test_wave20_one.py'):
        file=tmp_path/rel
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text('def test_example(): pass\n')
    return tmp_path


def test_all_three_categories_required(tmp_path):
    root=scaffold(tmp_path)
    assert sorted(selected(root))==['wave19','wave20','wave27']
    assert sum(map(len,selected(root).values()))==3


def test_missing_category_refused(tmp_path):
    root=scaffold(tmp_path)
    (root/'backend/tests/test_wave20_one.py').unlink()
    with pytest.raises(ValueError,match='wave20'):selected(root)


def test_symlink_test_not_accepted(tmp_path):
    root=scaffold(tmp_path)
    orig=root/'backend/tests/test_wave19_one.py'
    orig.unlink()
    try:orig.symlink_to(root/'backend/tests/test_wave20_one.py')
    except (OSError,NotImplementedError):pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError,match='wave19'):selected(root)


def test_list_only_does_not_execute(tmp_path):
    root=scaffold(tmp_path)
    assert main(['--repo',str(root),'--list-only'])==0
    assert not (root/'wave27-matrix.xml').exists()


def test_missing_repo_returns_block(tmp_path):
    assert main(['--repo',str(tmp_path),'--list-only'])==2


def test_actual_package_has_required_historical_inputs():
    root=Path(__file__).resolve().parents[3]
    assert any(root.glob('tools/amc_release/tests/test_wave27_*.py'))
    assert any(root.glob('test_support/baseline/backend/tests/test_wave19_*.py'))
