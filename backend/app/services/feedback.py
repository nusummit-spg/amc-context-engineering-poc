# from sqlalchemy.orm import Session

# from app.core.models import (
#     FeedbackRecord,
#     UnifiedEvaluationRecord,
#     EntryRoute,
#     AdjudicationVerdict,
#     RootCause,
#     Severity,
#     LifecycleStatus,
#     RepairTarget,
# )


# def trigger_feedback_loop(
#     db: Session,
#     feedback: FeedbackRecord,
# ) -> UnifiedEvaluationRecord:
#     """
#     Process a FeedbackRecord through the feedback evaluation pipeline.

#     Phase 1:
#     - Create deterministic evaluation results
#     - Create a stub GNN score
#     - Create stub semantic results
#     - Perform basic adjudication
#     - Determine root cause / severity
#     - Step 6: determine repair routing
#     - Store the result in UnifiedEvaluationRecord
#     """

#     deterministic_results = evaluate_deterministic_rules(feedback)
#     gnn_score = evaluate_gnn(feedback)
#     semantic_results = evaluate_semantic(feedback)

#     verdict, confidence = adjudicate(
#         feedback=feedback,
#         deterministic_results=deterministic_results,
#         gnn_score=gnn_score,
#         semantic_results=semantic_results,
#     )

#     root_cause = determine_root_cause(feedback, verdict)
#     severity = determine_severity(feedback)

#     # ---------------------------------------------------------
#     # Step 6: Repair analysis (REVISED_SUMMARY.md Gap 1)
#     # ---------------------------------------------------------
#     repair, repair_target = determine_repair_routing(root_cause)

#     evaluation = UnifiedEvaluationRecord(
#         session_id=feedback.session_id,
#         response_id=feedback.response_id,
#         entry_route=EntryRoute.HITL.value,
#         feedback_ref=feedback.feedback_id,
#         evidence_snapshot_ref=None,
#         deterministic_results=deterministic_results,
#         gnn_plausibility_score=gnn_score,
#         semantic_results=semantic_results,
#         llm_evaluation=None,
#         adjudication_verdict=verdict,
#         adjudication_confidence=confidence,
#         root_cause=root_cause,
#         severity=severity,
#         lifecycle_status=LifecycleStatus.OPEN.value,
#         repair=repair,
#         repair_target=repair_target,
#     )

#     db.add(evaluation)
#     db.commit()
#     db.refresh(evaluation)

#     return evaluation


# # ============================================================
# # Evaluation functions
# # ============================================================

# def evaluate_deterministic_rules(feedback: FeedbackRecord) -> dict:
#     return {
#         "feedback_present": feedback.notes is not None,
#         "correction_present": feedback.corrections is not None,
#         "entity_present": feedback.entity_name is not None,
#         "negative_rating": feedback.rating == "negative",
#         "feedback_type": feedback.feedback_type,
#     }


# def evaluate_gnn(feedback: FeedbackRecord) -> float:
#     """Phase 2 frozen GNN model stub."""
#     return 0.5


# def evaluate_semantic(feedback: FeedbackRecord) -> dict:
#     if feedback.corrections:
#         return {"entailment": 0.0, "contradiction": 1.0, "neutral": 0.0}
#     return {"entailment": 0.0, "contradiction": 0.0, "neutral": 1.0}


# def adjudicate(
#     feedback: FeedbackRecord,
#     deterministic_results: dict,
#     gnn_score: float,
#     semantic_results: dict,
# ) -> tuple[str, float]:
#     if feedback.feedback_type == "correction":
#         return AdjudicationVerdict.PARTIALLY_VALID.value, 0.75
#     if feedback.rating == "negative":
#         return AdjudicationVerdict.SUBJECTIVE.value, 0.60
#     return AdjudicationVerdict.INSUFFICIENT_EVIDENCE.value, 0.40


# def determine_root_cause(feedback: FeedbackRecord, verdict: str) -> str:
#     if feedback.feedback_type == "correction":
#         return RootCause.KNOWLEDGE.value
#     return RootCause.FEEDBACK_INVALID.value


# def determine_severity(feedback: FeedbackRecord) -> str:
#     if feedback.rating == "negative":
#         return Severity.MEDIUM.value
#     return Severity.LOW.value


# def determine_repair_routing(root_cause: str) -> tuple[bool, str | None]:
#     """
#     Step 6 — RepairAnalysisService, per REVISED_SUMMARY.md:
#       KNOWLEDGE / RETRIEVAL / GRAPH -> repair=True,  target="graph"
#       MODEL                        -> repair=True,  target="vector"
#       everything else               -> repair=False, target=None
#     """
#     if root_cause in {RootCause.KNOWLEDGE.value, RootCause.RETRIEVAL.value, RootCause.GRAPH.value}:
#         return True, RepairTarget.GRAPH.value
#     if root_cause == RootCause.MODEL.value:
#         return True, RepairTarget.VECTOR.value
#     return False, None

# from sqlalchemy.orm import Session

# from app.core.models import (
#     UnifiedEvaluationRecord,
#     QueryEvidence,
#     EntryRoute,
#     AdjudicationVerdict,
#     RootCause,
#     Severity,
#     LifecycleStatus,
#     RepairTarget,
# )


