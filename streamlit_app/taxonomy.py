# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
taxonomy.py
============
Builds taxonomy.json from data/AMFI/ and data/Sub Classification/.
Expected: csv/xlsx files with columns like scheme_name, amc_name, category,
sub_category, benchmark — column names are sniffed loosely (case-insensitive
substring match), so it tolerates messy AMFI exports.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Set

import config

_COLUMN_HINTS = {
    "fund_houses":        ["amc", "fund house", "asset management"],
    "scheme_names":       ["scheme name", "fund name"],
    "categories":         ["category"],
    "sub_categories":     ["sub category", "sub-category", "subcategory"],
    "benchmarks":         ["benchmark"],
}


def _read_tabular(path: Path):
    if path.suffix.lower() == ".csv":
        import csv
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            rows = list(csv.reader(f))
        if not rows:
            return [], []
        return rows[0], rows[1:]
    elif path.suffix.lower() in (".xlsx", ".xls"):
        # Try openpyxl first (handles real xlsx, even with .xls extension)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            ws = wb[wb.sheetnames[0]]
            rows = [[str(c).strip() if c is not None else "" for c in r]
                    for r in ws.iter_rows(values_only=True)]
            if rows:
                return rows[0], rows[1:]
        except Exception:
            pass
        # Try xlrd next (handles old binary xls format)
        try:
            import xlrd
            wb = xlrd.open_workbook(path)
            ws = wb.sheet_by_index(0)
            rows = [[str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)] for r in range(ws.nrows)]
            if rows:
                return rows[0], rows[1:]
        except Exception as e:
            print(f"  [taxonomy] Could not read {path.name} with either openpyxl or xlrd: {e}", flush=True)
            return [], []
    return [], []


def _match_columns(header: list[str]) -> Dict[str, int]:
    header_lower = [h.lower() for h in header]
    matched = {}
    for key, hints in _COLUMN_HINTS.items():
        for i, h in enumerate(header_lower):
            if any(hint in h for hint in hints):
                matched[key] = i
                break
    return matched


def build_taxonomy(verbose: bool = True) -> Dict[str, list]:
    taxonomy: Dict[str, Set[str]] = {k: set() for k in _COLUMN_HINTS}

    folders = [config.AMFI_DIR, config.SUBCLASS_DIR]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in (".csv", ".xlsx", ".xls"):
                continue
            header, rows = _read_tabular(path)
            if not header:
                continue
            col_map = _match_columns(header)
            for key, col_idx in col_map.items():
                for row in rows:
                    if col_idx < len(row) and row[col_idx].strip():
                        taxonomy[key].add(row[col_idx].strip())
            if verbose:
                print(f"  [taxonomy] {path.name}: matched {list(col_map.keys())}", flush=True)

    _STATIC_BASELINE = {
        "categories": ["Equity Schemes", "Debt Schemes", "Hybrid Schemes", "Solution Oriented Schemes", "Other Schemes", "Index Funds", "Fund of Funds"],
        "sub_categories": ["Large Cap Fund", "Mid Cap Fund", "Small Cap Fund", "Flexi Cap Fund", "Multi Cap Fund", "ELSS", "Sectoral/Thematic", "Liquid Fund", "Overnight Fund", "Money Market Fund", "Aggressive Hybrid", "Balanced Advantage"],
        "fund_houses": ["Adani Mutual Fund", "SBI Mutual Fund", "HDFC Mutual Fund", "ICICI Prudential Mutual Fund", "Nippon India Mutual Fund"],
    }
    for k, v in _STATIC_BASELINE.items():
        if k in taxonomy:
            taxonomy[k].update(v)

    result = {k: sorted(v) for k, v in taxonomy.items()}
    config.TAXONOMY_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        for k, v in result.items():
            print(f"  [taxonomy] {k}: {len(v)} entries", flush=True)
    return result


def load_taxonomy() -> Dict[str, list]:
    if not config.TAXONOMY_PATH.exists():
        return build_taxonomy()
    return json.loads(config.TAXONOMY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    build_taxonomy()
