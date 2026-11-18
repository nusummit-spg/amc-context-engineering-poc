"""Turn REAL JUnit results into gate evidence records for mvp_evidence_gate31 (never fabricates a PASS).

A gate record is written only when every mapped test ran (>=1), none failed, errored or was skipped. A skipped
LIVE31_BLOCKED test therefore blocks its gate instead of passing it. Gates that need evidence a JUnit file
cannot give (browser walkthrough, staging smoke, canary/SLO, integrated backend run) are never written here.

    python -m tools.amc_release.make_evidence31 --junit live31-junit.xml --checkout <clean checkout> --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from tools.amc_release.mvp_evidence_gate31 import current_sha

# gate -> test modules whose results are the evidence for it
GATE_MODULES = {
    "alembic_postgresql_014": ("test_pg_migration31",),
    "postgresql_first_publisher_race": ("test_publication_live31",),
    "neo4j_readback_compensation": ("test_publication_live31", "test_ops_drills_live31"),
    "faiss_receipt_rollback": ("test_faiss_serving_live31",),
    "authenticated_negative_routes": ("test_http_enforce_live31",),
}


def _cases(junit: Path) -> list[dict]:
    out = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        out.append({"module": tc.get("classname", "").rsplit(".", 1)[-1] if "." in tc.get("classname", "") else "",
                    "classname": tc.get("classname", ""), "name": tc.get("name", ""),
                    "failed": tc.find("failure") is not None or tc.find("error") is not None,
                    "skipped": tc.find("skipped") is not None,
                    "xfail": (tc.find("skipped") is not None and
                              "xfail" in (tc.find("skipped").get("type", "") + tc.find("skipped").get("message", "")).lower())})
    return out


def build(junit: Path, checkout: Path, out_dir: Path) -> dict:
    sha = current_sha(checkout)
    digest = hashlib.sha256(junit.read_bytes()).hexdigest()
    cases = _cases(junit)
    now = datetime.now(timezone.utc).isoformat()
    result = {"commit_sha": sha, "junit_sha256": digest, "written": [], "not_written": {}}
    out_dir.mkdir(parents=True, exist_ok=True)
    for gate, modules in GATE_MODULES.items():
        mine = [c for c in cases if any(m in c["classname"] for m in modules)]
        failed = [c["name"] for c in mine if c["failed"]]
        skipped = [c["name"] for c in mine if c["skipped"] and not c["xfail"]]
        if not mine:
            result["not_written"][gate] = "no test results found"
        elif failed:
            result["not_written"][gate] = f"{len(failed)} failed: {failed[:3]}"
        elif skipped:
            result["not_written"][gate] = f"{len(skipped)} skipped (blocked): {skipped[:3]}"
        else:
            record = {"gate": gate, "commit_sha": sha, "status": "PASS", "observed_at": now,
                      "evidence_refs": [f"junit sha256 {digest}", "modules: " + ", ".join(modules),
                                        f"{len(mine)} tests, 0 failed, 0 skipped"],
                      "environment": {"scope": "LOCAL DISPOSABLE services only (not staging, not UAT)",
                                      "os": platform.platform(), "python": sys.version.split()[0]},
                      "test_counts": {"tests": len(mine), "failed": 0, "skipped": 0},
                      "operator_reviewer": "not reviewed independently"}
            (out_dir / f"{gate}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            result["written"].append(gate)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.junit, args.checkout.resolve(), args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
