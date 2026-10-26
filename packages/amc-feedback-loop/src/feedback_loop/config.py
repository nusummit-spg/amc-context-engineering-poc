"""
Runtime configuration for the Human Feedback Loop module.
All thresholds and tunable values live here so they can be changed
without a redeploy (load from env-vars or pass overrides at startup).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeedbackLoopConfig:
    # ── Passive-capture window ───────────────────────────────────────────────
    passive_window_minutes: int = 3          # 2–4 min per design; default 3

    # ── Dissatisfaction signal thresholds ────────────────────────────────────
    requery_similarity_threshold: float = 0.75   # cosine sim ≥ this → signal fires
    min_signals_required: int = 2                # 2-of-3 required to convert

    # ── Deduplication ────────────────────────────────────────────────────────
    dedup_window_minutes: int = 5            # session-level dedup window

    # ── Numeric accuracy rule ────────────────────────────────────────────────
    numeric_critical_delta_pct: float = 50.0   # ≥ 50 % deviation → critical
    numeric_high_delta_pct: float = 20.0       # ≥ 20 % → high
    numeric_medium_delta_pct: float = 10.0     # ≥ 10 % → medium

    # ── Trigger / retry ──────────────────────────────────────────────────────
    webhook_timeout_seconds: float = 5.0
    retry_max_attempts: int = 3
    retry_wait_seconds: float = 2.0

    # ── Correction-language pattern list ─────────────────────────────────────
    correction_patterns: list[str] = field(default_factory=lambda: [
        r"\bno[,.]?\s+that'?s?\s+wrong\b",
        r"\bactually\s+it'?s?\b",
        r"\bthat'?s?\s+not\s+right\b",
        r"\bshould\s+be\b",
        r"\bincorrect\b",
        r"\bwrong\s+(?:value|number|figure|data)\b",
    ])


DEFAULT_ATTRIBUTE_KEYWORDS: dict[str, list[str]] = {
    "TER": ["ter", "expense ratio", "total expense", "expense"],
    "NAV": ["nav", "net asset value", "price"],
    "AUM": ["aum", "assets under management", "corpus"],
    "EXIT_LOAD": ["exit load", "exit penalty", "redemption fee"],
}


@dataclass
class FeedbackConfig(FeedbackLoopConfig):
    domain_name: str = "amc"
    fuzzy_match_threshold: float = 0.70
    entity_types: list[str] = field(default_factory=lambda: ["fund", "scheme", "amc", "regulation"])
    attribute_keywords: dict[str, list[str]] = field(default_factory=lambda: DEFAULT_ATTRIBUTE_KEYWORDS.copy())
    entity_master_path: str | None = None
    use_spacy: bool = True
    use_gliner: bool = True
    gliner_model_id: str | None = None
    enable_onnx: bool = False
    dissatisfaction_threshold: float = 0.65
    correction_confidence_min: float = 0.60
    enable_passive_capture: bool = True
    passive_timeout_seconds: int = 180

    def __init__(self, **kwargs):
        """Initialize a new instance of FeedbackConfig.
        """
        super().__init__()
        self.domain_name = kwargs.get("domain_name", "amc")
        self.fuzzy_match_threshold = kwargs.get("fuzzy_match_threshold", 0.70)
        self.entity_types = kwargs.get("entity_types", ["fund", "scheme", "amc", "regulation"])
        self.attribute_keywords = kwargs.get("attribute_keywords", DEFAULT_ATTRIBUTE_KEYWORDS.copy())
        self.entity_master_path = kwargs.get("entity_master_path", None)
        self.use_spacy = kwargs.get("use_spacy", True)
        self.use_gliner = kwargs.get("use_gliner", True)
        self.gliner_model_id = kwargs.get("gliner_model_id", None)
        self.enable_onnx = kwargs.get("enable_onnx", False)
        self.dissatisfaction_threshold = kwargs.get("dissatisfaction_threshold", 0.65)
        self.correction_confidence_min = kwargs.get("correction_confidence_min", 0.60)
        self.enable_passive_capture = kwargs.get("enable_passive_capture", True)
        self.passive_timeout_seconds = kwargs.get("passive_timeout_seconds", 180)
        for k, v in kwargs.items():
            setattr(self, k, v)

