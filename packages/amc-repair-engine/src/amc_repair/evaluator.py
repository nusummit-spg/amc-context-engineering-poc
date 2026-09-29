"""
Tiered evaluation routing engine.
"""
from typing import Any, Dict
from .config import RepairConfig
from .schemas import EvaluationResult

class TieredEvaluator:
    def __init__(self, config: RepairConfig):
        self.config = config

    def evaluate(self, response_id: str, evidence_pack: Dict[str, Any]) -> EvaluationResult:
        query = evidence_pack.get("query", "").lower()
        response = evidence_pack.get("response_text", "").lower()
        claimed = evidence_pack.get("claimed_value")

        # Tier 1A: Deterministic verification
        if claimed and str(claimed).lower() not in response:
            return EvaluationResult(
                response_id=response_id,
                verdict="REVISE",
                tier="TIER_1A",
                confidence=0.95,
                details={"reason": "Claimed value contradicts synthesis text"}
            )

        return EvaluationResult(
            response_id=response_id,
            verdict="PASS",
            tier="TIER_1A",
            confidence=0.90,
            details={"reason": "Synthesis conforms to factual constraints"}
        )
