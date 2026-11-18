"""The frontend's pilot API allowlist must equal the backend perimeter's (no drift between languages)."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
from app.api import pilot_perimeter31 as perimeter  # noqa: E402

JS = REPO / "mf-context-engine" / "src" / "utils" / "pilotSources.js"


def _js_list(name: str) -> list[str]:
    body = re.search(rf"export const {name}\s*=\s*\[(.*?)\];", JS.read_text(encoding="utf-8"), re.S).group(1)
    return re.findall(r'"([^"]+)"', body)


def test_js_allowlist_equals_the_backend_api_entries():
    backend = {f"{m} {p}" for m, p in perimeter._ALLOWED if p.startswith("/api/")}
    assert set(_js_list("PILOT_ALLOWED_API")) == backend


def test_js_prefix_rule_matches_the_backend_publication_status_rule():
    assert _js_list("PILOT_ALLOWED_API_PREFIXES") == ["GET " + perimeter._PUBLICATION_STATUS_PREFIX]


def test_every_js_allowed_call_is_really_admitted_by_the_backend():
    for entry in _js_list("PILOT_ALLOWED_API"):
        method, path = entry.split(" ", 1)
        assert perimeter.is_pilot_route_allowed(method, path), entry
