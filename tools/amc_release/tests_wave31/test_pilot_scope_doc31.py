"""WP00: the written pilot scope must match the enforced perimeter allowlist."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
from app.api import pilot_perimeter31 as perimeter  # noqa: E402

DOC = REPO / "remediation" / "wave3_1" / "PILOT_SCOPE_DECISION.md"


def _in_scope_section() -> str:
    text = DOC.read_text(encoding="utf-8")
    return text.split("## 2. In scope", 1)[1].split("## 3. Out of scope", 1)[0]


def _documented_routes() -> set[tuple[str, str]]:
    section = _in_scope_section().replace("{work_id}", "w1")
    return set(re.findall(r"`(GET|POST) (/[^`\s]*)`", section))


def test_every_documented_route_is_allowed_by_the_perimeter():
    routes = _documented_routes()
    assert routes, "no routes parsed from the scope document"
    for method, path in routes:
        assert perimeter.is_pilot_route_allowed(method, path), (method, path)


def test_every_exact_allowlist_entry_is_documented():
    documented = _documented_routes()
    for method, path in perimeter._ALLOWED:
        if (method, path) in {("GET", "/"), ("GET", "/chat"), ("GET", "/login")}:
            assert f"`{path}`" in _in_scope_section(), path   # listed in the static UI row
            continue
        assert (method, path) in documented, f"undocumented pilot route: {method} {path}"


def test_signoffs_are_not_pre_filled():
    text = DOC.read_text(encoding="utf-8")
    assert "Status: PROPOSED. Not approved." in text.replace("**", "")
    signoff = text.split("## 6. Required sign-off", 1)[1]
    assert signoff.count("_pending_") >= 6
