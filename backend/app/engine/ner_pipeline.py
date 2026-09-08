# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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

from app.engine import config
from app.engine import llm_text_client
from app.engine import taxonomy as taxonomy_mod

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
        gaz = _get_gazetteer()
        patterns = []
        for name in gaz.get("fund_houses", []):
            patterns.append({"label": "FUND_HOUSE", "pattern": name})
        for name in gaz.get("scheme_names", []):
            patterns.append({"label": "SCHEME_NAME", "pattern": name})
        for name in gaz.get("benchmarks", []):
            patterns.append({"label": "BENCHMARK", "pattern": name})
        # An entity_ruler with no patterns matches nothing and emits spaCy's
        # W036 warning on *every* call. Only add the pipe when the gazetteer
        # actually produced something.
        if patterns:
            ruler = _nlp.add_pipe("entity_ruler")
            ruler.add_patterns(patterns)
            print(f"  [ner-a] entity_ruler loaded with {len(patterns)} gazetteer patterns", flush=True)
        else:
            print("  [ner-a] gazetteer is empty — entity_ruler disabled "
                  "(rebuild taxonomy.json to enable fund-house/scheme matching)", flush=True)
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
def _get_gliner():
    global _gliner_model
    if _gliner_model is None:
        from gliner import GLiNER
        print("  [ner-b] Loading GLiNER…", flush=True)
        try:
            _gliner_model = GLiNER.from_pretrained(config.GLINER_MODEL_ID, local_files_only=True)
        except Exception:
            _gliner_model = GLiNER.from_pretrained(config.GLINER_MODEL_ID)
    return _gliner_model


def layer_b_gliner(text: str) -> List[Dict[str, Any]]:
    model = _get_gliner()
    raw = model.predict_entities(text, config.GLINER_LABELS, threshold=config.GLINER_THRESHOLD)
    return [{
        "text": r["text"], "label": r["label"].upper().replace(" ", "_"),
        "start": r["start"], "end": r["end"],
        "score": round(float(r["score"]), 3), "layer": "B",
    } for r in raw]


def clear_ner_cache():
    """Clears the query NER cache."""
    global _query_ner_cache
    _query_ner_cache.clear()


def run_layers_ab(text: str, min_confident_entities: int = 2, min_confidence: float = 0.8) -> List[Dict[str, Any]]:
    """
    De-duped union of Layer A (rules/gazetteer) + Layer B (GLiNER) entities with intelligent saturation bypass.
    If Layer A finds >= min_confident_entities confident matches, skip heavy GLiNER model inference.
    """
    if text in _query_ner_cache:
        return _query_ner_cache[text]

    ents = layer_a_rule_ner(text)
    # Ensure all Layer A entities have confidence attribute (1.0 for deterministic rule matches)
    for e in ents:
        if "confidence" not in e:
            e["confidence"] = 1.0
        if "score" not in e:
            e["score"] = 1.0

    confident_layer_a = [e for e in ents if e.get("confidence", 1.0) >= min_confidence]
    
    # Saturation check:
    # 1. Skip GLiNER if Layer A found >= min_confident_entities
    # 2. Or if text is short (<=300 chars) and has at least 1 high-confidence entity
    skip_gliner = config.ENABLE_GLINER_SKIP and (
        len(confident_layer_a) >= min_confident_entities or (len(confident_layer_a) >= 1 and len(text) <= 300)
    )

    if not skip_gliner:
        try:
            gliner_ents = layer_b_gliner(text)
            for ge in gliner_ents:
                if "confidence" not in ge:
                    ge["confidence"] = ge.get("score", 0.5)
            ents += gliner_ents
        except Exception as e:
            print(f"  [ner-b] GLiNER failed, skipping: {e}", flush=True)

    seen, deduped = set(), []
    for e in sorted(ents, key=lambda x: (x["start"], -x["end"])):
        key = (e["start"], e["end"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    if len(text) <= 500:
        _query_ner_cache[text] = deduped
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
    result = llm_text_client.call_llm_json(prompt, model_id=config.GROQ_MODEL_RELATIONS)
    if not isinstance(result, list):
        # call_llm_json returns None for an API failure *and* for unparseable
        # output. Either way it is a miss, not "this chunk has no relations" —
        # say so, or the relation count silently reads as a legitimate zero.
        print(f"  [ner-c] no usable relation JSON for {parent_id} "
              f"(model={config.GROQ_MODEL_RELATIONS}, got {type(result).__name__})", flush=True)
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
        ents = run_layers_ab(child["text"])
        for e in ents:
            e["child_id"] = child["child_id"]
            e["parent_id"] = child["parent_id"]
        all_entities.extend(ents)
        parent_entity_map.setdefault(child["parent_id"], []).extend(ents)

    for parent_id, parent in parents.items():
        rels = layer_c_relations(parent["text"], parent_id,
                                  known_entities=parent_entity_map.get(parent_id, []))
        all_relations.extend(rels)

    return {"entities": all_entities, "relations": all_relations}
