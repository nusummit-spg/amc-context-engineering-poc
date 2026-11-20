"""AMC Wave 3.1 evidence-completeness gate. NOT an independent UAT decision."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

REQUIRED_GATES = (
    "backend_integration", "authenticated_negative_routes", "alembic_postgresql_015",
    "postgresql_first_publisher_race", "neo4j_readback_compensation",
    "faiss_receipt_rollback", "frontend_build_browser",
    "staging_smoke", "canary_rollback_slo",
    "answer_quality",           # Wave 4.0 G11 (TDS-40 E5), written only by tools/amc_release/eval40.py
)
# G11 must carry every E5 metric as PASS and name what it measured (provider, model, embedder, gold set).
ANSWER_QUALITY_METRICS = (
    "fin_exact_match", "fin_exact_match_p0", "ungrounded_number_rate", "citation_validity", "routing_accuracy",
    "abstention_should_abstain", "abstention_answerable", "advice_refusal", "cross_tenant_leak",
    "reg_sme_acceptable",
)
ANSWER_QUALITY_BINDINGS = ("provider", "model", "embedder_id", "gold_manifest_sha256", "fin_dataset_version")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def current_sha(checkout: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout,
                       capture_output=True, text=True, timeout=10, check=True)
    sha = r.stdout.strip()
    if not SHA_RE.fullmatch(sha):
        raise ValueError("Checkout returned invalid commit SHA")
    clean = subprocess.run(["git", "status", "--porcelain"], cwd=checkout,
                           capture_output=True, text=True, timeout=10, check=True)
    if clean.stdout.strip():
        raise ValueError("MVP evidence requires a clean exact-commit checkout")
    return sha


def _valid_timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt <= datetime.now(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return False


def _answer_quality_ok(data: dict) -> bool:
    metrics, bindings = data.get("metrics"), data.get("bindings")
    if data.get("schema") != "amc-answer-quality-v1" or not isinstance(metrics, dict) or not isinstance(bindings, dict):
        return False
    if not all(isinstance(metrics.get(m), dict) and metrics[m].get("status") == "PASS"
               for m in ANSWER_QUALITY_METRICS):
        return False
    return all(isinstance(bindings.get(b), str) and bindings[b].strip() for b in ANSWER_QUALITY_BINDINGS)


def assess(checkout: Path, evidence_dir: Path) -> dict:
    sha = current_sha(checkout)
    out = {"schema": "amc-mvp-evidence-gate-v1", "sha": sha,
           "decision": "BLOCKED", "independent_acceptance": False,
           "missing": [], "invalid": [], "available": [], "junit": None}
    for gate in REQUIRED_GATES:
        path = evidence_dir / (gate + ".json")
        if not path.is_file():
            out["missing"].append(gate)
            continue
        if path.is_symlink():
            out["invalid"].append(gate + ":symlink")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                out["invalid"].append(gate + ":not_a_json_object")
                continue
            valid = (data.get("gate") == gate
                     and data.get("commit_sha") == sha
                     and data.get("status") == "PASS"
                     and _valid_timestamp(data.get("observed_at"))
                     and isinstance(data.get("evidence_refs"), list)
                     and len(data["evidence_refs"]) >= 1
                     and all(isinstance(v, str) and v.strip()
                             for v in data["evidence_refs"]))
            if valid and gate == "answer_quality" and not _answer_quality_ok(data):
                out["invalid"].append(gate + ":metrics_or_bindings_incomplete")
            elif valid:
                out["available"].append(gate)
            else:
                out["invalid"].append(gate + ":missing_or_stale_provenance")
        except (OSError, ValueError, TypeError):
            out["invalid"].append(gate + ":unreadable")
    junit = evidence_dir / "integrated-junit.xml"
    if not junit.is_file():
        out["missing"].append("integrated-junit.xml")
    elif junit.is_symlink():
        out["invalid"].append("integrated-junit.xml:symlink")
    else:
        try:
            root = ET.parse(junit).getroot()
            tests = list(root.iter("testcase"))
            failed = sum(x.find("failure") is not None or x.find("error") is not None
                         for x in tests)
            skipped = sum(x.find("skipped") is not None for x in tests)
            out["junit"] = {"testcases": len(tests), "failed": failed,
                            "skipped": skipped,
                            "sha256": hashlib.sha256(junit.read_bytes()).hexdigest()}
            if not tests or failed or skipped:
                out["invalid"].append("integrated-junit.xml:nonpassing_cases")
        except (ET.ParseError, OSError, ValueError):
            out["invalid"].append("integrated-junit.xml:invalid_xml")
    if not out["missing"] and not out["invalid"]:
        out["decision"] = "EVIDENCE_PRESENT_REQUIRES_INDEPENDENT_REVIEW"
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = assess(args.checkout.resolve(), args.evidence_dir.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        result = {"schema": "amc-mvp-evidence-gate-v1", "decision": "BLOCKED",
                  "independent_acceptance": False,
                  "error": type(exc).__name__ + ": " + str(exc)}
    data = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data + "\n", encoding="utf-8")
    print(data)
    return 0 if result["decision"] == "EVIDENCE_PRESENT_REQUIRES_INDEPENDENT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
