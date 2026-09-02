"""
ner_pipeline.py
================
Layer A — spaCy EntityRuler + Matcher + gazetteer  (rule-based, high precision)
Layer B — GLiNER zero/few-shot                     (generalization)
Layer C — LLM (Vertex/Gemini) relation extraction  (typed triples, context-aware)

Runs Layer A+B on CHILD chunks (small, precise spans).
Runs Layer C on PARENT chunks (needs surrounding context to find relations).
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List

import config
import llm_text_client
import taxonomy as taxonomy_mod

_nlp = None
_gliner_model = None
_gazetteer_cache = None


# ── LAYER A: RULE-BASED ────────────────────────────────────────────────
_ISIN_RE      = re.compile(r"\bIN[EF][A-Z0-9]{9}\b")
_NAV_RE       = re.compile(r"\bNAV\b.{0,20}?(₹?\s?[\d,]+\.\d{2,4})", re.I)
_AUM_RE       = re.compile(r"\bAUM\b.{0,20}?(₹?\s?[\d,]+\.?\d*\s?(Cr|Lakh|crore|lakh))", re.I)
_SEBI_RE      = re.compile(r"SEBI/[A-Z0-9/\-]+/\d{4}[-/]\d{2,4}", re.I)
_DATE_RE      = re.compile(r"\b\d{1,2}[-/](?:\d{1,2}|[A-Za-z]{3,9})[-/]\d{2,4}\b")


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.blank("en")
        ruler = _nlp.add_pipe("entity_ruler")
        gaz = _get_gazetteer()
        patterns = []
        for name in gaz.get("fund_houses", []):
            patterns.append({"label": "FUND_HOUSE", "pattern": name})
        for name in gaz.get("scheme_names", []):
            patterns.append({"label": "SCHEME_NAME", "pattern": name})
        for name in gaz.get("benchmarks", []):
            patterns.append({"label": "BENCHMARK", "pattern": name})
        ruler.add_patterns(patterns)
    return _nlp


def _get_gazetteer():
    global _gazetteer_cache
    if _gazetteer_cache is None:
        _gazetteer_cache = taxonomy_mod.load_taxonomy()
    return _gazetteer_cache


_query_ner_cache: Dict[str, List[Dict[str, Any]]] = {}

_COMMON_DOMAIN_ENTITIES = [
    ("Adani Enterprises", "FUND_HOUSE"),
    ("Adani Group", "FUND_HOUSE"),
    ("Mutual Funds", "MUTUAL_FUND_SCHEME_NAME"),
    ("Mutual Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Large Cap Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Large Cap", "MUTUAL_FUND_SCHEME_NAME"),
    ("Mid Cap Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Mid Cap", "MUTUAL_FUND_SCHEME_NAME"),
    ("Small Cap Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Small Cap", "MUTUAL_FUND_SCHEME_NAME"),
    ("Flexi Cap Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Flexi Cap", "MUTUAL_FUND_SCHEME_NAME"),
    ("Multi Cap Fund", "MUTUAL_FUND_SCHEME_NAME"),
    ("Multi Cap", "MUTUAL_FUND_SCHEME_NAME"),
    ("Solution Oriented Schemes", "SCHEME_CATEGORY"),
    ("Other Schemes", "SCHEME_CATEGORY"),
    ("Infrastructure Investment Trusts", "ASSET_CLASS"),
    ("InvITs", "ASSET_CLASS"),
    ("InvIT", "ASSET_CLASS"),
    ("AMC", "FUND_HOUSE"),
    ("SEBI", "REGULATOR"),
    ("EBITDA", "FINANCIAL_METRIC"),
    ("Revenue", "FINANCIAL_METRIC"),
    ("PAT", "FINANCIAL_METRIC"),
]

def layer_a_rule_ner(text: str) -> List[Dict[str, Any]]:
    ents: List[Dict[str, Any]] = []

    for m in _ISIN_RE.finditer(text):
        ents.append({"text": m.group(), "label": "ISIN", "start": m.start(), "end": m.end(), "layer": "A"})
    for m in _NAV_RE.finditer(text):
        ents.append({"text": m.group(1), "label": "NAV", "start": m.start(1), "end": m.end(1), "layer": "A"})
    for m in _AUM_RE.finditer(text):
        ents.append({"text": m.group(1), "label": "AUM", "start": m.start(1), "end": m.end(1), "layer": "A"})
    for m in _SEBI_RE.finditer(text):
        ents.append({"text": m.group(), "label": "SEBI_CIRCULAR", "start": m.start(), "end": m.end(), "layer": "A"})
    for m in _DATE_RE.finditer(text):
        ents.append({"text": m.group(), "label": "DATE", "start": m.start(), "end": m.end(), "layer": "A"})

    # Exact fast-track matching for core financial & regulatory domain phrases
    text_lower = text.lower()
    for phrase, label in _COMMON_DOMAIN_ENTITIES:
        idx = text_lower.find(phrase.lower())
        while idx != -1:
            ents.append({
                "text": text[idx : idx + len(phrase)],
                "label": label,
                "start": idx,
                "end": idx + len(phrase),
                "layer": "A"
            })
            idx = text_lower.find(phrase.lower(), idx + len(phrase))

    nlp = _get_nlp()
    doc = nlp(text)
    for ent in doc.ents:
        ents.append({"text": ent.text, "label": ent.label_,
                     "start": ent.start_char, "end": ent.end_char, "layer": "A"})
    return ents


# ── LAYER B: GLiNER ────────────────────────────────────────────────────
_NER_CACHE_MAX = 2000
_query_ner_cache: Dict[str, List[Dict[str, Any]]] = {}
_ner_cache_hits = 0
_ner_cache_misses = 0


def get_ner_cache_stats() -> Dict[str, Any]:
    total = _ner_cache_hits + _ner_cache_misses
    return {
        "hits": _ner_cache_hits,
        "misses": _ner_cache_misses,
        "hit_rate": round(_ner_cache_hits / max(total, 1), 3),
        "cache_size": len(_query_ner_cache),
    }


import threading
_NER_CACHE_LOCK = threading.Lock()

def _ner_cache_get(text: str) -> Optional[List[Dict[str, Any]]]:
    global _ner_cache_hits
    with _NER_CACHE_LOCK:
        if text in _query_ner_cache:
            _ner_cache_hits += 1
            return _query_ner_cache[text]
    return None


def _ner_cache_set(text: str, result: List[Dict[str, Any]]) -> None:
    global _ner_cache_misses
    with _NER_CACHE_LOCK:
        _ner_cache_misses += 1
        if len(_query_ner_cache) >= _NER_CACHE_MAX:
            for k in list(_query_ner_cache.keys())[: _NER_CACHE_MAX // 10]:
                _query_ner_cache.pop(k, None)
        _query_ner_cache[text] = result


def _get_gliner():
    global _gliner_model
    if _gliner_model is None:
        try:
            from gliner import GLiNER
            print("  [ner-b] Loading GLiNER…", flush=True)
            onnx_path = config.PROJECT_ROOT / "models" / "gliner_quantized.onnx"
            if config.ENABLE_ONNX_GLINER and onnx_path.exists():
                try:
                    _gliner_model = GLiNER.from_pretrained(str(onnx_path.parent), load_onnx=True)
                    print("  [ner-b] ONNX Quantized GLiNER ready.", flush=True)
                    return _gliner_model
                except Exception as exc:
                    print(f"  [ner-b] ONNX load failed ({exc}) — falling back to PyTorch.", flush=True)

            try:
                _gliner_model = GLiNER.from_pretrained(config.GLINER_MODEL_ID, local_files_only=True)
            except Exception:
                _gliner_model = GLiNER.from_pretrained(config.GLINER_MODEL_ID)
        except Exception as exc:
            print(f"  [ner-b] GLiNER unavailable (AppLocker/PyTorch policy): {exc}", flush=True)
            _gliner_model = False
    return _gliner_model if _gliner_model is not False else None


def warmup_ner_models() -> None:
    """Pre-load spaCy + GLiNER at startup. Call once from app.py."""
    print("  [NER Warmup] Loading spaCy EntityRuler...", flush=True)
    _get_nlp()
    print("  [NER Warmup] Loading GLiNER model...", flush=True)
    _get_gliner()
    print("  [NER Warmup] Done — both models cached in memory.", flush=True)


def layer_b_gliner(text: str, labels: list[str] = None) -> List[Dict[str, Any]]:
    model = _get_gliner()
    if not model:
        return []
    target_labels = labels or config.GLINER_LABELS
    raw = model.predict_entities(text, target_labels, threshold=config.GLINER_THRESHOLD)
    return [{
        "text": r["text"], "label": r["label"].upper().replace(" ", "_"),
        "start": r["start"], "end": r["end"],
        "score": round(float(r["score"]), 3), "layer": "B",
    } for r in raw]


def run_layers_ab(
    text: str,
    skip_gliner: bool = False,
    is_query: bool = False,
    domain_intent: str = None,
) -> List[Dict[str, Any]]:
    """De-duped union of Layer A + B entities on one child chunk or query."""
    if is_query:
        cached = _ner_cache_get(text)
        if cached is not None:
            return cached

    ents = layer_a_rule_ner(text)

    labels = config.get_gliner_labels(domain_intent) if domain_intent else config.GLINER_LABELS
    should_run_gliner = (
        not skip_gliner and (
            not ents or len(text) <= 500
        )
    )

    if should_run_gliner:
        try:
            ents += layer_b_gliner(text, labels=labels)
        except Exception as e:
            print(f"  [NER Notice] GLiNER Layer B skipped: {e}", flush=True)

    seen, deduped = set(), []
    for e in sorted(ents, key=lambda x: (x["start"], -x["end"])):
        key = (e["start"], e["end"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    if is_query and len(text) <= 500:
        _ner_cache_set(text, deduped)
    return deduped


# ── LAYER C: LLM RELATION EXTRACTION ───────────────────────────────────
_RELATION_PROMPT = """You extract typed relationships between mutual-fund entities from
the text below. Use ONLY entities explicitly present in the text.

