"""WP07 static audit: frontend call sites vs the verified pilot perimeter."""
from pathlib import Path

import pytest

from tools.amc_release import frontend_pilot_audit31 as audit

REPORT = Path(__file__).resolve().parents[3] / "remediation" / "wave3_1" / "FRONTEND_PILOT_COMPATIBILITY.md"


@pytest.mark.parametrize("fn,raw,expected", [
    ("request", "/query", "/api/query"),
    ("request", "/sessions/${encodeURIComponent(id)}", "/api/sessions/x"),
    ("request", "/admin/users${qs ? `", "/api/admin/users"),          # nested template literal
    ("request", "/feedback${query}", "/api/feedback"),                  # query-string suffix
    ("request", "/admin/audit?limit=${limit}", "/api/admin/audit"),
    ("fetch", "${API_BASE}/chat/stream", "/api/chat/stream"),
    ("fetch", "https://example.org/x", None),                           # not an app call
    ("fetch", "${OTHER}/x", None),
])
def test_normalization(fn, raw, expected):
    assert audit._normalize(fn, raw) == expected


def test_no_artifact_paths_in_the_report():
    for call in audit.collect_calls():
        assert "${" not in call["path"] and " " not in call["path"], call


def test_core_pilot_journey_calls_are_all_allowed():
    result = audit.audit()
    allowed = {(c["method"], c["path"]) for c in result["allowed"]}
    for core in audit.CORE_PILOT_CALLS:
        assert core in allowed, core


def test_known_non_pilot_features_are_reported_denied():
    denied = {(c["method"], c["path"]) for c in audit.audit()["denied"]}
    assert ("GET", "/api/sessions") in denied
    assert ("POST", "/api/chat/title") in denied
    assert ("POST", "/api/admin/ingestion/upload") in denied
    assert ("GET", "/api/graph") in denied


def test_committed_report_is_current():
    assert REPORT.is_file(), "run: python -m tools.amc_release.frontend_pilot_audit31 --write <report>"
    assert REPORT.read_text(encoding="utf-8") == audit.render(), "stale report; regenerate it"
