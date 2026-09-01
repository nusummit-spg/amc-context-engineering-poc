# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
taxonomy_extractor.py
=======================
Phase 6: Core extraction pipeline for dynamic taxonomy generation.
Processes documents from all acquisition channels and updates taxonomy.json.

7-step pipeline:
  6a: Route & extract (NAV/SID tabular vs. circular text)
  6b: NER-driven extraction (fund houses, schemes, regulatory obligations)
  6c: Concept normalization (dedup, case-normalize)
  6d: FIBO anchoring (map fund house → FIBO institutional concept)
  6e: Merge with versioning (atomic write, backup)
  6f: Neo4j graph node generation
  6g: NER hot-reload (update classifier without restart)

This module is the core IP — designed for incremental testing of each step.
"""
from __future__ import annotations
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from app.engine import config
from app.engine.provenance_ledger import DocumentStatus, get_ledger
from app.engine.taxonomy import write_taxonomy_atomic, backup_taxonomy


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# STEP 6A: Route & Extract (Tabular vs. Text)
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    """Result of extraction from a single document."""
    source_document: str
    source_hash: str
    timestamp: str
    fund_houses: Set[str] = field(default_factory=set)
    schemes: Set[str] = field(default_factory=set)
    benchmarks: Set[str] = field(default_factory=set)
    categories: Set[str] = field(default_factory=set)
    sub_categories: Set[str] = field(default_factory=set)
    regulatory_obligations: Set[str] = field(default_factory=set)
    compliance_concepts: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with sets as lists."""
        return {
            "source_document": self.source_document,
            "source_hash": self.source_hash,
            "timestamp": self.timestamp,
            "fund_houses": sorted(self.fund_houses),
            "schemes": sorted(self.schemes),
            "benchmarks": sorted(self.benchmarks),
            "categories": sorted(self.categories),
            "sub_categories": sorted(self.sub_categories),
            "regulatory_obligations": sorted(self.regulatory_obligations),
            "compliance_concepts": sorted(self.compliance_concepts),
            "errors": self.errors,
        }


