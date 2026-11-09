"""Known legacy-pattern scanner tests: no repo mutation."""
from pathlib import Path
import importlib.util

SPEC = importlib.util.spec_from_file_location("audit_wave20", Path(__file__).resolve().parents[2] / "tools" / "audit_legacy_quality_bypasses.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_scanner_finds_bypass(tmp_path):
    p=tmp_path / "backend/app/tabular"
    p.mkdir(parents=True)
    (p / "executor.py").write_text("return source_row_ids[:50]\n", encoding="utf-8")
    findings=mod.scan(tmp_path)
    assert any(f["rule"]=="F-01" and f["state"]=="BLOCK" for f in findings)


def test_scanner_missing_files_not_success(tmp_path):
    findings=mod.scan(tmp_path)
    assert findings and all(f["state"]=="UNKNOWN" for f in findings)


def test_scanner_line_is_grounded(tmp_path):
    p=tmp_path / "backend/app/tabular"
    p.mkdir(parents=True)
    (p / "executor.py").write_text("before\nsecond\nids = source_row_ids[:50]\n", encoding="utf-8")
    assert next(f for f in mod.scan(tmp_path) if f["rule"]=="F-01")["line"] == 3
