"""Branch policy for the exact-SHA evidence collector. No service access required."""
import subprocess
import pytest
from tools.amc_release import collect_local_evidence31 as collector


def test_both_wave31_lineage_branches_are_accepted():
    assert "feature/amc-wave31-integration" in collector.ALLOWED_BRANCHES
    assert "amc-dev-wave31-integration" in collector.ALLOWED_BRANCHES


@pytest.mark.parametrize("name", ["main", "amc-dev", "feature/other", ""])
def test_protected_and_unrelated_branches_are_not_accepted(name):
    assert name not in collector.ALLOWED_BRANCHES


def test_collector_rejects_unrelated_branch(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "tools" / "amc_release").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    run("init", "-q", "-b", "scratch-branch")
    run("-c", "user.email=t@example.org", "-c", "user.name=T", "commit", "--allow-empty", "-qm", "i")
    with pytest.raises(SystemExit) as exc:
        collector.main(["--repo", str(repo), "--out-dir", str(tmp_path / "out")])
    assert exc.value.code == 2
