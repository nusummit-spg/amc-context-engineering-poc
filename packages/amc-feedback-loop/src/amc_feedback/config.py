"""
Configuration schema for feedback loop.
Allows users to customize domain behavior without modifying code.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class FeedbackConfig(BaseModel):
    """Configuration for feedback loop behavior."""

    # Domain Configuration
    domain_name: str = Field(default="amc", description="Domain identifier (amc, wealth, etc.)")
    entity_types: List[str] = Field(
        default=["fund", "scheme", "amc", "regulation"],
        description="Entity types to recognize"
    )
    attribute_keywords: Dict[str, List[str]] = Field(
        default={
            "TER": ["ter", "expense ratio", "total expense", "expense"],
            "NAV": ["nav", "net asset value", "price"],
            "AUM": ["aum", "assets under management", "corpus"],
            "EXIT_LOAD": ["exit load", "exit penalty", "redemption fee"],
        },
        description="Attribute detection keywords"
    )

    # Entity Resolution
    entity_master_path: Optional[str] = Field(
        default=None,
        description="Path to entity catalog JSON file"
    )
    fuzzy_match_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum similarity for fuzzy matching"
    )

    # NER Configuration
    use_spacy: bool = Field(default=True, description="Enable spaCy rule-based layer")
    use_gliner: bool = Field(default=True, description="Enable GLiNER open-domain layer")
    gliner_model_id: str = Field(
        default="urchade/gliner_medium-v2.1",
        description="HuggingFace model ID for GLiNER"
    )
    enable_onnx: bool = Field(
        default=True,
        description="Use ONNX quantized GLiNER if available"
    )

    # Detection Thresholds
    dissatisfaction_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for correction detection"
    )
    correction_confidence_min: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to create correction patch"
    )

    # Passive Feedback
    enable_passive_capture: bool = Field(
        default=True,
        description="Enable automatic follow-up correction detection"
    )
    passive_timeout_seconds: int = Field(
        default=180,
        ge=30,
        description="Timeout for follow-up detection window"
    )

    # Storage
    database_adapter: str = Field(
        default="sqlite",
        description="Database adapter type (sqlite, postgresql, custom)"
    )
    evidence_adapter: str = Field(
        default="local",
        description="Evidence storage adapter (local, custom)"
    )
