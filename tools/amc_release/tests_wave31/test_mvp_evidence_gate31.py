"""Deterministic release-evidence intake tests. No service access required."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
from tools.amc_release import mvp_evidence_gate31 as gate

def _checkout(tmp_path):
    d=tmp_path/"repo";d.mkdir()
    subprocess.run(["git","init","-q"],cwd=d,check=True)
    subprocess.run(["git","-c","user.email=tests@example.org","-c","user.name=Tests",
                    "commit","--allow-empty","-qm","init"],cwd=d,check=True)
    e=tmp_path/"proof";e.mkdir()
    return d,e

def _write(e,key,sha,**override):
    data={"gate":key,"commit_sha":sha,"status":"PASS",
          "observed_at":datetime.now(timezone.utc).isoformat(),
          "evidence_refs":["observed-service-result"]}
    data.update(override)
    (e/(key+".json")).write_text(json.dumps(data),encoding="utf-8")

def _fill(e,sha):
    for g in gate.REQUIRED_GATES:_write(e,g,sha)
    ET.ElementTree(ET.fromstring('<testsuite><testcase name="ok"/></testsuite>')).write(
        e/"integrated-junit.xml")

def test_missing_blocks(tmp_path):
    d,e=_checkout(tmp_path)
    a=gate.assess(d,e)
    assert a["decision"]=="BLOCKED"
    assert len(a["missing"])==len(gate.REQUIRED_GATES)+1

def test_valid_schema_is_not_deployment_authorization(tmp_path):
    d,e=_checkout(tmp_path)
    _fill(e,gate.current_sha(d))
    a=gate.assess(d,e)
    assert a["decision"]=="EVIDENCE_PRESENT_REQUIRES_INDEPENDENT_REVIEW"
    assert a["independent_acceptance"] is False

def test_stale_sha_blocks(tmp_path):
    d,e=_checkout(tmp_path)
    _fill(e,gate.current_sha(d))
    _write(e,"faiss_receipt_rollback","0"*40)
    assert gate.assess(d,e)["decision"]=="BLOCKED"

def test_failed_or_skipped_junit_blocks(tmp_path):
    d,e=_checkout(tmp_path)
    _fill(e,gate.current_sha(d))
    for kind in ("failure","skipped"):
        (e/"integrated-junit.xml").write_text(
            f'<testsuite><testcase name="bad"><{kind}/></testcase></testsuite>')
        assert gate.assess(d,e)["decision"]=="BLOCKED"

def test_empty_or_future_provenance_blocks(tmp_path):
    d,e=_checkout(tmp_path)
    sha=gate.current_sha(d)
    _fill(e,sha)
    _write(e,"backend_integration",sha,evidence_refs=[])
    assert gate.assess(d,e)["decision"]=="BLOCKED"
    _write(e,"backend_integration",sha,
           observed_at=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat())
    assert gate.assess(d,e)["decision"]=="BLOCKED"
