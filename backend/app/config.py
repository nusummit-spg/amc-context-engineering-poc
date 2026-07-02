"""Application settings — loaded from environment / .env (WS1: secrets management)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "NuSummit ContextGraph API"
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
