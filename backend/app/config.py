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

    # --- AWS (prod deployment) ---
    aws_region: str = "ap-south-1"
    # If set (e.g. "/dev/microsoft-app-id") and the key below is empty, the key
    # is fetched from AWS Secrets Manager at startup. The secret may be a JSON
    # blob — anthropic_secret_json_key names the field to read (default
    # ANTHROPIC_API_KEY); if the secret is a bare string it's used as-is.
    # Local dev leaves anthropic_secret_id blank and uses ANTHROPIC_API_KEY.
    anthropic_secret_id: str = ""
    anthropic_secret_json_key: str = "ANTHROPIC_API_KEY"

    # --- LLM (Anthropic) ---
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"
    llm_fast_model: str = "claude-haiku-4-5"  # cheap classification calls
    llm_max_tokens: int = 16000
    llm_max_retries: int = 3
    llm_max_concurrency: int = 4  # client-side rate limiting

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "contextgraph"
    neo4j_database: str = "neo4j"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "amc_chunks"
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # fastembed local model
    embedding_dim: int = 384

    # --- Retrieval / context engineering (WS5d) ---
    context_token_budget: int = 12000
    max_traversal_depth: int = 3
    vector_top_k: int = 8
    min_context_quality_score: float = 0.3

    # --- Ingestion ---
    chunk_max_tokens: int = 400
    upload_dir: str = "./data/uploads"
    corpus_dir: str = "./data/corpus"

    @model_validator(mode="after")
    def _resolve_secret_from_aws(self) -> "Settings":
        """Load the Anthropic key from AWS Secrets Manager when configured.

        Only runs if the key is empty AND a secret id is provided, so local dev
        (key in .env, boto3 not installed) is unaffected. Handles both a JSON
        secret (reads anthropic_secret_json_key) and a bare-string secret.
        Failures degrade gracefully — the app still starts; only the LLM-backed
        routes will fail.
        """
        if self.anthropic_api_key or not self.anthropic_secret_id:
            return self
        try:
            import json as _json

            import boto3  # imported lazily; only needed on AWS

            sm = boto3.client("secretsmanager", region_name=self.aws_region)
            secret = sm.get_secret_value(SecretId=self.anthropic_secret_id)["SecretString"]
            try:
                value = _json.loads(secret).get(self.anthropic_secret_json_key, "")
            except (_json.JSONDecodeError, AttributeError):
                value = secret  # bare-string secret
            if value:
                object.__setattr__(self, "anthropic_api_key", value)
                logger.info("Loaded Anthropic key from Secrets Manager: %s",
                            self.anthropic_secret_id)
            else:
                logger.warning("Secret %s has no field %r",
                               self.anthropic_secret_id, self.anthropic_secret_json_key)
        except Exception as exc:  # noqa: BLE001 — never block startup on secret fetch
            logger.warning("Could not load Anthropic key from Secrets Manager (%s): %s",
                           self.anthropic_secret_id, exc)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
