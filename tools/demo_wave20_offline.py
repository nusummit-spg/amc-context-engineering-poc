#!/usr/bin/env python3
"""No-service Wave 2.0 smoke. Uses only ephemeral CSV and SQLite data."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from amc_quality.manifest import build_chunk_manifest, verify_chunk_manifest
from amc_quality.financial import FinancialQualityReadModel
from amc_quality.provenance import verify_ledger


def main():
    with TemporaryDirectory(prefix="amc-wave20-smoke-") as wd:
        root=Path(wd)
        source=root / "source.csv"
        with source.open("w",encoding="utf-8",newline="") as f:
            w=csv.writer(f)
            w.writerow(["scheme_code", "nav_per_unit"])
            w.writerow(["100033", "922.67"])
        manifest=build_chunk_manifest(source, root/"chunks",rows_per_chunk=1)
        verified=verify_chunk_manifest(source,manifest)
        db=root/"typed.db"
        with sqlite3.connect(db) as c:
            c.executescript("""CREATE TABLE dataset_versions (dataset_version TEXT PRIMARY KEY,status TEXT);
                CREATE TABLE active_version (id INTEGER PRIMARY KEY,dataset_version TEXT);
                CREATE TABLE source_rows (source_row_id TEXT PRIMARY KEY,dataset_version TEXT,validation_status TEXT,
                    scheme_code TEXT,amc_id TEXT,amc_display_name TEXT,scheme_id TEXT,plan_option_id TEXT,nav_per_unit TEXT,nav_date TEXT);
                CREATE TABLE nav_observations (observation_id TEXT PRIMARY KEY,source_row_id TEXT,dataset_version TEXT,
                    scheme_code TEXT,plan_option_id TEXT,nav_per_unit TEXT,nav_date TEXT);
                INSERT INTO dataset_versions VALUES ('demo','ACTIVE');
                INSERT INTO active_version VALUES (1,'demo');""")
            rid=sha256(b"demo-row").hexdigest()
            c.execute("INSERT INTO source_rows VALUES (?,?,?,?,?,?,?,?,?,?)", (rid,"demo","VALID","100033","A","AMC A","S","P","922.67","2026-06-29"))
            c.execute("INSERT INTO nav_observations VALUES (?,?,?,?,?,?,?)", ("o1",rid,"demo","100033","P","922.67","2026-06-29"))
        ans=FinancialQualityReadModel(db).exact_nav(scheme_code="100033", nav_date="2026-06-29",ledger_path=root/"ledger.jsonl")
        proof=verify_ledger(ans.ledger_path,expected_sha256=ans.contributors_sha256)
        if verified["rows"]!=1 or proof.contributors!=1:
            raise AssertionError("smoke evidence mismatched")
        print(json.dumps({"smoke":"PASS_SIMULATED","source_sha256":verified["source_sha256"],
                          "result_sha256":ans.result_sha256,"contributor_ledger_sha256":ans.contributors_sha256,
                          "note":"offline synthetic data only, NOT production acceptance"},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
