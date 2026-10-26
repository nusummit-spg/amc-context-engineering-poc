"""

Step 4  AdjudicationService



Multi-dimension root_cause classification.



This step does NOT decide how to fix anything or run any evaluation tier 

it only produces a preliminary root_cause for the Evaluation Layer to pick up.



root_cause taxonomy (from the design):

  knowledge            information gap in the knowledge base

  compliance           compliance / jurisdiction rule violated

  graph                incorrect graph relationship used

  context_engineering  prompt construction / context window issue

  retrieval            retriever pulled wrong / stale chunks

  model                generation-layer synthesis error (hallucination)

  guardrail            blocked or clipped by a safety filter

  presentation         formatting / display issue, correct underlying data

  feedback_invalid     feedback itself is inconsistent or lacks evidence



Decision logic (deterministic priority order):

  1. Compliance rule fired            â†’ compliance

  2. Numeric mismatch AND evidence had correct value (hallucination pattern)

                                      â†’ model

  3. Entity not in evidence           â†’ retrieval

  4. Structured correction present    â†’ knowledge (user knows better)

  5. Temporal staleness warning       â†’ retrieval

  6. Classification says 'correction' but no rule fired

                                      â†’ knowledge (soft signal)

  7. Negative sentiment only, no rule â†’ presentation (minor issue)

  8. No signal at all                 â†’ feedback_invalid

"""



from __future__ import annotations



from typing import Optional



import structlog



from feedback_loop.logging_config import get_pipeline_logger

from feedback_loop.logging import get_feedback_logger, log_step_info

from feedback_loop.domain_models import (

    AdjudicationResult,

    ClassificationResult,

    EvidenceSnapshot,

    FeedbackRecord,

    RouterResult,

    RootCause,

    RuleFinding,

)



logger = structlog.get_logger(__name__)

step_logger_adj = get_feedback_logger("adjudication")





def _rule_fired(findings: list[RuleFinding], rule_prefix: str) -> bool:

    """Rule fired.

    Args:
        findings (list[RuleFinding]): Collection or list of findings.
        rule_prefix (str): The rule prefix.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    return any(f.rule.startswith(rule_prefix) for f in findings)





def _numeric_finding(findings: list[RuleFinding]) -> Optional[RuleFinding]:

    """Numeric finding.

    Args:
        findings (list[RuleFinding]): Collection or list of findings.

    Returns:
        Optional[RuleFinding]: Matching object or record if found, None otherwise.
    """
    for f in findings:

        if f.rule == "C03_numeric_accuracy":

            return f

    return None





class AdjudicationService:

    """

    Step 4  preliminary root_cause classification.



    Takes the router result (rules fired), the optional classification

    result from Step 1, and the evidence snapshot to reason across

    multiple dimensions.

    """



    def run(

        self,

        row: FeedbackRecord,

        snapshot: EvidenceSnapshot,

        router_result: RouterResult,

        classification: Optional[ClassificationResult] = None,

        session_id: Optional[str] = None,

        feedback_id: Optional[str] = None,

    ) -> AdjudicationResult:

        """Classify root_cause using deterministic priority rules.
        Returns AdjudicationResult  sets lifecycle_status='open' externally
        by the RecordBuilder after this call.

        Args:
            row (FeedbackRecord): The row.
            snapshot (EvidenceSnapshot): The snapshot.
            router_result (RouterResult): The router result.
            classification (Optional[ClassificationResult]): The classification.
            session_id (Optional[str]): Unique identifier of the session.
            feedback_id (Optional[str]): Unique identifier of the feedback.

        Returns:
            AdjudicationResult: Resulting AdjudicationResult instance.
        """
        findings = router_result.rules_fired

        log_step_info(

            step_logger_adj,

            "ADJUDICATION_START",

            "Adjudication starting for %s (findings_count=%d)",

            row.feedback_id,

            len(findings),

        )



        # Priority 1  compliance / jurisdiction violation

        if _rule_fired(findings, "C05_compliance"):

            root_cause = RootCause.COMPLIANCE



        # Priority 2  numeric mismatch where evidence had correct value

        # (hallucination: model generated a number not present in retrieved chunks)

        elif (numeric := _numeric_finding(findings)) and snapshot.evidence_selected:

            # Evidence chunks contained a numeric value  model deviated from it

            root_cause = RootCause.MODEL



        # Priority 3  entity not in evidence â†’ retriever missed it

        elif _rule_fired(findings, "C01_referential"):

            root_cause = RootCause.RETRIEVAL



        # Priority 4  user supplied explicit structured correction

        elif _rule_fired(findings, "C04_structured_correction"):

            root_cause = RootCause.KNOWLEDGE



        # Priority 5  temporal staleness

        elif _rule_fired(findings, "C02_temporal"):

            root_cause = RootCause.RETRIEVAL



        # Priority 6  NLP signal: correction intent but no hard rule fired

        elif classification and classification.intent == "correction":

            root_cause = RootCause.KNOWLEDGE



        # Priority 7  negative sentiment only, no rule fired (may be style)

        elif classification and classification.sentiment_compound < -0.3:

            root_cause = RootCause.PRESENTATION



        # Priority 8  no signal of any kind

        else:

            root_cause = RootCause.FEEDBACK_INVALID



        log_step_info(

            step_logger_adj,

            "ADJUDICATION_COMPLETE",

            "Adjudication complete for %s: root_cause=%s",

            row.feedback_id,

            root_cause,

        )



        step_logger = None

        if session_id and feedback_id:

            step_logger = get_pipeline_logger("adjudication", session_id, feedback_id)

        if step_logger:

            step_logger.info(f"Adjudication complete. Root cause {str(root_cause)}")

        logger.info(

            "adjudication_complete",

            feedback_id=row.feedback_id,

            root_cause=root_cause,

            rules_fired=[f.rule for f in findings],

        )



        return AdjudicationResult(root_cause=root_cause)



