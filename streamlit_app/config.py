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

# ── CLAUDE ────────────────────────────────────────────────────────────
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

CLAUDE_MODEL_RELATIONS = os.environ.get("CLAUDE_MODEL_RELATIONS", "claude-sonnet-4-6")
CLAUDE_MODEL_LIGHT = os.environ.get("CLAUDE_MODEL_LIGHT", "claude-haiku-4-5-20251001")

# Vision (image extraction during indexing) — throttle + model.
CLAUDE_VISION_MODEL = os.environ.get("CLAUDE_VISION_MODEL", "claude-sonnet-4-6")
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

# ── NER ────────────────────────────────────────────────────────────────
GLINER_MODEL_ID   = os.environ.get("GLINER_MODEL_ID", "urchade/gliner_medium-v2.1")
GLINER_LABELS     = [
    "mutual fund scheme name", "fund house", "benchmark index",
    "fund manager", "asset class", "sector",
]
GLINER_THRESHOLD  = 0.4

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