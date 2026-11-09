#!/usr/bin/env python3
"""Offline, read-only source audit. Reports high-risk legacy call paths.

This is a baseline scanner, not a proof that undiscovered paths are safe.
Does not mutate local repository, accept remote URLs, or inspect credentials.
"""
import argparse
import json
from pathlib import Path
import re

RULES = (
    ("F-01", "backend/app/tabular/executor.py", r"source_row_ids\s*\[:\s*50\s*\]", "truncated provenance IDs"),
    ("F-02", "backend/app/tabular/csv_excel_loader.py", r"declared_total_rows\s*=\s*16245", "implicit row-count fallback"),
    ("F-03", "backend/app/tabular/csv_excel_loader.py", r"declared_chunks\s*=\s*22", "implicit chunk-count fallback"),
    ("F-04", "backend/app/services/financial_policy_service.py", r"return\s+True\s+#\s+Legacy fallback allowed", "legacy numeric fallback permitted"),
    ("G-01", "backend/app/graph/correction_patch_layer.py", r"if\s+p\.approved\]", "approved-only serving reader"),
    ("G-02", "backend/app/graph/correction_patch_layer.py", r"return\s+self\.promote_to_permanent\(", "legacy direct promotion alias"),
    ("P-01", "backend/app/services/outbox_processor.py", r"raise\s+NotImplementedError", "outbox handler still unimplemented"),
)


def scan(repo: Path) -> list[dict]:
    findings=[]
    for rule, path, expression, desc in RULES:
        file=repo / path
        if not file.is_file():
            findings.append({"rule": rule, "file": path, "state": "UNKNOWN", "detail": "source file missing"})
            continue
        try:
            content=file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"rule": rule, "file": path, "state": "UNKNOWN", "detail": "source unreadable"})
            continue
        matches=list(re.finditer(expression, content))
        if matches:
            findings.append({"rule": rule, "file": path, "state": "BLOCK",
                             "line": content.count("\n", 0, matches[0].start())+1, "detail":desc})
    return findings


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Read-only AMC legacy quality audit")
    p.add_argument("--repo", type=Path, required=True)
    args=p.parse_args(argv)
    if not args.repo.is_dir():
        p.error("repository directory not found")
    findings=scan(args.repo)
    print(json.dumps({"release_gate": "BLOCK", "scope":"known-regex-patterns-only", "findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