Allowed predicates: manages, holds, governs, benchmarks_against, invests_in,
regulated_by, part_of, launched_on.

TEXT:
\"\"\"{text}\"\"\"

DETECTED ENTITIES (for reference, from an earlier NER pass):
{entities}

Return a JSON array of triples, each:
{{"subject": "...", "predicate": "...", "object": "...",
  "confidence": 0.0-1.0, "source_chunk_id": "{chunk_id}"}}

If no clear relation exists, return an empty array [].
"""


def layer_c_relations(parent_text: str, parent_id: str,
                       known_entities: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    ent_str = ", ".join(sorted({e["text"] for e in (known_entities or [])})) or "none detected"
    prompt = _RELATION_PROMPT.format(text=parent_text[:3000], entities=ent_str, chunk_id=parent_id)
    result = llm_text_client.call_llm_json(prompt, model_id=config.CLAUDE_MODEL_RELATIONS)
    if not isinstance(result, list):
        return []
    clean = []
    for r in result:
        if not isinstance(r, dict):
            continue
        if not all(k in r for k in ("subject", "predicate", "object")):
            continue
        r["source_chunk_id"] = parent_id
        r["confidence"] = float(r.get("confidence", 0.5))
        clean.append(r)
    return clean


def run_full_ner_for_chunk_set(children: List[Dict], parents: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Orchestrates all 3 layers for one document's chunks.
    Returns {"entities": [...per-child...], "relations": [...per-parent...]}
    """
    all_entities, all_relations = [], []
    parent_entity_map: Dict[str, List[Dict]] = {}

    for child in children:
        raw_ents = run_layers_ab(child["text"])
        # P0-3 Fix: Always copy dict to prevent mutating shared cached entity objects
        ents = []
        for e in raw_ents:
            e_copy = dict(e)
            e_copy["child_id"] = child["child_id"]
            e_copy["parent_id"] = child["parent_id"]
            ents.append(e_copy)
        all_entities.extend(ents)
        parent_entity_map.setdefault(child["parent_id"], []).extend(ents)


    for parent_id, parent in parents.items():
        rels = layer_c_relations(parent["text"], parent_id,
                                  known_entities=parent_entity_map.get(parent_id, []))
        all_relations.extend(rels)

    return {"entities": all_entities, "relations": all_relations}