def tabular_nav_extract(df: pd.DataFrame) -> ExtractionResult:
    """
    Step 6a (Tabular): Extract from NAV DataFrame.
    Columns typically: AMCName, SchemeName, NAV, Category, SubCategory, Benchmark
    """
    result = ExtractionResult(
        source_document="nav_dataframe",
        source_hash=hashlib.sha256(df.to_csv().encode()).hexdigest(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    # Column mapping with fuzzy matching
    amc_col = None
    scheme_col = None
    category_col = None
    subcategory_col = None
    benchmark_col = None
    
    for col in df.columns:
        col_lower = col.lower()
        if not amc_col and any(x in col_lower for x in ["amc", "fund house", "fund_house"]):
            amc_col = col
        if not scheme_col and any(x in col_lower for x in ["scheme", "fund", "fund_name"]):
            scheme_col = col
        if not category_col and "category" in col_lower:
            category_col = col
        if not subcategory_col and any(x in col_lower for x in ["subcategory", "sub_category", "sub-category"]):
            subcategory_col = col
        if not benchmark_col and "benchmark" in col_lower:
            benchmark_col = col
    
    # Extract
    if amc_col:
        result.fund_houses.update(df[amc_col].dropna().astype(str).unique())
    if scheme_col:
        result.schemes.update(df[scheme_col].dropna().astype(str).unique())
    if category_col:
        result.categories.update(df[category_col].dropna().astype(str).unique())
    if subcategory_col:
        result.sub_categories.update(df[subcategory_col].dropna().astype(str).unique())
    if benchmark_col:
        result.benchmarks.update(df[benchmark_col].dropna().astype(str).unique())
    
    logger.info(f"[extraction] Tabular NAV: {len(result.fund_houses)} houses, {len(result.schemes)} schemes")
    return result


def tabular_sid_extract(df: pd.DataFrame) -> ExtractionResult:
    """Step 6a (Tabular): Extract from SID/SAI DataFrame."""
    result = ExtractionResult(
        source_document="sid_sai_dataframe",
        source_hash=hashlib.sha256(df.to_csv().encode()).hexdigest(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    # Similar column mapping
    for col in df.columns:
        col_lower = col.lower()
        if any(x in col_lower for x in ["amc", "fund house"]):
            result.fund_houses.update(df[col].dropna().astype(str).unique())
        if "scheme" in col_lower:
            result.schemes.update(df[col].dropna().astype(str).unique())
    
    logger.info(f"[extraction] SID/SAI: {len(result.fund_houses)} houses, {len(result.schemes)} schemes")
    return result


# ──────────────────────────────────────────────────────────────────────────
# STEP 6B: NER-Driven Extraction (Circular Text)
# ──────────────────────────────────────────────────────────────────────────

REGULATORY_OBLIGATION_KEYWORDS = {
    "fund house", "amc", "asset management",
    "scheme", "mutual fund",
    "nav", "net asset value",
    "redemption", "disclosure",
    "kyc", "know your customer",
    "factsheet", "benchmark",
}

COMPLIANCE_CONCEPTS = {
    "sebi", "amfi", "compliance",
    "regulation", "circular", "master circular",
    "amendment", "suspension", "cancellation",
    "suspension of sale", "segregation",
}


def ner_circular_extract(
    text: str,
    use_gliner: bool = True
) -> ExtractionResult:
    """
    Step 6b (NER): Extract named entities from circular text.
    
    Strategies:
      1. GliNER-based NER (if available, else regex fallback)
      2. Keyword extraction (regex patterns for regulatory terms)
      3. Regulatory obligations (heuristic scoring)
    """
    result = ExtractionResult(
        source_document="circular_text",
        source_hash=hashlib.sha256(text.encode()).hexdigest(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    # Strategy 1: GliNER NER (if enabled)
    if use_gliner and config.GLINER_MODEL_ID:
        try:
            from gliner import GLiNER
            model = GLiNER.from_pretrained(config.GLINER_MODEL_ID)
            
            # Chunk large texts (GliNER has token limits)
            chunks = [text[i:i+1000] for i in range(0, len(text), 800)]
            
            for chunk in chunks:
                entities = model.predict_entities(
                    chunk,
                    labels=config.GLINER_LABELS,
                    threshold=config.GLINER_THRESHOLD
                )
                
                for ent in entities:
                    label = ent["label"].lower()
                    text_val = ent["text"].strip()
                    
                    if "fund house" in label or "amc" in label:
                        result.fund_houses.add(text_val)
                    elif "scheme" in label or "fund name" in label:
                        result.schemes.add(text_val)
                    elif "benchmark" in label:
                        result.benchmarks.add(text_val)
                    elif "asset class" in label:
                        result.categories.add(text_val)
                    elif "sector" in label:
                        result.sub_categories.add(text_val)
        except Exception as e:
            logger.warning(f"[extraction] GliNER failed: {e}")
            result.errors.append(f"GliNER extraction failed: {str(e)}")
    
    # Strategy 2: Keyword extraction (regex patterns)
    # Pattern: "Fund House: XYZ AMC"
    fh_pattern = r"Fund\s+House[:\s]+([A-Z][A-Za-z\s&]+(?:AMC|Limited))"
    for match in re.finditer(fh_pattern, text, re.IGNORECASE):
        result.fund_houses.add(match.group(1).strip())
    
    # Pattern: "Scheme: Name of Scheme"
    scheme_pattern = r"Scheme[:\s]+([A-Z][A-Za-z0-9\s\-&]+?)(?:\(|,|$)"
    for match in re.finditer(scheme_pattern, text):
        scheme_name = match.group(1).strip()
        if len(scheme_name) > 3:  # Filter out noise
            result.schemes.add(scheme_name)
    
    # Strategy 3: Regulatory obligations (keyword matching)
    text_lower = text.lower()
    for keyword in REGULATORY_OBLIGATION_KEYWORDS:
        if keyword in text_lower:
            result.regulatory_obligations.add(keyword)
    
    for concept in COMPLIANCE_CONCEPTS:
        if concept in text_lower:
            result.compliance_concepts.add(concept)
    
    logger.info(f"[extraction] Circular NER: {len(result.fund_houses)} houses, "
                f"{len(result.regulatory_obligations)} obligations")
    return result


# ──────────────────────────────────────────────────────────────────────────
# STEP 6C: Concept Normalization
# ──────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize a text token for deduplication."""
    # Strip whitespace, lowercase, remove extra spaces
    text = text.strip().lower()
    text = re.sub(r'\s+', ' ', text)
    # Remove common suffixes
    text = re.sub(r'\s+(limited|pvt|ltd|inc|corp)$', '', text)
    return text


def deduplicate_and_normalize(
    items: Set[str],
    case_sensitive: bool = False
) -> Set[str]:
    """
    Deduplicate a set of items using normalized forms.
    
    Args:
        items: set of strings to deduplicate
        case_sensitive: if False, use case-insensitive matching
        
    Returns:
        deduplicated set
    """
    if not items:
        return set()
    
    result = set()
    seen_normalized = set()
    
    for item in sorted(items):
        normalized = normalize_text(item) if not case_sensitive else item.strip()
        
        # Skip duplicates
        if normalized in seen_normalized:
            continue
        
        seen_normalized.add(normalized)
        result.add(item)  # Keep original casing
    
    return result


def merge_extraction_results(
    results: List[ExtractionResult],
    dedup: bool = True
) -> ExtractionResult:
    """
    Merge multiple extraction results (Step 6c).
    
    Args:
        results: list of ExtractionResult objects
        dedup: if True, deduplicate and normalize all fields
        
    Returns:
        merged ExtractionResult
    """
    merged = ExtractionResult(
        source_document="merged",
        source_hash="",
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    for result in results:
        merged.fund_houses.update(result.fund_houses)
        merged.schemes.update(result.schemes)
        merged.benchmarks.update(result.benchmarks)
        merged.categories.update(result.categories)
        merged.sub_categories.update(result.sub_categories)
        merged.regulatory_obligations.update(result.regulatory_obligations)
        merged.compliance_concepts.update(result.compliance_concepts)
        merged.errors.extend(result.errors)
    
    # Deduplicate if requested
    if dedup:
        merged.fund_houses = deduplicate_and_normalize(merged.fund_houses)
        merged.schemes = deduplicate_and_normalize(merged.schemes)
        merged.benchmarks = deduplicate_and_normalize(merged.benchmarks)
        merged.categories = deduplicate_and_normalize(merged.categories)
        merged.sub_categories = deduplicate_and_normalize(merged.sub_categories)
    
    return merged


# ──────────────────────────────────────────────────────────────────────────
# STEP 6D: FIBO Anchoring
# ──────────────────────────────────────────────────────────────────────────

# Simplified FIBO mapping (real implementation would use RDF lookup)
FIBO_MAPPING = {
    "fund house": "fibo:InvestmentManager",
    "amc": "fibo:InvestmentManager",
    "asset management": "fibo:AssetManagement",
    "scheme": "fibo:MutualFundProduct",
    "mutual fund": "fibo:MutualFundProduct",
    "nav": "fibo:NetAssetValue",
    "benchmark": "fibo:BenchmarkIndex",
}


def map_to_fibo(term: str, threshold: float = 0.85) -> Optional[str]:
    """
    Map a term to a FIBO concept using fuzzy matching.
    
    Args:
        term: term to map
        threshold: similarity threshold (0.0-1.0)
        
    Returns:
        FIBO concept URI or None if no match
    """
    term_lower = normalize_text(term)
    
    best_match = None
    best_score = 0.0
    
    for fibo_term, fibo_uri in FIBO_MAPPING.items():
        score = SequenceMatcher(None, term_lower, fibo_term).ratio()
        if score > best_score:
            best_score = score
            best_match = fibo_uri
    
    return best_match if best_score >= threshold else None


def build_fibo_mapping_report(
    extraction: ExtractionResult,
    threshold: float = 0.85
) -> Dict[str, Any]:
    """
    Build a report of FIBO mappings for all extracted terms (Step 6d).
    """
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "mappings": {},
    }
    
    all_terms = (
        extraction.fund_houses
        | extraction.schemes
        | extraction.benchmarks
        | extraction.categories
    )
    
    for term in sorted(all_terms):
        fibo = map_to_fibo(term, threshold)
        if fibo:
            report["mappings"][term] = fibo
    
    coverage = len(report["mappings"]) / len(all_terms) if all_terms else 0
    report["coverage"] = coverage
    
    logger.info(f"[extraction] FIBO mapping: {len(report['mappings'])} / {len(all_terms)} "
                f"({coverage*100:.1f}%)")
    return report


# ──────────────────────────────────────────────────────────────────────────
# STEP 6E: Merge with Versioning
# ──────────────────────────────────────────────────────────────────────────

def merge_taxonomy_delta(
    extraction: ExtractionResult,
    current_taxonomy: Dict[str, list] = None
) -> Tuple[Dict[str, list], Dict[str, Any]]:
    """
    Merge extracted delta into current taxonomy (Step 6e).
    Creates versioned backup, performs atomic write.
    
    Returns:
        (updated_taxonomy_dict, merge_report)
    """
    if current_taxonomy is None:
        import app.engine.taxonomy as tax_module
        current_taxonomy = tax_module.load_taxonomy()
    
    # Backup before merge
    backup_path = backup_taxonomy()
    
    # Initialize sets from current taxonomy
    updated = {
        "fund_houses": set(current_taxonomy.get("fund_houses", [])),
        "schemes": set(current_taxonomy.get("schemes", [])),
        "benchmarks": set(current_taxonomy.get("benchmarks", [])),
        "categories": set(current_taxonomy.get("categories", [])),
        "sub_categories": set(current_taxonomy.get("sub_categories", [])),
    }
    
    # Merge extraction
    updated["fund_houses"].update(extraction.fund_houses)
    updated["schemes"].update(extraction.schemes)
    updated["benchmarks"].update(extraction.benchmarks)
    updated["categories"].update(extraction.categories)
    updated["sub_categories"].update(extraction.sub_categories)
    
    # Convert back to sorted lists
    result = {k: sorted(v) for k, v in updated.items()}
    
    # Atomic write
    write_taxonomy_atomic(result)
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backup_path": str(backup_path),
        "added": {
            "fund_houses": len(updated["fund_houses"]) - len(set(current_taxonomy.get("fund_houses", []))),
            "schemes": len(updated["schemes"]) - len(set(current_taxonomy.get("schemes", []))),
            "benchmarks": len(updated["benchmarks"]) - len(set(current_taxonomy.get("benchmarks", []))),
        },
    }
    
    logger.info(f"[extraction] Merged delta: {report['added']['fund_houses']} new fund houses, "
                f"{report['added']['schemes']} new schemes")
    return result, report


# ──────────────────────────────────────────────────────────────────────────
# STEP 6F: Neo4j Graph Node Generation
# ──────────────────────────────────────────────────────────────────────────

def generate_graph_nodes(extraction: ExtractionResult) -> Dict[str, list]:
    """
    Generate Neo4j node and relationship definitions (Step 6f).
    
    Returns:
        dict with keys "nodes", "relationships"
    """
    nodes = []
    relationships = []
    
    # Fund house nodes
    for house in extraction.fund_houses:
        nodes.append({
            "label": "FundHouse",
            "properties": {
                "name": house,
                "normalized": normalize_text(house),
                "source": "taxonomy_extractor",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        })
    
    # Scheme nodes
    for scheme in extraction.schemes:
        nodes.append({
            "label": "Scheme",
            "properties": {
                "name": scheme,
                "normalized": normalize_text(scheme),
                "source": "taxonomy_extractor",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        })
    
    # Category nodes
    for category in extraction.categories:
        nodes.append({
            "label": "Category",
            "properties": {
                "name": category,
                "source": "taxonomy_extractor",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        })
    
    logger.info(f"[extraction] Generated {len(nodes)} graph nodes for extraction")
    
    return {
        "nodes": nodes,
        "relationships": relationships,
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 6G: NER Hot-Reload
# ──────────────────────────────────────────────────────────────────────────

_NER_MODEL_CACHE = None


def reload_ner_model(force: bool = False) -> None:
    """
    Reload NER model without restarting (Step 6g).
    Used after taxonomy.json updates to recognize new terms.
    """
    global _NER_MODEL_CACHE
    
    if not config.GLINER_MODEL_ID:
        logger.info("[extraction] GliNER not configured, skipping hot-reload")
        return
    
    try:
        from gliner import GLiNER
        
        if force or _NER_MODEL_CACHE is None:
            logger.info(f"[extraction] Loading GliNER model: {config.GLINER_MODEL_ID}")
            _NER_MODEL_CACHE = GLiNER.from_pretrained(config.GLINER_MODEL_ID)
            logger.info("[extraction] GliNER model reloaded")
    except Exception as e:
        logger.error(f"[extraction] Failed to reload NER model: {e}")


def get_ner_model():
    """Get the cached NER model, loading if necessary."""
    global _NER_MODEL_CACHE
    if _NER_MODEL_CACHE is None:
        reload_ner_model(force=True)
    return _NER_MODEL_CACHE


if __name__ == "__main__":
    # Quick test of extraction pipeline
    test_text = """
    Fund House: Aditya Birla Sun Life AMC Limited
    Scheme: Aditya Birla Sun Life Frontline Equity Fund
    Benchmark: NSE Nifty 50 Index
    Category: Equity
    Sub-Category: Large Cap
    
    SEBI Regulation 16C: Fund houses must comply with NAV disclosure requirements.
    Redemption and Suspension policies apply.
    """
    
    result = ner_circular_extract(test_text, use_gliner=False)
    print(f"Extracted: {result.to_dict()}")
    
    fibo_report = build_fibo_mapping_report(result)
    print(f"FIBO mapping: {fibo_report}")
