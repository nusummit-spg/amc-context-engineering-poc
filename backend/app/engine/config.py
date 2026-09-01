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
TAXONOMY_BACKUP_DIR = PROJECT_ROOT / "taxonomy_backups"
FAISS_DIR      = PROJECT_ROOT / "faiss_indexes"
LOG_DIR        = PROJECT_ROOT / "logs"
for d in (FAISS_DIR, LOG_DIR, TAXONOMY_BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)

# S3 bucket new source documents are uploaded to (reindex_from_s3.py syncs
# this into DATA_DIR before running build_index). Empty = sync step skipped.
CORPUS_BUCKET = os.environ.get("CORPUS_BUCKET", "")

# ── GROQ ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# On AWS the key isn't on disk — fetch it from Secrets Manager when a secret id
# is configured and GROQ_API_KEY is empty.
_SECRET_ID = os.environ.get("GROQ_SECRET_ID", "")
if not GROQ_API_KEY and _SECRET_ID:
    try:
        import json as _json
        import boto3
        _sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        _secret = _sm.get_secret_value(SecretId=_SECRET_ID)["SecretString"]
        _field = os.environ.get("GROQ_SECRET_JSON_KEY", "GROQ_API_KEY")
        try:
            GROQ_API_KEY = _json.loads(_secret).get(_field, "")
        except (_json.JSONDecodeError, AttributeError):
            GROQ_API_KEY = _secret
    except Exception as _exc:  # noqa: BLE001
        print(f"  [config] Could not load key from Secrets Manager ({_SECRET_ID}): {_exc}", flush=True)

GROQ_MODEL_RELATIONS = os.environ.get("GROQ_MODEL_RELATIONS", "qwen/qwen3.8-27b")
GROQ_MODEL_LIGHT = os.environ.get("GROQ_MODEL_LIGHT", "qwen/qwen3.8-27b")

# Vision (image extraction during indexing) — throttle + model.
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")
GROQ_MAX_CONCURRENT_VISION = int(os.environ.get("GROQ_MAX_CONCURRENT_VISION", "4"))
GROQ_VISION_RPM = int(os.environ.get("GROQ_VISION_RPM", "50"))

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
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "contextgraph")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# ── PII / DPDP ─────────────────────────────────────────────────────────
PII_SCRUB_ENABLED = os.environ.get("PII_SCRUB_ENABLED", "true").lower() == "true"

# ── EFFICIENCY INITIATIVE FEATURE FLAGS ────────────────────────────────
ENABLE_HYDE_CACHE = os.environ.get("ENABLE_HYDE_CACHE", "true").lower() == "true"
ENABLE_GLINER_SKIP = os.environ.get("ENABLE_GLINER_SKIP", "true").lower() == "true"
ENABLE_CYPHER_AUTO_CORRECTION = os.environ.get("ENABLE_CYPHER_AUTO_CORRECTION", "true").lower() == "true"
ENABLE_SMART_VECTOR_PRUNING = os.environ.get("ENABLE_SMART_VECTOR_PRUNING", "true").lower() == "true"
ENABLE_SEMANTIC_CACHE_WARMUP = os.environ.get("ENABLE_SEMANTIC_CACHE_WARMUP", "true").lower() == "true"

# ── MISC ──────────────────────────────────────────────────────────────
SUPPORTED_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".pptx", ".txt"}
VERBOSE = True


# ── ACQUISITION CHANNELS (Phase 0/1 config) ───────────────────────────────
# SEBI RSS feed for regulatory circulars
SEBI_RSS_URL = os.environ.get("SEBI_RSS_URL", "https://www.sebi.gov.in/rss/circulars_en.xml")

# AMFI NAV/SID/AUM endpoints
AMFI_NAV_URL = os.environ.get("AMFI_NAV_URL", "https://www.amfiindia.com/spages/NAVAll.txt")
AMFI_SID_SAI_URL = os.environ.get("AMFI_SID_SAI_URL", "https://www.amfiindia.com/spages/SID_SAI_Listing_url.txt")
AMFI_MONTHLY_AUM_URL = os.environ.get("AMFI_MONTHLY_AUM_URL", "https://www.amfiindia.com/spages/AUM_April_2023.txt")

# Member portal inbox directory (Channel C: folder watcher)
MEMBER_PORTAL_INBOX = Path(os.environ.get("MEMBER_PORTAL_INBOX", 
                                           str(PROJECT_ROOT / "data" / "member_inbox")))
MEMBER_PORTAL_INBOX.mkdir(parents=True, exist_ok=True)

# Taxonomy/retrieval configuration
RETRIEVAL_ACTIVE_ONLY = os.environ.get("RETRIEVAL_ACTIVE_ONLY", "true").lower() == "true"
CACHE_GRAPH_MODE = os.environ.get("CACHE_GRAPH_MODE", "memory").lower()  # memory|redis|none

# RSS/SEBI polling rates (requests per minute)
SEBI_POLL_INTERVAL_MINUTES = int(os.environ.get("SEBI_POLL_INTERVAL_MINUTES", "5"))
SEBI_DOWNLOAD_RATE_LIMIT = int(os.environ.get("SEBI_DOWNLOAD_RATE_LIMIT", "3"))  # per minute
