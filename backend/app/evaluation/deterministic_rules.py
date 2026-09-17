# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
deterministic_rules.py
======================
Tier 1A deterministic evaluation rules and STOP-1 gating.
Executes non-LLM, rule-based verification:
  - C02: Source Currency (freshness of data)
  - C03: Numeric Accuracy (extracts numbers, checks deviation against retrieved chunks)
  - F06: Citation Integrity (verifies cited chunk identifiers exist in retrieved evidence)
"""

from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.evaluation.deterministic_rules")


class RuleVerdict(str, Enum):
    """Evaluation verdict for a rule."""
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class RuleResult:
    """Result of a single deterministic rule evaluation."""
    rule_id: str
    rule_name: str
    verdict: RuleVerdict
    confidence: float
    evidence: Dict[str, Any]
    explanation: str


class DeterministicRuleEngine:
    """
    Tier 1A deterministic evaluation rules.
    Catches common failures with 0 LLM tokens.
    """

    DEFAULT_SOURCE_MAX_AGE_DAYS = 7
    DEFAULT_NUMERIC_DEVIATION_PCT = 0.05  # 5%

    def __init__(
        self,
        source_max_age_days: int = DEFAULT_SOURCE_MAX_AGE_DAYS,
        numeric_deviation_threshold: float = DEFAULT_NUMERIC_DEVIATION_PCT
    ):
        self.source_max_age_days = source_max_age_days
        self.numeric_deviation_threshold = numeric_deviation_threshold

    def evaluate_source_currency(self, evidence_pack: Dict[str, Any]) -> RuleResult:
        """
        Rule C02: Source Currency
        Checks if source age in days exceeds threshold.
        """
        source_age_days = evidence_pack.get("source_age_days")
        if source_age_days is None:
            # Check metadata or D2 source versions
            source_versions = evidence_pack.get("source_versions", {})
            if isinstance(source_versions, dict) and "age_days" in source_versions:
                source_age_days = source_versions["age_days"]

        if source_age_days is None:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="source_age_days not provided in evidence pack"
            )

        if source_age_days <= self.source_max_age_days:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={
                    "source_age_days": source_age_days,
                    "threshold_days": self.source_max_age_days
                },
                explanation=f"Source is {source_age_days} days old (within {self.source_max_age_days} day limit)"
            )
        else:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "source_age_days": source_age_days,
                    "threshold_days": self.source_max_age_days
                },
                explanation=f"Source is {source_age_days} days old (exceeds {self.source_max_age_days} day threshold)"
            )

    def evaluate_numeric_accuracy(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any],
        chunk_store: Any = None
    ) -> RuleResult:
        """
        Rule C03: Numeric Accuracy
        Extracts numbers from response and verifies against numbers present in retrieved chunks.
        """
        response_numbers = self._extract_numbers(response_text)
        if not response_numbers:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="No numerical values found in response text"
            )

        # Gather source numbers from evidence_pack
        source_numbers: List[float] = []
        if "source_numbers" in evidence_pack:
            source_numbers = [float(n) for n in evidence_pack["source_numbers"]]
        elif "chunks" in evidence_pack:
            for ch in evidence_pack["chunks"]:
                text_content = ch.get("text", "") if isinstance(ch, dict) else str(ch)
                source_numbers.extend(self._extract_numbers(text_content))
        elif "context" in evidence_pack:
            source_numbers.extend(self._extract_numbers(str(evidence_pack["context"])))

        if not source_numbers:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={"response_numbers": response_numbers},
                explanation="No reference numbers found in source context to verify against"
            )

        mismatches = []
        for resp_num in response_numbers:
            closest_source = self._find_closest_number(resp_num, source_numbers)
            if closest_source is not None:
                if closest_source == 0.0:
                    deviation_pct = abs(resp_num)
                else:
                    deviation_pct = abs(resp_num - closest_source) / abs(closest_source)

                if deviation_pct > self.numeric_deviation_threshold:
                    mismatches.append({
                        "response_value": resp_num,
                        "source_value": closest_source,
                        "deviation_pct": round(deviation_pct, 4)
                    })

        if mismatches:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "mismatches": mismatches,
                    "threshold_pct": self.numeric_deviation_threshold
                },
                explanation=f"Numeric mismatch detected: {len(mismatches)} values deviate from source"
            )
        else:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={"verified_numbers": len(response_numbers)},
                explanation=f"All {len(response_numbers)} numeric values match retrieved sources"
            )

    def evaluate_citation_integrity(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any]
    ) -> RuleResult:
        """
        Rule F06: Citation Integrity
        Verifies that citation identifiers in the response resolve to retrieved chunks.
        """
        citation_ids = self._extract_citation_ids(response_text)
        if not citation_ids:
            return RuleResult(
                rule_id="F06_CITATION_INTEGRITY",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="No citations found in response text"
            )

        chunk_ids = set(evidence_pack.get("chunk_ids", []))
        broken_citations = [cid for cid in citation_ids if cid not in chunk_ids]

        if broken_citations:
            return RuleResult(
                rule_id="F06_CITATION_INTEGRITY",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "broken_citations": broken_citations,
                    "total_citations": len(citation_ids),
                    "retrieved_chunk_ids": list(chunk_ids)
                },
                explanation=f"{len(broken_citations)} citation(s) do not resolve to retrieved chunks"
            )
        else:
            return RuleResult(
                rule_id="F06_CITATION_INTEGRITY",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={"verified_citations": len(citation_ids)},
                explanation=f"All {len(citation_ids)} citations successfully verified"
            )

    def evaluate_all(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any],
        chunk_store: Any = None
    ) -> List[RuleResult]:
        """Run all Tier 1A deterministic rules."""
        return [
            self.evaluate_source_currency(evidence_pack),
            self.evaluate_numeric_accuracy(response_text, evidence_pack, chunk_store),
            self.evaluate_citation_integrity(response_text, evidence_pack)
        ]

    def should_stop(self, results: List[RuleResult]) -> bool:
        """
        STOP-1 gate decision.
        If ANY rule returns FAIL with confidence >= 0.9, stop immediately (0 LLM tokens).
        """
        critical_failures = [
            r for r in results
            if r.verdict == RuleVerdict.FAIL and r.confidence >= 0.9
        ]
        return len(critical_failures) > 0

    # Helpers
    def _extract_numbers(self, text: str) -> List[float]:
        if not text:
            return []
        # Strip citation tags so citation IDs (e.g., [source: C_101], C_1234) are not extracted as numerical financial values
        cleaned = re.sub(r'\[(?:source|chunk_id|chunk)?:?\s*[A-Za-z0-9_\-]+\]', '', text)
        cleaned = re.sub(r'\bC_\d+\b', '', cleaned)
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        matches = re.findall(pattern, cleaned)
        return [float(m) for m in matches if m]

    def _find_closest_number(self, target: float, numbers: List[float]) -> Optional[float]:
        if not numbers:
            return None
        return min(numbers, key=lambda x: abs(x - target))

    def _extract_citation_ids(self, text: str) -> List[str]:
        # [source: C_1234], [chunk_id: C_1234], [C_1234], or C_1234 citation tags
        pattern = r'\[(?:source|chunk_id|chunk):\s*([A-Za-z0-9_\-]+)\]|\[([A-Za-z0-9_\-]+)\]'
        matches = re.findall(pattern, text or "")
        citations = []
        for m1, m2 in matches:
            cid = m1 or m2
            if cid and (cid.startswith("C_") or cid.startswith("chunk_")):
                citations.append(cid)
        return citations
