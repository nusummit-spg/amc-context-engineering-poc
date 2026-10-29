"""
RecordBuilder  orchestrates the 4-step unified record build.

Execution model (per design Section 3):
    Steps 1 + 2  run concurrently  (ThreadPoolExecutor, max_workers=2)
    Steps 3 + 4  run sequentially  after both 1 and 2 finish
    One single DB write at the end

Returns:
    UnifiedEvaluationRecord    successfully built record
    None                        row was a duplicate; discard silently
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional

import structlog

from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    ClassificationResult,
    EnrichmentResult,
    FeedbackRecord,
    LifecycleStatus,
    UnifiedEvaluationRecord,
    FeedbackSource
)
from feedback_loop.services.adjudication import AdjudicationService
from feedback_loop.services.classification import ClassificationService
from feedback_loop.services.diagnosis import DiagnosisService
from feedback_loop.services.enrichment import EvidenceEnrichmentService
from feedback_loop.services.repair_analyzer import RepairAnalyzerService
from feedback_loop.services.router import AdaptiveRouterService
from feedback_loop.logging import (
    get_feedback_logger,
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

logger = structlog.get_logger(__name__)
step_logger = get_feedback_logger("orchestrator")


class RecordBuilder:
    """
    Wires the four services together and enforces the concurrency model
    defined in the technical design.

    A single RecordBuilder instance is safe to share across threads 
    all mutable state lives in local variables within build().
    """

    def __init__(
        self,
        config: FeedbackLoopConfig,
        db: AbstractDatabaseAdapter,
        evidence_adapter: AbstractEvidenceAdapter,
    ) -> None:
        """Initialize a new instance of RecordBuilder.

        Args:
            config (FeedbackLoopConfig): Configuration dictionary or settings object.
            db (AbstractDatabaseAdapter): Database session instance.
            evidence_adapter (AbstractEvidenceAdapter): The evidence adapter.
        """
        self._config = config
        self._db = db
        self._classification_svc = ClassificationService()
        self._enrichment_svc = EvidenceEnrichmentService(config, evidence_adapter, db)
        self._router_svc = AdaptiveRouterService(config)
        self._adjudication_svc = AdjudicationService()
        self._diagnosis_svc = DiagnosisService()
        self._repair_analyzer_svc = RepairAnalyzerService()

    def build(self, row: FeedbackRecord) -> Optional[UnifiedEvaluationRecord]:
        """Execute the unified record build (Steps 1–7) for one feedback_records row.

        Returns None when the row is a duplicate and should be discarded.
        The caller (IngestService) is responsible for the single DB write
        so that write errors don't get swallowed here.

        Args:
            row (FeedbackRecord): The row.

        Returns:
            Optional[UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        log = logger.bind(
            feedback_id=row.feedback_id,
            response_id=row.response_id,
            source=row.source,
        )
        log_step_info(
            step_logger,
            "BUILD_START",
            "Starting unified record build: feedback_id=%s, response_id=%s, source=%s",
            row.feedback_id,
            row.response_id,
            row.source,
        )

        # ── Guard: skip if a unified record already exists for this response ──
        if self._db.unified_record_exists(row.response_id):
            log_step_info(
                step_logger,
                "DUPLICATE_SKIP",
                "Unified record already exists for response_id=%s, skipping build",
                row.response_id,
            )
            log.info("unified_record_already_exists_skipping")
            return None

        # ── Steps 1 + 2 — concurrent ──────────────────────────────────────────
        classification: Optional[ClassificationResult] = None
        enrichment: Optional[EnrichmentResult] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            # Step 1 is only scheduled when there is text to classify
            step1_future: Optional[concurrent.futures.Future] = None
            if self._classification_svc.should_run(row):
                log_step_info(step_logger, "STEP1_START", "Scheduling Step 1 (Classification) for feedback_id=%s", row.feedback_id)
                step1_future = pool.submit(self._classification_svc.run, row, row.session_id, row.feedback_id)

            # Step 2 always runs
            log_step_info(step_logger, "STEP2_START", "Scheduling Step 2 (Enrichment) for response_id=%s", row.response_id)
            step2_future = pool.submit(self._enrichment_svc.run, row, row.session_id, row.feedback_id)

            # Collect results — step 1 result is optional
            if step1_future is not None:
                try:
                    classification = step1_future.result()
                    log_step_info(
                        step_logger,
                        "STEP1_COMPLETE",
                        "Step 1 (Classification) complete: intent=%s, sentiment=%.4f",
                        classification.intent if classification else "none",
                        classification.sentiment_compound if classification else 0.0,
                    )
                except Exception as exc:
                    # Step 1 failure is non-fatal; log and continue without it
                    log_step_warning(step_logger, "STEP1_ERROR", "Step 1 (Classification) failed (non-fatal): %s", exc)
                    log.warning("step1_classification_failed", error=str(exc))
                    classification = None

            try:
                enrichment = step2_future.result()
                log_step_info(
                    step_logger,
                    "STEP2_COMPLETE",
                    "Step 2 (Enrichment) complete: entry_route=%s, duplicate=%s",
                    enrichment.entry_route,
                    enrichment.is_duplicate,
                )
                log.info("step2_enrichment_complete", snapshot=enrichment.evidence_snapshot)
            except Exception as exc:
                # Step 2 failure is fatal — we cannot build a record without evidence
                log_step_error(step_logger, "STEP2_ERROR", "Step 2 (Enrichment) failed (fatal): %s", exc)
                log.error("step2_enrichment_failed", error=str(exc))
                raise

        # ── Duplicate short-circuit ───────────────────────────────────────────
        if enrichment.is_duplicate:
            log_step_info(
                step_logger,
                "DUPLICATE_SHORT_CIRCUIT",
                "Enrichment detected duplicate cluster_id=%s for feedback_id=%s",
                enrichment.cluster_id,
                row.feedback_id,
            )
            log.info("duplicate_short_circuit", cluster_id=enrichment.cluster_id)
            return None

        # ── Step 3 — Adaptive Router (needs step 2 evidence) ──────────────────
        log_step_info(step_logger, "STEP3_START", "Running Step 3 (Adaptive Router)...")
        router_result = self._router_svc.run(
            row=row,
            snapshot=enrichment.evidence_snapshot,
            session_id=row.session_id,
            feedback_id=row.feedback_id,
        )
        log_step_info(
            step_logger,
            "STEP3_COMPLETE",
            "Step 3 (Adaptive Router) complete: rules_fired=%s, severity=%s",
            [f.rule for f in router_result.rules_fired],
            router_result.severity,
        )

        # ── Step 4 — Adjudication (needs step 3 output) ───────────────────────
        log_step_info(step_logger, "STEP4_START", "Running Step 4 (Adjudication)...")
        adjudication_result = self._adjudication_svc.run(
            row=row,
            snapshot=enrichment.evidence_snapshot,
            router_result=router_result,
            classification=classification,
            session_id=row.session_id,
            feedback_id=row.feedback_id,
        )
        log_step_info(
            step_logger,
            "STEP4_COMPLETE",
            "Step 4 (Adjudication) complete: root_cause=%s",
            adjudication_result.root_cause,
        )

        # ── Step 5 — Diagnosis (needs step 3 + 4 output) ──────────────────────
        log_step_info(step_logger, "STEP5_START", "Running Step 5 (Diagnosis)...")
        diagnosis_result = self._diagnosis_svc.diagnose(
            root_cause=adjudication_result.root_cause,
            router_result=router_result,
            snapshot=enrichment.evidence_snapshot,
        )
        log_step_info(
            step_logger,
            "STEP5_COMPLETE",
            "Step 5 (Diagnosis) complete: stack_layer=%s, confidence=%.2f",
            diagnosis_result.stack_layer,
            diagnosis_result.confidence,
        )

        # ── Step 6 — Repair Analysis (needs step 5 output) ────────────────────
        log_step_info(step_logger, "STEP6_START", "Running Step 6 (Repair Analysis)...")
        repair_analysis = self._repair_analyzer_svc.analyze(
            diagnosis=diagnosis_result,
            severity=router_result.severity,
            root_cause=adjudication_result.root_cause,
            confidence=diagnosis_result.confidence,
        )
        log_step_info(
            step_logger,
            "STEP6_COMPLETE",
            "Step 6 (Repair Analysis) complete: repair=%s, repair_target=%s",
            repair_analysis.repair,
            repair_analysis.repair_target,
        )

        # ── Assemble the unified record ───────────────────────────────────────
        record = UnifiedEvaluationRecord(
            session_id=row.session_id,
            response_id=row.response_id,
            entry_route=enrichment.entry_route,
            feedback_ref=row.feedback_id if enrichment.entry_route == "hitl" else None,
            evidence_snapshot_ref=enrichment.evidence_snapshot_ref,
            root_cause=adjudication_result.root_cause,
            severity=router_result.severity,
            lifecycle_status=LifecycleStatus.OPEN,
            # Auditability: store dissatisfaction evidence when present
            dissatisfaction_evidence=(
                {
                    **(enrichment.dissatisfaction_signal.model_dump() if enrichment.dissatisfaction_signal else {}),
                    "correction_claims": row.corrections if isinstance(row.corrections, list) else ([row.corrections] if row.corrections else []),
                    "feedback_text": row.notes,
                }
                if (enrichment.dissatisfaction_signal or row.corrections or row.notes or row.source in (FeedbackSource.ACTIVE, "active"))
                else None
            ),
            repair=repair_analysis.repair,
            repair_target=repair_analysis.repair_target,
        )

        # ── Step 7 — Tiered Evaluation (optional, runs when repair=True) ───────
        if repair_analysis.repair:
            try:
                log_step_info(step_logger, "STEP7_START", "Running Step 7 (Tiered Evaluation) for response_id=%s", row.response_id)
                from app.evaluation.evaluation_router import EvaluationRouter
                router = EvaluationRouter()

                # Build evidence pack for evaluation
                evidence_pack = {
                    "response_text": enrichment.evidence_snapshot.response_text,
                    "query": enrichment.evidence_snapshot.original_query,
                    "context": " ".join([c.content or c.value or "" for c in enrichment.evidence_snapshot.evidence_selected]),
                    "chunks": [
                        {"text": c.content or c.value, "score": getattr(c, "score", 0)}
                        for c in enrichment.evidence_snapshot.evidence_selected
                    ],
                    "intent": classification.intent if classification else None,
                }

                evaluation_results = router.evaluate(
                    response_id=row.response_id,
                    evidence_pack=evidence_pack,
                )

                log_step_info(
                    step_logger,
                    "STEP7_COMPLETE",
                    "Step 7 (Tiered Evaluation) complete: tier=%s, verdict=%s, confidence=%s",
                    evaluation_results.get("tier"),
                    evaluation_results.get("verdict"),
                    evaluation_results.get("confidence"),
                )

                log.info(
                    "evaluation_complete",
                    feedback_id=row.feedback_id,
                    tier=evaluation_results.get("tier"),
                    verdict=evaluation_results.get("verdict"),
                )

                if evaluation_results:
                    record.deterministic_results = evaluation_results.get("rule_results")
                    record.gnn_plausibility_score = evaluation_results.get("gnn_plausibility_score")
                    record.semantic_results = evaluation_results.get("nli_result")
                    record.llm_evaluation = evaluation_results.get("critic_result")
                    raw_v = evaluation_results.get("verdict")
                    norm_v = None
                    if raw_v:
                        norm = str(raw_v).lower().strip()
                        if norm in ("valid", "partially_valid", "invalid", "subjective", "insufficient_evidence"):
                            norm_v = norm
                        elif norm in ("pass",):
                            norm_v = "valid"
                        elif norm in ("fail",):
                            norm_v = "invalid"
                        elif norm in ("warn", "revise", "partial"):
                            norm_v = "partially_valid"
                        elif "inconclusive" in norm or "insufficient" in norm:
                            norm_v = "insufficient_evidence"
                        else:
                            norm_v = "valid"
                    record.adjudication_verdict = norm_v
                    record.adjudication_confidence = evaluation_results.get("confidence")
            except Exception as exc:
                log_step_warning(step_logger, "STEP7_SKIPPED", "Tiered evaluation skipped or failed: %s", exc)
                log.warning("evaluation_failed_or_skipped", error=str(exc))

        log_step_info(
            step_logger,
            "BUILD_COMPLETE",
            "UnifiedEvaluationRecord built: entry_route=%s, root_cause=%s, severity=%s, repair=%s, repair_target=%s",
            record.entry_route,
            record.root_cause,
            record.severity,
            record.repair,
            record.repair_target,
        )

        log.info(
            "record_built",
            entry_route=record.entry_route,
            root_cause=record.root_cause,
            severity=record.severity,
            repair=record.repair,
            repair_target=record.repair_target,
        )
        return record

