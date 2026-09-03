# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Application settings — loaded from environment / .env (WS1: secrets management)."""
import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "NuSummit ContextGraph API"
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    query_engine: str = "legacy"                     # "legacy" | "v2" | "shadow" | "canary"
    canary_percentage: int = 0                       # 0 to 100 for canary traffic routing
    active_corpus_version: str = "v2_baseline_20260814"

    # --- AWS (prod deployment) ---
    aws_region: str = "ap-south-1"
    groq_secret_id: str = ""
    groq_secret_json_key: str = "GROQ_API_KEY"

    # --- Groq LLM Configuration (API-key based) ---
    llm_provider: str = "groq"
    groq_api_key: str = ""
    
    llm_model: str = "openai/gpt-oss-120b"
    llm_fast_model: str = "openai/gpt-oss-20b"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.0-flash"
    
    # Provider Fallbacks (Configurable - DISABLED BY DEFAULT)
    enable_multi_provider_fallback: bool = False      # Default False: only primary provider (Groq) is used
    enable_local_llm_fallback: bool = False           # Default False: local small model disabled by default
    local_llm_endpoint: str = "http://127.0.0.1:11434/v1"
    local_llm_model: str = "qwen2.5:3b"
    
    llm_max_tokens: int = 2048
    llm_max_retries: int = 3
    llm_max_concurrency: int = 4                      # client-side rate limiting

    # --- Guardrails & Invalidation Controls ---
    enable_pre_retrieval_guardrails: bool = True      # Short-circuits safety refusals in <5ms
    enable_cache_invalidation_on_ingest: bool = True  # Purges cache for target corpus on document activation

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "contextgraph"
    neo4j_database: str = "neo4j"

    # --- Vector store (FAISS, in-process, persisted to disk) ---
    faiss_dir: str = "./data/faiss"                  # index.faiss + payloads.json live here
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # fastembed local model
    embedding_dim: int = 384

    # --- Retrieval / context engineering (WS5d) ---
    context_token_budget: int = 4000
    max_traversal_depth: int = 3
    vector_top_k: int = 8
    min_context_quality_score: float = 0.3

    # --- Ingestion ---
    chunk_max_tokens: int = 400
    upload_dir: str = "./data/uploads"
    corpus_dir: str = "./data/corpus"

    # --- Auth (WS: login) ---
    # HMAC signing key for session tokens. Override with a long random value
    # via AUTH_SECRET_KEY in .env for any non-local environment — the
    # fallback below is only safe for local dev.
    auth_secret_key: str = "dev-only-insecure-secret-change-me"
    auth_session_ttl_minutes: int = 480               # 8h; "Remember Me" uses a longer client-side TTL
    auth_session_ttl_minutes_remember: int = 20_160    # 14 days
    auth_users_path: str = "app/auth/data/users.json"  # JSON store today; swap for a DB repository later

    @model_validator(mode="after")
    def _resolve_secret_from_aws(self) -> "Settings":
        """Load the Groq key from AWS Secrets Manager when configured."""
        if self.groq_api_key or not self.groq_secret_id:
            return self
        try:
            import json as _json
            import boto3

            sm = boto3.client("secretsmanager", region_name=self.aws_region)
            secret = sm.get_secret_value(SecretId=self.groq_secret_id)["SecretString"]
            try:
                value = _json.loads(secret).get(self.groq_secret_json_key, "")
            except (_json.JSONDecodeError, AttributeError):
                value = secret
            if value:
                object.__setattr__(self, "groq_api_key", value)
                logger.info("Loaded Groq key from Secrets Manager: %s", self.groq_secret_id)
            else:
                logger.warning("Secret %s has no field %r", self.groq_secret_id, self.groq_secret_json_key)
        except Exception as exc:
            logger.warning("Could not load Groq key from Secrets Manager (%s): %s", self.groq_secret_id, exc)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
