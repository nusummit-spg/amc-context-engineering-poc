# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
config.py — single source of truth for all env vars, paths, and constants.
Reuses the same Vertex/Gemini credential pattern as faiss_store.py.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── PATHS ────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).resolve().parent
DATA_DIR       = PROJECT_ROOT / "data" / "AMC"
AMFI_DIR       = PROJECT_ROOT / "data" / "AMFI"
SUBCLASS_DIR   = PROJECT_ROOT / "data" / "Sub Classification"
TAXONOMY_PATH  = PROJECT_ROOT / "taxonomy.json"
FAISS_DIR      = PROJECT_ROOT / "faiss_indexes"
LOG_DIR        = PROJECT_ROOT / "logs"
for d in (FAISS_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── LLM PROVIDERS & LITELLM ─────────────────────────────────────────────
PRIMARY_LLM_PROVIDER = os.environ.get("PRIMARY_LLM_PROVIDER", "groq").lower()

# Groq Configuration (Primary testing provider)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL_LIGHT = os.environ.get("GROQ_MODEL_LIGHT", "groq/llama-3.1-8b-instant")
GROQ_MODEL_RELATIONS = os.environ.get("GROQ_MODEL_RELATIONS", "groq/llama-3.1-8b-instant")


# ── CLAUDE / ANTHROPIC ──────────────────────────────────────────────────
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

# On AWS the key isn't on disk — fetch it from Secrets Manager when a secret id
# is configured and CLAUDE_API_KEY is empty. Handles a JSON secret (reads the
# named field) or a bare-string secret. Never blocks import on failure.
_SECRET_ID = os.environ.get("ANTHROPIC_SECRET_ID", "")
if not CLAUDE_API_KEY and _SECRET_ID:
    try:
        import json as _json
        import boto3
        _sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        _secret = _sm.get_secret_value(SecretId=_SECRET_ID)["SecretString"]
        _field = os.environ.get("ANTHROPIC_SECRET_JSON_KEY", "ANTHROPIC_API_KEY")
        try:
            CLAUDE_API_KEY = _json.loads(_secret).get(_field, "")
        except (_json.JSONDecodeError, AttributeError):
            CLAUDE_API_KEY = _secret
    except Exception as _exc:  # noqa: BLE001
        print(f"  [config] Could not load key from Secrets Manager ({_SECRET_ID}): {_exc}", flush=True)

CLAUDE_MODEL_RELATIONS = os.environ.get("CLAUDE_MODEL_RELATIONS", "claude-haiku-4-5-20251001")
CLAUDE_MODEL_LIGHT = os.environ.get("CLAUDE_MODEL_LIGHT", "claude-haiku-4-5-20251001")

# Vision (image extraction during indexing) — throttle + model.
CLAUDE_VISION_MODEL = os.environ.get("CLAUDE_VISION_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MAX_CONCURRENT_VISION = int(os.environ.get("CLAUDE_MAX_CONCURRENT_VISION", "4"))
CLAUDE_VISION_RPM = int(os.environ.get("CLAUDE_VISION_RPM", "50"))

# ── SMART EXTRACTION — the actual rate-limit fix ────────────────────────────
SMART_EXTRACTION = os.environ.get("SMART_EXTRACTION", "true").lower() == "true"
LOCAL_TEXT_SUFFICIENCY_THRESHOLD = int(os.environ.get("LOCAL_TEXT_SUFFICIENCY_THRESHOLD", "400"))
EXTRACTION_CACHE_DIR = PROJECT_ROOT / "logs" / "extraction_cache"
EXTRACTION_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── VERTEX / GEMINI (same pattern as faiss_store._get_gemini_client) ─────
VERTEX_KEY_PATH  = PROJECT_ROOT / "vertex_key.json"
GOOGLE_CLOUD_PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_REGION   = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
VERTEX_MODEL_RELATIONS = os.environ.get("VERTEX_MODEL_RELATIONS", "gemini-2.5-pro")
VERTEX_MODEL_LIGHT     = os.environ.get("VERTEX_MODEL_LIGHT", "gemini-2.5-flash")
GEMINI_API_KEY          = os.environ.get("GEMINI_API_KEY", "")

# ── CHUNKING (reused verbatim from faiss_store.py so both indexes align) ─
PARENT_CHUNK_SIZE    = 1200
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE     = 250
CHILD_CHUNK_OVERLAP  = 50

# ── FEATURE FLAGS (cheap insurance for staged rollout) ──────────────────────
ENABLE_CONTEXT_BUDGET    = os.environ.get("ENABLE_CONTEXT_BUDGET", "true").lower() == "true"
ENABLE_INTENT_CACHE      = os.environ.get("ENABLE_INTENT_CACHE", "true").lower() == "true"
ENABLE_PARALLEL_RETRIEVAL = os.environ.get("ENABLE_PARALLEL_RETRIEVAL", "true").lower() == "true"
ENABLE_STREAMING         = os.environ.get("ENABLE_STREAMING", "true").lower() == "true"
ENABLE_ONNX_GLINER       = os.environ.get("ENABLE_ONNX_GLINER", "true").lower() == "true"
ENABLE_LANGDETECT        = os.environ.get("ENABLE_LANGDETECT", "true").lower() == "true"
ENABLE_GUARDRAILS_AI     = os.environ.get("ENABLE_GUARDRAILS_AI", "true").lower() == "true"
ENABLE_RRF_FUSION        = os.environ.get("ENABLE_RRF_FUSION", "true").lower() == "true"
ENABLE_TRIPLE_NOTATION   = os.environ.get("ENABLE_TRIPLE_NOTATION", "true").lower() == "true"
CACHE_GRAPH_MODE         = os.environ.get("CACHE_GRAPH_MODE", "smart").lower()  # "smart", "live", "skip"
RETRIEVAL_ACTIVE_ONLY    = os.environ.get("RETRIEVAL_ACTIVE_ONLY", "true").lower() == "true"
SEBI_RSS_URL             = os.environ.get("SEBI_RSS_URL", "https://www.sebi.gov.in/rss.html")
AMFI_NAV_URL             = os.environ.get("AMFI_NAV_URL", "https://portal.amfiindia.com/spages/NAVAll.txt")
MEMBER_PORTAL_INBOX      = PROJECT_ROOT / "data" / "AMC" / "member_portal_inbox"
MEMBER_PORTAL_INBOX.mkdir(parents=True, exist_ok=True)

# ── PER-DOMAIN CONVERSATION HISTORY WINDOW ──────────────────────────────────
INTENT_HISTORY_TURNS: dict = {
    "sebi_regulation":       3,   # regulatory context benefits from deeper history
    "esg_sustainability":    3,   # ESG multi-turn comparisons are common
    "financial_performance":  2,
    "fund_performance":      2,
    "corporate_governance":  2,
}



# ── NER ────────────────────────────────────────────────────────────────
GLINER_MODEL_ID   = os.environ.get("GLINER_MODEL_ID", "urchade/gliner_medium-v2.1")
GLINER_LABELS     = [
    "mutual fund scheme name", "fund house", "benchmark index",
    "fund manager", "asset class", "sector",
    "ESG metric", "sustainability initiative", "climate change adaptation",
    "carbon emission", "BRSR indicator", "financial metric", "regulatory requirement",
]
GLINER_THRESHOLD  = 0.4

GLINER_LABELS_BY_DOMAIN = {
    "sebi_regulation": [
        "mutual fund scheme name", "fund house", "regulatory requirement",
        "compliance rule", "clause", "penalty", "asset class",
    ],
    "esg_sustainability": [
        "ESG metric", "sustainability initiative", "climate change adaptation",
        "carbon emission", "BRSR indicator", "net zero target", "decarbonization",
    ],
    "financial_performance": [
        "financial metric", "revenue", "EBITDA", "credit rating",
        "debt ratio", "net worth", "AUM", "capital expenditure",
    ],
    "fund_performance": [
        "mutual fund scheme name", "fund house", "benchmark index",
        "fund manager", "asset allocation", "exit load", "expense ratio", "TER",
    ],
    "corporate_governance": [
        "governance obligation", "ERP", "rating provider", "audit",
        "board of directors", "compliance officer", "code of conduct",
    ],
}

def get_gliner_labels(domain_intent: str = "") -> list[str]:
    """Returns domain-specific GLiNER labels if domain_intent matches, else fallback to GLINER_LABELS."""
    if domain_intent and domain_intent in GLINER_LABELS_BY_DOMAIN:
        return GLINER_LABELS_BY_DOMAIN[domain_intent]
    return GLINER_LABELS

# ── ENTITY RESOLUTION (entity_resolver.py) ──────────────────────────────
# Cosine similarity floor for treating a graph node as a genuine match for a
# query entity mention (vs. naive substring containment).
SIMILARITY_MATCH_THRESHOLD = float(os.environ.get("SIMILARITY_MATCH_THRESHOLD", "0.65"))

# ── TEXT-TO-CYPHER (text_to_cypher.py) ──────────────────────────────────
# Row cap enforced on LLM-generated aggregation queries (added as a LIMIT
# clause if the model didn't include one).
CYPHER_MAX_ROWS = int(os.environ.get("CYPHER_MAX_ROWS", "25"))

# ── NEO4J ─────────────────────────────────────────────────────────────
NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# ── PII / DPDP ─────────────────────────────────────────────────────────
PII_SCRUB_ENABLED = os.environ.get("PII_SCRUB_ENABLED", "true").lower() == "true"

# ── MISC ──────────────────────────────────────────────────────────────
SUPPORTED_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".pptx", ".txt"}
VERBOSE = True
