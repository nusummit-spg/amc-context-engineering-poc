"""Collect exact-commit Wave 3.1 engineering evidence without running migrations.

Run from repository root: python -m tools.amc_release.collect_local_evidence31
The script never deploys, changes Git refs, or approves MVP. npm may create ignored build files.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, timeout=15)
    return result.stdout.strip()


def count_junit(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
        cases = list(root.iter("testcase"))
        return {
            "tests": len(cases),
            "failures": sum(x.find("failure") is not None for x in cases),
            "errors": sum(x.find("error") is not None for x in cases),
            "skips": sum(x.find("skipped") is not None for x in cases),
        }
    except (OSError, ET.ParseError):
        return {"invalid_xml": True}


def run_stage(name: str, command: list[str], cwd: Path, output: Path,
              env: dict[str, str], timeout_seconds: int) -> dict:
    logfile = output / f"{name}.log"
    result = {"stage": name, "command": command, "started_at": utcnow(),
              "log_file": logfile.name, "exit_code": None}
    start = time.monotonic()
    try:
        with logfile.open("w", encoding="utf-8", errors="replace") as fh:
            completed = subprocess.run(command, cwd=cwd, env=env,
                                       stdout=fh, stderr=subprocess.STDOUT,
                                       timeout=timeout_seconds, check=False)
        result["exit_code"] = completed.returncode
    except subprocess.TimeoutExpired:
        result["error"] = f"timeout after {timeout_seconds} seconds"
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["duration_seconds"] = round(time.monotonic() - start, 2)
    result["finished_at"] = utcnow()
    result["status"] = "PASS" if result["exit_code"] == 0 else "FAIL"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--out-dir", type=Path, help="Must be outside Git checkout")
    parser.add_argument("--full-backend", action="store_true",
                        help="Run broad backend collection/regression (resource intensive)")
    parser.add_argument("--frontend", action="store_true",
                        help="Run npm ci, npm test and npm build")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.timeout_seconds < 60:
        parser.error("--timeout-seconds must be >=60")
    if not (repo / "backend").is_dir() or not (repo / "tools/amc_release").is_dir():
        parser.error("--repo is not an AMC checkout")
    try:
        sha = git(repo, "rev-parse", "HEAD")
        dirty = git(repo, "status", "--porcelain")
        branch = git(repo, "branch", "--show-current")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        parser.error(f"Git evidence unavailable: {exc}")
    if dirty:
        parser.error("Working tree must be clean. Commit fixes before exact-SHA testing")
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        parser.error("Invalid Git commit SHA")
    if branch != "feature/amc-wave31-integration":
        parser.error("Switch to feature/amc-wave31-integration before qualification")

    output = (args.out_dir or repo.parent / f"amc-wave31-evidence-{sha[:12]}").resolve()
    if output == repo or repo in output.parents:
        parser.error("Evidence directory must be OUTSIDE Git checkout")
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(output / "pycache")
    env["PYTHONPATH"] = os.pathsep.join([str(repo / "backend"), str(repo),
                                         env.get("PYTHONPATH", "")])
    # Routine source tests cannot depend on real provider data or persistent state.
    env["AMC_VERIFIED_SERVING_MODE"] = "off"
    env.pop("DATABASE_URL", None)
    env.pop("AMC_MIGRATION_DATABASE_URL", None)
    stages: list[dict] = []

    def stage(name: str, command: list[str], cwd: Path | None = None) -> None:
        print(f"[AMC] {name}: running", flush=True)
        r = run_stage(name, command, cwd or repo, output, env,
                      args.timeout_seconds)
        if name == "targeted":
            r["junit"] = count_junit(output / "targeted-junit.xml")
            if r["status"] == "PASS" and (not r["junit"] or
                not r["junit"].get("tests") or any(r["junit"].get(k, 0)
                                          for k in ("failures", "errors", "skips"))):
                r["status"] = "FAIL"
                r["error"] = "Missing/failed/skipped JUnit tests"
        stages.append(r)
        print(f"[AMC] {name}: {r['status']}", flush=True)

    py = sys.executable
    stage("compile", [py, "-m", "compileall", "-q", "backend"])
    stage("targeted", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                       "backend/tests/test_pilot_perimeter31.py",
                       "backend/tests/test_db_runtime31.py",
                       "backend/tests/test_verified_legacy_route_gates31.py",
                       "tools/amc_release/tests_wave31/test_mvp_evidence_gate31.py",
                       "--junitxml", str(output / "targeted-junit.xml")])
    stage("source-qualification", [py, "-m", "tools.amc_release.qualification31",
                                   "--repo", str(repo), "--out", str(output / "source-audit.json")])
    release = [py, "-m", "tools.amc_release.run_wave31_tests", "--root", str(repo),
               "--out", str(output / "wave31.json")]
    if args.full_backend:
        release.append("--full-backend")
    stage("wave31-tests", release)
    if args.frontend:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        for name, command in (("npm-ci", [npm, "ci"]),
                              ("frontend-test", [npm, "test"]),
                              ("frontend-build", [npm, "run", "build"])):
            stage(name, command, repo / "mf-context-engine")

    python_311 = sys.version_info[:2] == (3, 11)
    status = "PASS_SOURCE_ONLY" if python_311 and all(
        s["status"] == "PASS" for s in stages) else "BLOCKED"
    result = {
        "schema": "amc-local-qualification-31-v1", "commit_sha": sha,
        "branch": branch, "time_utc": utcnow(), "python": sys.version,
        "python_311_canonical": python_311, "platform": platform.platform(),
        "status": status, "evidence_scope": "source_and_mock_tests_only",
        "mvp_approved": False, "stages": stages,
        "runtime_gates_pending": ["postgresql_migration_014",
            "postgresql_first_publisher_race", "neo4j_mutation_recovery",
            "faiss_active_receipt_revocation", "authenticated_http_sse",
            "browser_qa", "staging_canary_rollback_slo", "independent_uat"],
    }
    (output / "local-handoff-summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[AMC] {status}: {output / 'local-handoff-summary.json'}", flush=True)
    return 0 if status == "PASS_SOURCE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