# class MissingQueryEvidenceError(Exception):
#     """Raised when no QueryEvidence row exists for a feedback's response_id.

#     unified_evaluation_records.evidence_snapshot_ref is NOT NULL and FKs to
#     query_evidence.response_id, so a QueryEvidence row must exist before
#     the feedback loop can run for that response.
#     """


# def trigger_feedback_loop(
#     db: Session,
#     feedback: FeedbackRecor,
# ) -> UnifiedEvaluationRecord:
#     """
#     Process a FeedbackRecord through the feedback evaluation pipeline.
#     """

#     # ---------------------------------------------------------
#     # 0. Resolve required evidence_snapshot_ref
#     # ---------------------------------------------------------
#     query_evidence = (
#         db.query(QueryEvidence)
#         .filter(QueryEvidence.response_id == feedback.response_id)
#         .first()
#     )
#     if query_evidence is None:
#         raise MissingQueryEvidenceError(
#             f"No query_evidence row found for response_id={feedback.response_id}. "
#             "Create the QueryEvidence record before running the feedback loop."
#         )

#     deterministic_results = evaluate_deterministic_rules(feedback)
#     gnn_score = evaluate_gnn(feedback)
#     semantic_results = evaluate_semantic(feedback)

#     verdict, confidence = adjudicate(
#         feedback=feedback,
#         deterministic_results=deterministic_results,
#         gnn_score=gnn_score,
#         semantic_results=semantic_results,
#     )

#     root_cause = determine_root_cause(feedback, verdict)
#     severity = determine_severity(feedback)
#     repair, repair_target = determine_repair_routing(root_cause)

#     evaluation = UnifiedEvaluationRecord(
#         session_id=feedback.session_id,
#         response_id=feedback.response_id,
#         entry_route=EntryRoute.HITL.value,
#         feedback_ref=None,  # feedback_ref points at response_feedback.feedback_id, not
#                              # feedback_records.feedback_id — this FeedbackRecord alone
#                              # can't populate it; wire it up once a ResponseFeedback row
#                              # exists for this response (see feedback_evaluation router).
#         evidence_snapshot_ref=query_evidence.response_id,
#         deterministic_results=deterministic_results,
#         gnn_plausibility_score=gnn_score,
#         semantic_results=semantic_results,
#         llm_evaluation=None,
#         adjudication_verdict=verdict,
#         adjudication_confidence=confidence,
#         root_cause=root_cause,
#         severity=severity,
#         lifecycle_status=LifecycleStatus.OPEN.value,
#         repair=repair,
#         repair_target=repair_target,
#     )

#     db.add(evaluation)
#     db.commit()
#     db.refresh(evaluation)

#     # Back-fill the reverse link now that the row exists (avoids the
#     # circular-FK chicken-and-egg problem — see chat note).
#     query_evidence.unified_record_ref = evaluation.response_id
#     db.commit()

#     return evaluation


# # ============================================================
# # Evaluation functions (unchanged)
# # ============================================================

# def evaluate_deterministic_rules(feedback: FeedbackRecord) -> dict:
#     return {
#         "feedback_present": feedback.notes is not None,
#         "correction_present": feedback.corrections is not None,
#         "entity_present": feedback.entity_name is not None,
#         "negative_rating": feedback.rating == "negative",
#         "feedback_type": feedback.feedback_type,
#     }


# def evaluate_gnn(feedback: FeedbackRecord) -> float:
#     return 0.5


# def evaluate_semantic(feedback: FeedbackRecord) -> dict:
#     if feedback.corrections:
#         return {"entailment": 0.0, "contradiction": 1.0, "neutral": 0.0}
#     return {"entailment": 0.0, "contradiction": 0.0, "neutral": 1.0}


# def adjudicate(
#     feedback: FeedbackRecord,
#     deterministic_results: dict,
#     gnn_score: float,
#     semantic_results: dict,
# ) -> tuple[str, float]:
#     if feedback.feedback_type == "correction":
#         return AdjudicationVerdict.PARTIALLY_VALID.value, 0.75
#     if feedback.rating == "negative":
#         return AdjudicationVerdict.SUBJECTIVE.value, 0.60
#     return AdjudicationVerdict.INSUFFICIENT_EVIDENCE.value, 0.40


# def determine_root_cause(feedback: FeedbackRecord, verdict: str) -> str:
#     if feedback.feedback_type == "correction":
#         return RootCause.KNOWLEDGE.value
#     return RootCause.FEEDBACK_INVALID.value


# def determine_severity(feedback: FeedbackRecord) -> str:
#     if feedback.rating == "negative":
#         return Severity.MEDIUM.value
#     return Severity.LOW.value


# def determine_repair_routing(root_cause: str) -> tuple[bool, str | None]:
#     if root_cause in {RootCause.KNOWLEDGE.value, RootCause.RETRIEVAL.value, RootCause.GRAPH.value}:
#         return True, RepairTarget.GRAPH.value
#     if root_cause == RootCause.MODEL.value:
#         return True, RepairTarget.VECTOR.value
#     return False, None