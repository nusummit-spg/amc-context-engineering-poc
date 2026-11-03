#!/usr/bin/env python3
"""
G01-T08: Build source-row and chunk reconciliation probe
Acceptance: Reports raw row count, sum of 22 chunk counts and gaps/overlaps
"""
import json
import csv
import hashlib
from pathlib import Path
from typing import Dict, List, Any


def hash_file(filepath: Path) -> str:
    """Compute SHA256 hash of file"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def reconcile_csv_chunks():
    """Reconcile CSV chunks against manifest declaration"""
    backend_path = Path(__file__).parent.parent.parent / "backend"
    chunks_dir = backend_path / "data" / "source_docs" / "chunks"
    manifest_path = chunks_dir / "manifest.json"
    
    result = {
        "task": "G01-T08",
        "purpose": "CSV chunk reconciliation",
        "manifest_declared": {
            "total_rows": 16245,
            "num_chunks": 22,
            "pattern": "21 × 750 + 495"
        },
        "manifest_exists": manifest_path.exists(),
        "chunks_found": [],
        "reconciliation": {
            "total_rows_actual": 0,
            "chunks_present": 0,
            "chunks_missing": [],
            "row_count_matches": False,
            "chunk_count_matches": False,
            "gaps_or_overlaps": []
        },
        "issues": []
    }
    
    # Read manifest
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            result["manifest_content"] = manifest
    else:
        result["issues"].append("CRITICAL: manifest.json not found")
        return result
    
    # Scan for chunk files
    chunk_pattern = "mutual_fund_data_chunk_*.csv"
    chunk_files = sorted(chunks_dir.glob(chunk_pattern))
    
    for chunk_file in chunk_files:
        chunk_info = {
            "filename": chunk_file.name,
            "path": str(chunk_file.relative_to(backend_path)),
            "exists": True,
            "size_bytes": chunk_file.stat().st_size,
            "sha256": hash_file(chunk_file)
        }
        
        # Count rows (excluding header)
        try:
            with open(chunk_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                row_count = sum(1 for _ in reader)
                chunk_info["row_count"] = row_count
                chunk_info["has_header"] = header is not None
                chunk_info["header_columns"] = len(header) if header else 0
                
                result["reconciliation"]["total_rows_actual"] += row_count
        except Exception as e:
            chunk_info["error"] = str(e)
            result["issues"].append(f"Could not read {chunk_file.name}: {e}")
        
        result["chunks_found"].append(chunk_info)
    
    # Reconciliation checks
    result["reconciliation"]["chunks_present"] = len(chunk_files)
    
    # Expected: 22 chunks
    if result["reconciliation"]["chunks_present"] != 22:
        result["issues"].append(
            f"MISMATCH: Expected 22 chunks, found {result['reconciliation']['chunks_present']}"
        )
        # Identify missing chunks
        expected_chunks = [f"mutual_fund_data_chunk_{i:03d}.csv" for i in range(1, 23)]
        found_names = {c["filename"] for c in result["chunks_found"]}
        result["reconciliation"]["chunks_missing"] = [
            name for name in expected_chunks if name not in found_names
        ]
    else:
        result["reconciliation"]["chunk_count_matches"] = True
    
    # Expected: 16,245 total rows
    actual_rows = result["reconciliation"]["total_rows_actual"]
    if actual_rows != 16245:
        result["issues"].append(
            f"MISMATCH: Expected 16,245 rows, found {actual_rows} rows"
        )
    else:
        result["reconciliation"]["row_count_matches"] = True
    
    # Check expected pattern: 21 chunks of 750, last chunk of 495
    # 21 * 750 + 495 = 15,750 + 495 = 16,245
    if len(result["chunks_found"]) == 22:
        expected_pattern_rows = 21 * 750 + 495
        for i, chunk in enumerate(result["chunks_found"]):
            expected_rows = 750 if i < 21 else 495
            if chunk.get("row_count") != expected_rows:
                result["reconciliation"]["gaps_or_overlaps"].append({
                    "chunk": chunk["filename"],
                    "expected_rows": expected_rows,
                    "actual_rows": chunk.get("row_count"),
                    "difference": chunk.get("row_count", 0) - expected_rows
                })
    
    # Overall status
    if not result["issues"]:
        result["status"] = "PASS"
        result["message"] = "All 22 chunks present, 16,245 rows accounted for"
    else:
        result["status"] = "FAIL"
        result["message"] = f"{len(result['issues'])} issues found"
    
    # Save results
    output_path = Path(__file__).parent / "csv_reconciliation_report.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"✓ CSV reconciliation report saved to {output_path}")
    print(f"✓ Status: {result['status']}")
    print(f"✓ Chunks found: {result['reconciliation']['chunks_present']}/22")
    print(f"✓ Total rows: {result['reconciliation']['total_rows_actual']}/16,245")
    
    if result["issues"]:
        print(f"\n⚠ Issues found:")
        for issue in result["issues"]:
            print(f"  - {issue}")
    
    print("\nG01-T08 COMPLETE: CSV reconciliation probe executed")
    return result


if __name__ == "__main__":
    reconcile_csv_chunks()
