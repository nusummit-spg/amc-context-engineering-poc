#app/scripts/seed_audit_schema.py
import uuid
from datetime import datetime, timezone

from app.core.database import SessionLocal, init_db
from app.core.models import (
    AuditMetadata,
    Violation,
    ResponseFeedback,
    QueryEvidence,
    ComplianceRule,
    FundScheme,
    ChatSession,
    Region,
    AuditType,
    AuditStatus,
    ViolationCategory,
    ViolationStatus,
    Severity,
    ConfidenceLevel,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_audit_schema():
    """
    Create one linked chain of dummy data across all 7 AMC audit tables,
    in FK dependency order, to confirm the schema is wired correctly.

    Order: fund_schemes -> compliance_rules -> audit_metadata -> violations
           -> response_feedback / query_evidence / sessions
    """
    db = SessionLocal()

    try:
        # -----------------------------------------------------
        # 1. fund_schemes (no dependencies)
        # -----------------------------------------------------
        fund = FundScheme(
            fund_id="AXIS_BLUECHIP",
            isin="INF846K01337",
            name="Axis Bluechip Fund",
            fund_house="Axis Mutual Fund",
            category="large_cap",
            mandate="Large-cap equity growth",
            risk_profile="high",
            aum_crores=8500.50,
            nav_per_unit=45.32,
            region=Region.SEBI.value,
            applicable_rules_json=["SEBI_EQUITY_EXPOSURE_MIN"],
        )
        db.add(fund)

        # -----------------------------------------------------
        # 2. compliance_rules (no dependencies)
        # -----------------------------------------------------
        rule = ComplianceRule(
            rule_id="SEBI_EQUITY_EXPOSURE_MIN",
            regulation_id="SEBI_MF_2017_49_1",
            rule_type=ViolationCategory.PORTFOLIO.value,
            region=Region.SEBI.value,
            title="Minimum Equity Exposure for Large-Cap Schemes",
            description="Large-cap equity schemes must maintain minimum 65% equity exposure",
            condition_plain_text="equity_exposure_pct >= 0.65",
            severity=Severity.HIGH.value,
            enforcement_level="automatic",
            confidence_threshold=0.95,
            required_evidence_types=["portfolio_disclosure"],
            regulation_section="SEBI(MF) Regulations, 2017, Clause 49.1",
            is_active=True,
            version_number=1,
        )
        db.add(rule)
        db.commit()  # commit so fund_id / rule_id exist before FK reference

        # -----------------------------------------------------
        # 3. audit_metadata (no dependencies)
        # -----------------------------------------------------
        audit = AuditMetadata(
            audit_id=f"audit_{uuid.uuid4().hex[:12]}",
            region=Region.SEBI.value,
            audit_type=AuditType.FULL_CORPUS.value,
            funds_audited_count=154,
            funds_passed_count=142,
            funds_with_violations_count=12,
            total_rules_evaluated=3080,
            total_violations_detected=12,
            critical_violations=2,
            high_violations=5,
            medium_violations=3,
            low_violations=2,
            overall_compliance_score=92.5,
            status=AuditStatus.COMPLETED.value,
            triggered_by="system",
            triggering_action="scheduled",
            escalation_triggered=False,
        )
        db.add(audit)
        db.commit()  # commit so audit_id exists before FK reference

        # -----------------------------------------------------
        # 4. violations (FK: audit_metadata, references fund/rule loosely)
        # -----------------------------------------------------
        violation = Violation(
            violation_id=f"v_{uuid.uuid4().hex[:12]}",
            audit_id=audit.audit_id,
            rule_id=rule.rule_id,
            fund_id=fund.fund_id,
            severity=Severity.HIGH.value,
            violation_type=ViolationCategory.PORTFOLIO.value,
            region=Region.SEBI.value,
            description="Equity exposure 62% below minimum 65% for large-cap equity scheme",
            actual_value="0.62",
            threshold_value="0.65",
            gap_percentage=-4.6,
            confidence_score=0.98,
            evidence_count=3,
            status=ViolationStatus.DETECTED.value,
            detected_at=_now_iso(),
            evidence_docs_json=["portfolio_disclosure_aug2026.pdf"],
            created_by="system",
        )
        db.add(violation)
        db.commit()  # commit so violation_id exists before FK reference

        # -----------------------------------------------------
        # 5. response_feedback (FK: audit_metadata, violations)
        # -----------------------------------------------------
        feedback = ResponseFeedback(
            response_id="11111111-1111-1111-1111-111111111111",
            interaction_id=str(uuid.uuid4()),
            session_id="22222222-2222-2222-2222-222222222222",
            turn_number=1,
            query_text="What is the equity exposure of Axis Bluechip Fund?",
            actor_id="reviewer_01",
            actor_role="Compliance & Regulatory Officer",
            selected_categories=["F03", "F07"],
            feedback_text="Confirmed the exposure figure is below the SEBI threshold.",
            answer_relevance_score=4,
            source_quality_score=5,
            completeness_score=4,
            automated_category="portfolio_compliance",
            automated_confidence=0.87,
            audit_id=audit.audit_id,
            violation_id=violation.violation_id,
        )
        db.add(feedback)

        # -----------------------------------------------------
        # 6. query_evidence (FK: audit_metadata)
        # -----------------------------------------------------
        query_ev = QueryEvidence(
            response_id="33333333-3333-3333-3333-333333333333",
            session_id="22222222-2222-2222-2222-222222222222",
            request_id=str(uuid.uuid4()),
            query_text="What is the equity exposure of Axis Bluechip Fund?",
            query_type="factual_lookup",
            query_intent="compliance_check",
            retrieval_mode="contextgraph",
            serving_engine="hybrid_v1",
            assembled_context_json={
                "chunks": ["portfolio_disclosure_aug2026.pdf#p3"],
                "graph_nodes": ["fund:AXIS_BLUECHIP", "rule:SEBI_EQUITY_EXPOSURE_MIN"],
            },
            synthesis_output_json={
                "answer": "Equity exposure is 62%, below the 65% SEBI minimum.",
                "confidence": 0.91,
            },
            graph_highlight_json={"path": ["fund:AXIS_BLUECHIP", "holds", "equity_position"]},
            latency_ms=842,
            retrieval_latency_ms=310,
            synthesis_latency_ms=532,
            quality_score=0.91,
            confidence_level=ConfidenceLevel.HIGH.value,
            audit_id=audit.audit_id,
            linked_violations_json=[violation.violation_id],
            has_feedback=True,
            feedback_summary_json={"positive": 1, "negative": 0},
        )
        db.add(query_ev)

        # -----------------------------------------------------
        # 7. sessions (FK: audit_metadata)
        # -----------------------------------------------------
        session_row = ChatSession(
            session_id="22222222-2222-2222-2222-222222222222",
            user_id="33333333-3333-3333-3333-333333333333",
            audit_id=audit.audit_id,
        )
        db.add(session_row)

        db.commit()

        print("Audit schema seed complete.\n")
        print(f"fund_id:      {fund.fund_id}")
        print(f"rule_id:      {rule.rule_id}")
        print(f"audit_id:     {audit.audit_id}")
        print(f"violation_id: {violation.violation_id}")
        print(f"feedback_id:  {feedback.feedback_id}")
        print(f"response_id (query_evidence): {query_ev.response_id}")
        print(f"session_id:   {session_row.session_id}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_audit_schema()
    