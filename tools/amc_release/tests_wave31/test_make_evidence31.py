"""The evidence builder must never turn a failed, skipped or missing test run into a PASS."""
import json
import subprocess

from tools.amc_release import make_evidence31 as me


def _repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.email=t@e.org", "-c", "user.name=T", "commit", "--allow-empty", "-qm", "i"],
                   cwd=d, check=True)
    return d


def _junit(path, cases):
    body = "".join(
        f'<testcase classname="tests.live31.{mod}" name="{name}">{inner}</testcase>' for mod, name, inner in cases)
    path.write_text(f"<testsuite>{body}</testsuite>")
    return path


def test_all_passing_modules_produce_pass_records(tmp_path):
    repo = _repo(tmp_path)
    j = _junit(tmp_path / "j.xml", [("test_pg_migration31", "a", ""), ("test_pg_migration31", "b", "")])
    r = me.build(j, repo, tmp_path / "out")
    assert r["written"] == ["alembic_postgresql_014"]
    rec = json.loads((tmp_path / "out" / "alembic_postgresql_014.json").read_text())
    assert rec["status"] == "PASS" and rec["commit_sha"] == r["commit_sha"] and len(rec["commit_sha"]) == 40
    assert "not staging" in rec["environment"]["scope"]


def test_a_failure_a_skip_or_missing_results_never_pass(tmp_path):
    repo = _repo(tmp_path)
    j = _junit(tmp_path / "j.xml", [
        ("test_publication_live31", "ok", ""),
        ("test_publication_live31", "bad", "<failure message='x'/>"),
        ("test_faiss_serving_live31", "blocked", "<skipped message='LIVE31_BLOCKED: no pg'/>"),
    ])
    r = me.build(j, repo, tmp_path / "out")
    assert r["written"] == []
    assert "failed" in r["not_written"]["postgresql_first_publisher_race"]
    assert "blocked" in r["not_written"]["faiss_receipt_rollback"]
    assert r["not_written"]["authenticated_negative_routes"] == "no test results found"
    assert not list((tmp_path / "out").glob("*.json"))


def test_a_pinned_expected_failure_does_not_block_a_gate(tmp_path):
    repo = _repo(tmp_path)
    j = _junit(tmp_path / "j.xml", [
        ("test_pg_migration31", "a", ""),
        ("test_pg_migration31", "sqlite", "<skipped type='pytest.xfail' message='PRE-EXISTING'/>"),
    ])
    assert me.build(j, repo, tmp_path / "out")["written"] == ["alembic_postgresql_014"]


def test_gates_that_junit_cannot_prove_are_never_written():
    assert not {"staging_smoke", "canary_rollback_slo", "backend_integration", "frontend_build_browser"} \
        & set(me.GATE_MODULES)
