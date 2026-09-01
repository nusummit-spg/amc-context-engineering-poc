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

from app.engine import config

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
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [[str(c).strip() if c is not None else "" for c in r]
                for r in ws.iter_rows(values_only=True)]
        if not rows:
            return [], []
        return rows[0], rows[1:]
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

    result = {k: sorted(v) for k, v in taxonomy.items()}
    config.TAXONOMY_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    if verbose:
        for k, v in result.items():
            print(f"  [taxonomy] {k}: {len(v)} entries", flush=True)
    return result


def load_taxonomy() -> Dict[str, list]:
    if not config.TAXONOMY_PATH.exists():
        return build_taxonomy()
    return json.loads(config.TAXONOMY_PATH.read_text())


if __name__ == "__main__":
    build_taxonomy()


# ──────────────────────────────────────────────────────────────────────────
# EXTENSIONS FOR PHASE 0: Versioning, Atomic Writes, Backup
# ──────────────────────────────────────────────────────────────────────────

import shutil
from datetime import datetime


def backup_taxonomy(source_path: Path = None, dest_dir: Path = None) -> Path:
    """
    Create a timestamped backup of taxonomy.json.
    
    Args:
        source_path: taxonomy file to backup (default: TAXONOMY_PATH)
        dest_dir: directory to store backups (default: TAXONOMY_BACKUP_DIR)
        
    Returns:
        Path to the created backup file
    """
    source_path = source_path or config.TAXONOMY_PATH
    dest_dir = dest_dir or config.TAXONOMY_BACKUP_DIR
    
    if not source_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {source_path}")
    
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().isoformat().replace(":", "-")
    backup_name = f"taxonomy_{timestamp}.json"
    backup_path = dest_dir / backup_name
    
    shutil.copy2(source_path, backup_path)
    return backup_path


def write_taxonomy_atomic(data: Dict[str, list], target_path: Path = None) -> None:
    """
    Write taxonomy atomically: write to temp file first, then rename.
    Prevents torn/corrupt writes if process crashes mid-write.
    
    Args:
        data: taxonomy dict to write
        target_path: target file path (default: TAXONOMY_PATH)
    """
    target_path = target_path or config.TAXONOMY_PATH
    temp_path = target_path.parent / f"{target_path.name}.tmp"
    
    # Write to temp file
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    # Atomic rename
    temp_path.replace(target_path)


