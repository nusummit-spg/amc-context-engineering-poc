"""
Configuration schema for repair engine.
"""
from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field

class RepairConfig(BaseModel):
    """Configuration for repair engine behavior."""

    # Patch Layer Configuration
    patch_ttl_days: int = Field(default=7, ge=1, le=365)
    patch_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    use_redis: bool = Field(default=False)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_key_prefix: str = Field(default="amc_repair:")

    # Evaluation Configuration
    enable_tier1_rules: bool = Field(default=True)
    tier1_stop_confidence: float = Field(default=0.90, ge=0.0, le=1.0)

    # Governance Batch Configuration
    auto_approve_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    batch_size: int = Field(default=100, ge=1, le=1000)

    # Graph Adapter Configuration
    graph_adapter: Literal["neo4j", "memory", "custom"] = Field(default="memory")
    graph_uri: Optional[str] = Field(default=None)
    graph_user: Optional[str] = Field(default=None)
    graph_password: Optional[str] = Field(default=None)
    graph_database: str = Field(default="neo4j")
