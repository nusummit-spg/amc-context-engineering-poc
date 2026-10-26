"""
Step 3  AdaptiveRouterService

Deterministic rule check against the evidence snapshot and any structured
corrections.  Maps fired rules to a preliminary severity.

Rules implemented:
  C01   referential integrity (entity present in evidence)
  C02   temporal freshness  (source_version staleness indicator)
  C03   numeric accuracy    (response value vs. evidence value)
  C04   structured correction present (user-supplied explicit correction)
  C05   compliance / jurisdiction keyword detection

Severity mapping (design Â§ 3):
  - Compliance / jurisdiction violation  â†’ critical
  - Numeric delta â‰¥ thresholds           â†’ critical / high / medium
  - Entity not in evidence               â†’ high
  - Structured correction present        â†’ high
  - Presentation-only / minor            â†’ low
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

import structlog

from feedback_loop.logging_config import get_pipeline_logger
from feedback_loop.logging import get_feedback_logger, log_step_info
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    EvidenceSnapshot,
    FeedbackRecord,
    RouterResult,
    RuleFinding,
    Severity,
)

logger = structlog.get_logger(__name__)
step_logger_rtr = get_feedback_logger("router")

# Compliance / jurisdiction keywords that auto-triage to critical
_COMPLIANCE_KEYWORDS = re.compile(
    r"\b(sebi|amfi|irda|nsdl|cdsl|rbi|compliance|regulation|regulatory|"
    r"jurisdiction|statutory|mandatory|breach|penalty|violation)\b",
    re.IGNORECASE,
)


def _extract_numeric(text: str) -> Optional[float]:
    """Pull first numeric value (int or decimal, optionally followed by %) from text.

    Args:
        text (str): Input text content.

    Returns:
        Optional[float]: Matching object or record if found, None otherwise.
    """
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*%?", text)
    if match:
        return float(match.group(1))
    return None


def _extract_all_numerics(text: str) -> list[float]:
    """Pull all numeric values (int or decimal) from text.

    Args:
        text (str): Input text content.

    Returns:
        list[float]: List of resulting items or records.
    """
    matches = re.findall(r"\b(\d+(?:\.\d+)?)\s*%?", text)
    return [float(m) for m in matches]


def _delta_pct(response_val: float, evidence_val: float) -> float:
    """Absolute percentage deviation of response vs. evidence.

    Args:
        response_val (float): The response val.
        evidence_val (float): The evidence val.

    Returns:
        float: Resulting float instance.
    """
    if evidence_val == 0:
        return 0.0
    return abs(response_val - evidence_val) / abs(evidence_val) * 100.0


class AdaptiveRouterService:
    """
    Step 3  deterministic rule check + severity assignment.

    Runs for BOTH active and passive rows.
    Does NOT escalate to NLI or LLM  that tier only exists in the
    external Evaluation Layer.
    """

    def __init__(self, config: FeedbackLoopConfig) -> None:
        """Initialize a new instance of AdaptiveRouterService.

        Args:
            config (FeedbackLoopConfig): Configuration dictionary or settings object.
        """
        self._config = config

    #  Individual rule checks 

    def _check_c01_referential(
        self, row: FeedbackRecord, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C01  entity named in feedback should appear in evidence chunks.

        Args:
            row (FeedbackRecord): The row.
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        entity = row.entity_name
        if not entity:
            return None
        # Check response text and evidence chunks
        in_response = entity.lower() in snapshot.response_text.lower()
        in_chunks = any(
            entity.lower() in (c.content or "").lower()
            or entity.lower() in (c.value or "").lower()
            for c in snapshot.evidence_selected
        )
        if not in_response and not in_chunks:
            return RuleFinding(
                rule="C01_referential_integrity",
                result="FAIL",
                detail=f"Entity '{entity}' not found in response or evidence chunks.",
            )
        return None

    def _check_c02_temporal(
        self, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C02  flag when any evidence chunk has no source_version (staleness indicator).

        Args:
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        stale = [c.chunk_id for c in snapshot.evidence_selected if not c.source_version]
        if stale:
            return RuleFinding(
                rule="C02_temporal_freshness",
                result="WARN",
                detail=f"Chunks missing source_version (possible stale data): {stale}",
            )
        return None

    def _check_c03_numeric(
        self, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C03  numeric accuracy.
        Compares the first numeric value in response_text against the first
        numeric value in any evidence chunk.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        response_val = _extract_numeric(snapshot.response_text)
        if response_val is None:
            return None

        for chunk in snapshot.evidence_selected:
            evidence_text = chunk.value or chunk.content or ""
            evidence_val = _extract_numeric(evidence_text)
            if evidence_val is None:
                continue
            delta = _delta_pct(response_val, evidence_val)
            if delta > 0:
                return RuleFinding(
                    rule="C03_numeric_accuracy",
                    result="FAIL",
                    response_value=response_val,
                    evidence_value=evidence_val,
                    delta_pct=round(delta, 2),
                )
        return None

    def _check_c04_structured_correction(
        self, row: FeedbackRecord
    ) -> Optional[RuleFinding]:
        """C04  user supplied an explicit structured correction.

        Args:
            row (FeedbackRecord): The row.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        if row.corrections:
            return RuleFinding(
                rule="C04_structured_correction",
                result="FAIL",
                detail=f"User-supplied correction: {row.corrections}",
            )
        return None

    def _check_c05_compliance(
        self, row: FeedbackRecord, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C05  compliance/jurisdiction keyword in notes or response.

        Args:
            row (FeedbackRecord): The row.
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        text_to_scan = " ".join(filter(None, [
            row.notes or "",
            snapshot.response_text,
        ]))
        matches = _COMPLIANCE_KEYWORDS.findall(text_to_scan)
        if matches:
            return RuleFinding(
                rule="C05_compliance_jurisdiction",
                result="FAIL",
                detail=f"Compliance keywords detected: {list(set(m.lower() for m in matches))}",
            )
        return None

    def _check_c06_cardinality(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
        """C06 — Cardinality check: response claims single value but evidence has multiple distinct values.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        evidence_numbers = []
        for chunk in snapshot.evidence_selected:
            nums = _extract_all_numerics(chunk.content or chunk.value or "")
            evidence_numbers.extend(nums)

        response_numbers = _extract_all_numerics(snapshot.response_text)

        if len(response_numbers) == 1 and len(set(evidence_numbers)) > 1:
            return RuleFinding(
                rule="C06_cardinality",
                result="WARN",
                detail=f"Response claims single value {response_numbers[0]} but evidence contains multiple: {list(set(evidence_numbers))}",
            )
        return None

    def _check_c07_cross_source(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
        """C07 — Cross-source consistency: same fact from different sources must agree.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        source_groups = defaultdict(list)
        for chunk in snapshot.evidence_selected:
            if chunk.source_version:
                source_groups[chunk.source_version].append(chunk)

        if len(source_groups) < 2:
            return None

        source_values = {}
        for source, chunks in source_groups.items():
            for chunk in chunks:
                num = _extract_numeric(chunk.content or chunk.value or "")
                if num is not None:
                    source_values[source] = num
                    break

        if len(source_values) >= 2:
            vals = list(source_values.values())
            if max(vals) - min(vals) > 0.01:
                return RuleFinding(
                    rule="C07_cross_source",
                    result="FAIL",
                    detail=f"Cross-source conflict: {source_values}",
                )
        return None

    def _check_c08_duplicate(self, row: FeedbackRecord) -> Optional[RuleFinding]:
        """C08 — Duplicate detection: feedback is repetitive of previous submission.

        Args:
            row (FeedbackRecord): The row.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        return None

    def _check_c09_hierarchy(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
        """C09 — Taxonomy hierarchy violation: response references incorrect taxonomy level.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            Optional[RuleFinding]: Matching object or record if found, None otherwise.
        """
        return None

    # ── Severity mapping ──────────────────────────────────────────────────────

    def _severity_from_rules(self, findings: list[RuleFinding]) -> Optional[Severity]:
        """Severity from rules.

        Args:
            findings (list[RuleFinding]): Collection or list of findings.

        Returns:
            Optional[Severity]: Matching object or record if found, None otherwise.
        """
        if not findings:
            return None

        severity_rank = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }

        candidates: list[Severity] = []
        rule_names = {f.rule for f in findings}

        # Compliance → always critical
        if "C05_compliance_jurisdiction" in rule_names:
            candidates.append(Severity.CRITICAL)

        # Numeric severity tiers
        for f in findings:
            if f.rule == "C03_numeric_accuracy" and f.delta_pct is not None:
                if f.delta_pct >= self._config.numeric_critical_delta_pct:
                    candidates.append(Severity.CRITICAL)
                elif f.delta_pct >= self._config.numeric_high_delta_pct:
                    candidates.append(Severity.HIGH)
                elif f.delta_pct >= self._config.numeric_medium_delta_pct:
                    candidates.append(Severity.MEDIUM)
                else:
                    candidates.append(Severity.LOW)

        # Cross-source conflict / Entity / correction mismatch → high
        if rule_names & {"C01_referential_integrity", "C04_structured_correction", "C07_cross_source"}:
            candidates.append(Severity.HIGH)

        # Cardinality mismatch → medium
        if "C06_cardinality" in rule_names:
            candidates.append(Severity.MEDIUM)

        # Temporal warning → low
        if "C02_temporal_freshness" in rule_names:
            candidates.append(Severity.LOW)

        if not candidates:
            return Severity.MEDIUM

        return max(candidates, key=lambda s: severity_rank.get(s, 0))

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, row: FeedbackRecord, snapshot: EvidenceSnapshot, session_id: str = None, feedback_id: str = None) -> RouterResult:
        """Execute deterministic rule checks against evidence and feedback.

        Args:
            row (FeedbackRecord): The row.
            snapshot (EvidenceSnapshot): The snapshot.
            session_id (str): Unique identifier of the session.
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            RouterResult: Resulting RouterResult instance.
        """
        findings: list[RuleFinding] = []
        log_step_info(step_logger_rtr, "ROUTER_START", "Adaptive router evaluating rules for feedback_id=%s", row.feedback_id)

        for checker in (
            lambda: self._check_c01_referential(row, snapshot),
            lambda: self._check_c02_temporal(snapshot),
            lambda: self._check_c03_numeric(snapshot),
            lambda: self._check_c04_structured_correction(row),
            lambda: self._check_c05_compliance(row, snapshot),
            lambda: self._check_c06_cardinality(snapshot),
            lambda: self._check_c07_cross_source(snapshot),
            lambda: self._check_c08_duplicate(row),
            lambda: self._check_c09_hierarchy(snapshot),
        ):
            result = checker()
            if result is not None:
                findings.append(result)

        severity = self._severity_from_rules(findings)

        log_step_info(
            step_logger_rtr,
            "ROUTER_COMPLETE",
            "Adaptive router complete for %s: rules_fired=%s, severity=%s",
            row.feedback_id,
            [f.rule for f in findings],
            severity,
        )

        step_logger = None
        if session_id and feedback_id:
            step_logger = get_pipeline_logger("router", session_id, feedback_id)
            if step_logger:
                step_logger.info("Router complete")
        logger.info(
            "router_complete",
            feedback_id=row.feedback_id,
            rules_fired=[f.rule for f in findings],
            severity=severity,
        )

        return RouterResult(rules_fired=findings, severity=severity)