def restore_taxonomy_version(backup_path: Path) -> Dict[str, list]:
    """
    Restore taxonomy from a backup version and return the data.
    
    Args:
        backup_path: path to backup taxonomy file
        
    Returns:
        loaded taxonomy dict
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    
    data = json.loads(backup_path.read_text())
    
    # Copy backup to current taxonomy
    write_taxonomy_atomic(data)
    return data


def list_taxonomy_versions(backup_dir: Path = None) -> list[tuple[Path, datetime]]:
    """
    List all backed-up taxonomy versions in chronological order.
    
    Args:
        backup_dir: directory containing backups (default: TAXONOMY_BACKUP_DIR)
        
    Returns:
        list of (backup_path, timestamp) tuples, newest first
    """
    backup_dir = backup_dir or config.TAXONOMY_BACKUP_DIR
    versions = []
    
    if not backup_dir.exists():
        return versions
    
    for backup_file in backup_dir.glob("taxonomy_*.json"):
        try:
            # Extract timestamp from filename
            ts_str = backup_file.stem.replace("taxonomy_", "").replace("-", ":")
            ts = datetime.fromisoformat(ts_str)
            versions.append((backup_file, ts))
        except (ValueError, AttributeError):
            continue
    
    # Sort by timestamp, newest first
    versions.sort(key=lambda x: x[1], reverse=True)
    return versions


def diff_taxonomy_versions(
    old_path: Path,
    new_path: Path
) -> Dict[str, Dict[str, list]]:
    """
    Compare two taxonomy versions and return diffs.
    
    Args:
        old_path: path to older taxonomy
        new_path: path to newer taxonomy
        
    Returns:
        dict with keys "added", "removed", "unchanged" per category
    """
    old_data = json.loads(old_path.read_text())
    new_data = json.loads(new_path.read_text())
    
    result = {}
    for key in set(old_data.keys()) | set(new_data.keys()):
        old_set = set(old_data.get(key, []))
        new_set = set(new_data.get(key, []))
        
        result[key] = {
            "added": sorted(new_set - old_set),
            "removed": sorted(old_set - new_set),
            "unchanged": sorted(old_set & new_set),
        }
    
    return result


# ──────────────────────────────────────────────────────────────────────────
# PHASE 10: SKOS Export & RDF Generation
# ──────────────────────────────────────────────────────────────────────────

def export_taxonomy_skos(
    taxonomy_data: Dict[str, list] = None,
    include_fibo: bool = True
) -> str:
    """
    Export taxonomy to SKOS (Simple Knowledge Organization System) RDF format.
    Used for external sharing and semantic web integration.
    
    Args:
        taxonomy_data: taxonomy dict (default: load from disk)
        include_fibo: include FIBO mappings in output
        
    Returns:
        RDF/XML as string
    """
    if taxonomy_data is None:
        taxonomy_data = load_taxonomy()
    
    # SKOS RDF template
    rdf_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '         xmlns:skos="http://www.w3.org/2004/02/skos/core#"',
        '         xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '         xmlns:fibo="https://spec.edmcouncil.org/fibo/ontology/">',
        '',
    ]
    
    # Create concept scheme
    from datetime import datetime
    timestamp = datetime.utcnow().isoformat()
    
    rdf_lines.append('  <rdf:Description rdf:about="http://example.org/taxonomy/amfi">')
    rdf_lines.append('    <rdf:type rdf:resource="http://www.w3.org/2004/02/skos/core#ConceptScheme"/>')
    rdf_lines.append('    <dc:title>AMFI Regulatory Taxonomy</dc:title>')
    rdf_lines.append(f'    <dc:created>{timestamp}</dc:created>')
    rdf_lines.append('  </rdf:Description>')
    rdf_lines.append('')
    
    # Export each category as a concept
    for category, terms in taxonomy_data.items():
        # Skip if not a list
        if not isinstance(terms, list):
            continue
        
        for term in sorted(set(terms)):  # Dedup
            # Sanitize for use in URI
            safe_term = term.replace(" ", "_").replace("/", "_").lower()
            uri = f"http://example.org/taxonomy/amfi#{category}_{safe_term}"
            
            rdf_lines.append(f'  <rdf:Description rdf:about="{uri}">')
            rdf_lines.append('    <rdf:type rdf:resource="http://www.w3.org/2004/02/skos/core#Concept"/>')
            rdf_lines.append(f'    <skos:prefLabel>{term}</skos:prefLabel>')
            rdf_lines.append(f'    <skos:inScheme rdf:resource="http://example.org/taxonomy/amfi"/>')
            
            # Add FIBO mapping if available
            if include_fibo:
                try:
                    from app.engine.taxonomy_extractor import map_to_fibo
                    fibo_uri = map_to_fibo(term)
                    if fibo_uri:
                        rdf_lines.append(f'    <skos:exactMatch rdf:resource="{fibo_uri}"/>')
                except Exception:
                    pass
            
            rdf_lines.append('  </rdf:Description>')
            rdf_lines.append('')
    
    rdf_lines.append('</rdf:RDF>')
    
    return '\n'.join(rdf_lines)


def export_taxonomy_json_ld(
    taxonomy_data: Dict[str, list] = None
) -> Dict[str, any]:
    """
    Export taxonomy to JSON-LD (Linked Data) format.
    Useful for web APIs and linked data applications.
    
    Args:
        taxonomy_data: taxonomy dict (default: load from disk)
        
    Returns:
        JSON-LD dict
    """
    if taxonomy_data is None:
        taxonomy_data = load_taxonomy()
    
    from datetime import datetime
    
    doc = {
        "@context": {
            "@vocab": "http://example.org/taxonomy/amfi#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dc": "http://purl.org/dc/elements/1.1/",
            "fibo": "https://spec.edmcouncil.org/fibo/ontology/",
        },
        "@type": "skos:ConceptScheme",
        "dc:title": "AMFI Regulatory Taxonomy",
        "dc:created": datetime.utcnow().isoformat(),
        "dc:description": "Regulatory and operational taxonomy for Indian Mutual Funds",
        "hasConceptsOf": [],
    }
    
    # Add concepts
    for category, terms in taxonomy_data.items():
        if not isinstance(terms, list):
            continue
        
        for term in sorted(set(terms)):
            concept = {
                "@type": "skos:Concept",
                "skos:prefLabel": term,
                "skos:inScheme": {"@id": "http://example.org/taxonomy/amfi"},
                "category": category,
            }
            doc["hasConceptsOf"].append(concept)
    
    return doc


if __name__ == "__main__":
    # Test export
    taxonomy = load_taxonomy()
    print("Sample SKOS output:")
    skos = export_taxonomy_skos(taxonomy, include_fibo=False)
    print(skos[:500])
    print("\nSample JSON-LD output:")
    jsonld = export_taxonomy_json_ld(taxonomy)
    print(json.dumps(jsonld, indent=2)[:500])
