# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
migrate_data.py
===============
Migrates and comprehensively populates data.db (SQLAlchemy SQLite application database)
with:
  1. Fund Schemes (fund_schemes.csv + seed funds)
  2. Compliance Rules (rules.csv, sec_rules.csv, esma_rules.csv)
  3. Audit Metadata (authoritative historical & continuous audit records)
  4. Violations (detected compliance gaps linked to audits, rules, and funds)
  5. Chat Sessions (from logs/chat_sessions and chat_query_evidence)
  6. Query Evidence (from logs/chat_query_evidence/chat_evidence_*.json)
  7. Response Feedback (baseline seed records and all feedback written directly via API to data.db)
  8. Unified Evaluation Records (adjudicated evaluation linking feedback & evidence)
"""

import csv
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine, Base
from app.schemas import (
    AuditMetadata,
    Violation,
    ResponseFeedback,
    QueryEvidence,
    ComplianceRule,
    FundScheme,
    ChatSession,
    UnifiedEvaluationRecord,
)
from app.schemas.models import (
    Region,
    AuditType,
    AuditStatus,
    ComplianceTrend,
    ViolationCategory,
    ViolationStatus,
    Severity,
    ConfidenceLevel,
    EntryRoute,
    RootCause,
    LifecycleStatus,
    RepairTarget,
    AdjudicationVerdict,
    _now_iso,
)

logger = logging.getLogger("app.db.migrate_data")

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
COMPLIANCE_DATA_DIR = BASE_DIR / "data" / "compliance"
CHAT_EVIDENCE_DIR = BASE_DIR / "logs" / "chat_query_evidence"
CHAT_SESSIONS_DIR = BASE_DIR / "logs" / "chat_sessions"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def populate_fund_schemes(db: Session) -> int:
    """Populate fund_schemes table from fund_schemes.csv and seed funds."""
    count = 0
    csv_file = COMPLIANCE_DATA_DIR / "fund_schemes.csv"
    
    # Always include baseline seed funds
    baseline_funds = [
        {
            "fund_id": "AXIS_BLUECHIP",
            "isin": "INF846K01337",
            "name": "Axis Bluechip Fund",
            "fund_house": "Axis Mutual Fund",
            "category": "Equity",
            "mandate": "Large-cap equity growth",
            "risk_profile": "high",
            "aum_crores": 8500.50,
            "nav_per_unit": 45.32,
            "region": Region.SEBI.value,
            "applicable_rules_json": ["RULE_PORT_CONC_001", "SEBI_EQUITY_EXPOSURE_MIN"],
        }
    ]
    
    for f in baseline_funds:
        existing = db.query(FundScheme).filter_by(fund_id=f["fund_id"]).first()
        if not existing:
            db.add(FundScheme(**f))
            count += 1

    if csv_file.exists():
        with open(csv_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fid = row.get("fund_id", "").strip()
                if not fid:
                    continue
                existing = db.query(FundScheme).filter_by(fund_id=fid).first()
                if existing:
                    continue

                reg = row.get("region", "SEBI").strip().upper()
                if reg not in ("SEBI", "SEC", "ESMA"):
                    reg = "SEBI"

                try:
                    aum = float(row.get("aum_cr", 0.0))
                except (ValueError, TypeError):
                    aum = 0.0

                fund = FundScheme(
                    fund_id=fid,
                    isin=row.get("isin", "").strip() or None,
                    name=row.get("name", fid).strip(),
                    fund_house=row.get("fund_house", "Mutual Fund AMC").strip(),
                    category=row.get("category", "Equity").strip(),
                    mandate=row.get("mandate", "").strip() or None,
                    risk_profile=row.get("risk_profile", "moderate").strip() or None,
                    aum_crores=aum,
                    nav_per_unit=None,
                    region=reg,
                    applicable_rules_json=["RULE_PORT_CONC_001", "RULE_PORT_SECTOR_001"],
                )
                db.add(fund)
                count += 1

    db.commit()
    logger.info("Populated %d fund_schemes into data.db", count)
    return count


def populate_compliance_rules(db: Session) -> int:
    """Populate compliance_rules table from rules.csv, sec_rules.csv, and esma_rules.csv."""
    count = 0
    rule_files = [
        (COMPLIANCE_DATA_DIR / "rules.csv", "SEBI"),
        (COMPLIANCE_DATA_DIR / "sec_rules.csv", "SEC"),
        (COMPLIANCE_DATA_DIR / "esma_rules.csv", "ESMA"),
    ]

    # Baseline seed rule
    seed_rule = {
        "rule_id": "SEBI_EQUITY_EXPOSURE_MIN",
        "regulation_id": "SEBI_MF_2017_49_1",
        "rule_type": "portfolio",
        "region": "SEBI",
        "title": "Minimum Equity Exposure for Large-Cap Schemes",
        "description": "Large-cap equity schemes must maintain minimum 65% equity exposure",
        "condition_plain_text": "equity_exposure_pct >= 0.65",
        "condition_code_json": {"metric": "equity_exposure_pct", "operator": ">=", "threshold": 0.65},
        "severity": "high",
        "enforcement_level": "automatic",
        "confidence_threshold": 0.95,
        "required_evidence_types": ["portfolio_disclosure"],
        "regulation_section": "SEBI(MF) Regulations, 2017, Clause 49.1",
        "is_active": True,
        "version_number": 1,
    }
    if not db.query(ComplianceRule).filter_by(rule_id=seed_rule["rule_id"]).first():
        db.add(ComplianceRule(**seed_rule))
        count += 1

    valid_types = {"portfolio", "governance", "kyc", "risk", "reporting"}
    valid_severities = {"critical", "high", "medium", "low"}

    for csv_file, default_region in rule_files:
        if not csv_file.exists():
            continue
        with open(csv_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = row.get("rule_id", "").strip()
                if not rid:
                    continue
                if db.query(ComplianceRule).filter_by(rule_id=rid).first():
                    continue

                rtype = row.get("rule_type", "portfolio").strip().lower()
                if rtype not in valid_types:
                    rtype = "portfolio"

                r_reg = row.get("region", default_region).strip().upper()
                if r_reg not in ("SEBI", "SEC", "ESMA"):
                    r_reg = default_region

                r_sev = row.get("severity", "medium").strip().lower()
                if r_sev not in valid_severities:
                    r_sev = "medium"

                try:
                    conf = float(row.get("confidence_threshold", 0.95))
                    conf = max(0.0, min(1.0, conf))
                except (ValueError, TypeError):
                    conf = 0.95

                metric = row.get("metric", "").strip()
                cond = row.get("condition", "").strip()
                thresh = row.get("threshold", "").strip()
                cond_plain = f"{metric} {cond} {thresh}".strip() if metric else row.get("description", "")

                rule = ComplianceRule(
                    rule_id=rid,
                    regulation_id=row.get("regulation_id", "").strip() or None,
                    rule_type=rtype,
                    region=r_reg,
                    title=row.get("title", rid).strip(),
                    description=row.get("description", "").strip() or None,
                    condition_plain_text=cond_plain or None,
                    condition_code_json={"metric": metric, "condition": cond, "threshold": thresh},
                    applicable_categories=[row.get("applicable_funds", "All").strip()],
                    severity=r_sev,
                    enforcement_level="automatic",
                    confidence_threshold=conf,
                    required_evidence_types=["regulatory_disclosure"],
                    is_active=True,
                    version_number=1,
                    regulation_section=row.get("regulation_id", "").strip() or None,
                )
                db.add(rule)
                count += 1

    db.commit()
    logger.info("Populated %d compliance_rules into data.db", count)
    return count


def populate_audit_metadata_and_violations(db: Session) -> tuple[int, int]:
    """Populate audit_metadata and violations tables with comprehensive audit runs."""
    audit_count = 0
    violation_count = 0

    audits_data = [
        {
            "audit_id": "audit_20260901_123456",
            "audit_run_timestamp": "2026-09-01T10:00:00Z",
            "region": "SEBI",
            "audit_type": "full_corpus",
            "funds_audited_count": 10,
            "funds_passed_count": 6,
            "funds_with_violations_count": 4,
            "total_rules_evaluated": 320,
            "total_violations_detected": 4,
            "critical_violations": 1,
            "high_violations": 2,
            "medium_violations": 1,
            "low_violations": 0,
            "audit_duration_ms": 4250,
            "overall_compliance_score": 92.5,
            "compliance_trend": "stable",
            "status": "completed",
            "triggered_by": "system_scheduler",
            "triggering_action": "scheduled_quarterly_run",
            "report_id": "rep_sebi_20260901",
        },
        {
            "audit_id": "audit_20260910_sebi_scheduled",
            "audit_run_timestamp": "2026-09-10T08:00:00Z",
            "region": "SEBI",
            "audit_type": "batch",
            "funds_audited_count": 10,
            "funds_passed_count": 8,
            "funds_with_violations_count": 2,
            "total_rules_evaluated": 320,
            "total_violations_detected": 2,
            "critical_violations": 0,
            "high_violations": 1,
            "medium_violations": 1,
            "low_violations": 0,
            "audit_duration_ms": 3120,
            "overall_compliance_score": 96.0,
            "compliance_trend": "improving",
            "status": "completed",
            "triggered_by": "compliance_officer",
            "triggering_action": "pre_launch_batch_audit",
            "report_id": "rep_sebi_20260910",
        },
        {
            "audit_id": "audit_20260915_sec_batch",
            "audit_run_timestamp": "2026-09-15T12:00:00Z",
            "region": "SEC",
            "audit_type": "batch",
            "funds_audited_count": 5,
            "funds_passed_count": 4,
            "funds_with_violations_count": 1,
            "total_rules_evaluated": 270,
            "total_violations_detected": 1,
            "critical_violations": 0,
            "high_violations": 1,
            "medium_violations": 0,
            "low_violations": 0,
            "audit_duration_ms": 2890,
            "overall_compliance_score": 95.5,
            "compliance_trend": "stable",
            "status": "completed",
            "triggered_by": "sec_compliance_lead",
            "triggering_action": "ica_1940_quarterly_check",
            "report_id": "rep_sec_20260915",
        },
        {
            "audit_id": "audit_20260917_esma_batch",
            "audit_run_timestamp": "2026-09-17T09:00:00Z",
            "region": "ESMA",
            "audit_type": "batch",
            "funds_audited_count": 6,
            "funds_passed_count": 5,
            "funds_with_violations_count": 1,
            "total_rules_evaluated": 324,
            "total_violations_detected": 1,
            "critical_violations": 1,
            "high_violations": 0,
            "medium_violations": 0,
            "low_violations": 0,
            "audit_duration_ms": 2980,
            "overall_compliance_score": 94.0,
            "compliance_trend": "stable",
            "status": "completed",
            "triggered_by": "esma_auditor",
            "triggering_action": "ucits_compliance_audit",
            "report_id": "rep_esma_20260917",
        },
    ]

    for a in audits_data:
        if not db.query(AuditMetadata).filter_by(audit_id=a["audit_id"]).first():
            db.add(AuditMetadata(**a))
            audit_count += 1
    db.commit()

    violations_data = [
        {
            "violation_id": "v_20260901_001",
            "audit_id": "audit_20260901_123456",
            "rule_id": "SEBI_EQUITY_EXPOSURE_MIN",
            "fund_id": "AXIS_BLUECHIP",
            "severity": "high",
            "violation_type": "portfolio",
            "region": "SEBI",
            "description": "Equity exposure 62% below minimum 65% for large-cap equity scheme",
            "actual_value": "0.62",
            "threshold_value": "0.65",
            "gap_percentage": -4.6,
            "confidence_score": 0.98,
            "evidence_count": 3,
            "status": "detected",
            "detected_at": "2026-09-01T10:30:15Z",
            "evidence_docs_json": ["portfolio_disclosure_aug2026.pdf"],
            "created_by": "system",
        },
        {
            "violation_id": "v_20260901_002",
            "audit_id": "audit_20260901_123456",
            "rule_id": "RULE_PORT_CONC_001",
            "fund_id": "SEBI_FUND_001",
            "severity": "critical",
            "violation_type": "portfolio",
            "region": "SEBI",
            "description": "Single security holding at 16.4% exceeds the 15% maximum statutory cap",
            "actual_value": "0.164",
            "threshold_value": "0.150",
            "gap_percentage": 9.33,
            "confidence_score": 0.99,
            "evidence_count": 4,
            "status": "reviewed",
            "detected_at": "2026-09-01T10:31:00Z",
            "evidence_docs_json": ["monthly_factsheet_hdfc_aug2026.pdf"],
            "created_by": "system",
        },
        {
            "violation_id": "v_20260901_003",
            "audit_id": "audit_20260901_123456",
            "rule_id": "RULE_PORT_SECTOR_001",
            "fund_id": "SEBI_FUND_004",
            "severity": "high",
            "violation_type": "portfolio",
            "region": "SEBI",
            "description": "Financial Services sector concentration at 32.8% exceeds the 30% limit",
            "actual_value": "0.328",
            "threshold_value": "0.300",
            "gap_percentage": 9.33,
            "confidence_score": 0.96,
            "evidence_count": 2,
            "status": "detected",
            "detected_at": "2026-09-01T10:32:00Z",
            "evidence_docs_json": ["nippon_smallcap_portfolio.pdf"],
            "created_by": "system",
        },
        {
            "violation_id": "v_20260901_004",
            "audit_id": "audit_20260901_123456",
            "rule_id": "RULE_PORT_UNRATED_001",
            "fund_id": "SEBI_FUND_002",
            "severity": "medium",
            "violation_type": "portfolio",
            "region": "SEBI",
            "description": "Unrated debt exposure 5.8% exceeds statutory ceiling of 5.0%",
            "actual_value": "0.058",
            "threshold_value": "0.050",
            "gap_percentage": 16.0,
            "confidence_score": 0.94,
            "evidence_count": 2,
            "status": "remediated",
            "detected_at": "2026-09-01T10:33:00Z",
            "resolved_at": "2026-09-05T14:00:00Z",
            "resolution_action": "Portfolio rebalanced to bring unrated debt to 4.2%",
            "evidence_docs_json": ["icici_corp_bond_disclosure.pdf"],
            "created_by": "system",
        },
    ]

    for v in violations_data:
        if not db.query(Violation).filter_by(violation_id=v["violation_id"]).first():
            db.add(Violation(**v))
            violation_count += 1
    db.commit()

    logger.info("Populated %d audits and %d violations into data.db", audit_count, violation_count)
    return audit_count, violation_count


def populate_chat_sessions_and_query_evidence(db: Session) -> tuple[int, int]:
    """Ingest chat sessions and query_evidence records from on-disk JSON logs."""
    session_count = 0
    evidence_count = 0
    default_audit_id = "audit_20260901_123456"

    # 1. From CHAT_EVIDENCE_DIR
    if CHAT_EVIDENCE_DIR.exists():
        for json_path in CHAT_EVIDENCE_DIR.glob("*.json"):
            try:
                with open(json_path, mode="r", encoding="utf-8") as f:
                    data = json.load(f)

                # Ingest session
                sess_info = data.get("session", {})
                sid = sess_info.get("session_id")
                if sid:
                    existing_sess = db.query(ChatSession).filter_by(session_id=sid).first()
                    if not existing_sess:
                        session_row = ChatSession(
                            session_id=sid,
                            user_id=sess_info.get("user_id"),
                            created_at=sess_info.get("created_at", _now()),
                            updated_at=sess_info.get("updated_at", _now()),
                            ended_at=sess_info.get("ended_at"),
                            audit_id=default_audit_id,
                        )
                        db.add(session_row)
                        db.commit()
                        session_count += 1

                # Ingest query evidence turns
                turns = data.get("query_evidence", [])
                for t in turns:
                    resp_id = t.get("response_id")
                    if not resp_id:
                        continue
                    if db.query(QueryEvidence).filter_by(response_id=resp_id).first():
                        continue

                    # Ensure parent session exists
                    t_sid = t.get("session_id") or sid
                    if t_sid and not db.query(ChatSession).filter_by(session_id=t_sid).first():
                        db.add(ChatSession(
                            session_id=t_sid,
                            user_id="default_user",
                            created_at=_now(),
                            updated_at=_now(),
                            audit_id=default_audit_id,
                        ))
                        db.commit()
                        session_count += 1

                    q_ev = QueryEvidence(
                        response_id=resp_id,
                        session_id=t_sid,
                        request_id=t.get("request_id"),
                        query_text=t.get("query_text", ""),
                        query_type=t.get("query_type"),
                        query_intent=t.get("query_intent"),
                        retrieval_mode=t.get("retrieval_mode", "contextgraph"),
                        serving_engine=t.get("serving_engine", "hybrid_v1"),
                        assembled_context_json=t.get("assembled_context_json") or {},
                        synthesis_output_json=t.get("synthesis_output_json") or {},
                        graph_highlight_json=t.get("graph_highlight_json"),
                        traditional_result_json=t.get("traditional_result_json"),
                        latency_ms=t.get("latency_ms", 500),
                        retrieval_latency_ms=t.get("retrieval_latency_ms", 200),
                        synthesis_latency_ms=t.get("synthesis_latency_ms", 300),
                        quality_score=t.get("quality_score", 0.9),
                        confidence_level="high",
                        audit_id=default_audit_id,
                        linked_violations_json=t.get("linked_violations_json", []),
                        has_feedback=bool(t.get("has_feedback", False)),
                        feedback_summary_json=t.get("feedback_summary_json"),
                        created_at=t.get("created_at", _now()),
                    )
                    db.add(q_ev)
                    evidence_count += 1
                db.commit()
            except Exception as e:
                logger.warning("Error processing evidence file %s: %s", json_path.name, e)
                db.rollback()

    # 2. Also register any standalone chat sessions in CHAT_SESSIONS_DIR
    if CHAT_SESSIONS_DIR.exists():
        for sp in CHAT_SESSIONS_DIR.glob("*.json"):
            sid = sp.stem
            if not db.query(ChatSession).filter_by(session_id=sid).first():
                try:
                    db.add(ChatSession(
                        session_id=sid,
                        user_id="user_chat_session",
                        created_at=_now(),
                        updated_at=_now(),
                        audit_id=default_audit_id,
                    ))
                    db.commit()
                    session_count += 1
                except Exception:
                    db.rollback()

    logger.info("Populated %d sessions and %d query_evidence into data.db", session_count, evidence_count)
    return session_count, evidence_count


def populate_response_feedback(db: Session) -> int:
    """Populate baseline feedback records into data.db (single source of truth).
    
    Note: feedback.db has been deprecated. All feedback is now written directly 
    to data.db via the API endpoints. This function seeds baseline feedback for
    demo/testing purposes only.
    """
    count = 0
    default_audit_id = "audit_20260901_123456"

    # Seed baseline feedback if empty
    seed_feedback = [
        {
            "feedback_id": "fb_seed_001",
            "response_id": "resp_seed_baseline_001",
            "interaction_id": "int_4d5f72d3-a66a-4a89-b1e2-39e0de73e7fe",
            "session_id": "4d5f72d3-a66a-4a89-b1e2-39e0de73e7fe",
            "turn_number": 1,
            "query_text": "Can you give me the characteristics of the liquid fund",
            "actor_id": "sarah_compliance_lead",
            "actor_role": "Compliance & Regulatory Officer",
            "selected_categories": ["F01", "F03"],
            "feedback_text": "Confirmed liquid fund residual maturity is capped at 91 days.",
            "answer_relevance_score": 5,
            "source_quality_score": 4,
            "completeness_score": 5,
            "automated_category": "compliance",
            "automated_confidence": 0.92,
            "audit_id": default_audit_id,
        }
    ]

    for fb in seed_feedback:
        existing = db.query(ResponseFeedback).filter(
            (ResponseFeedback.feedback_id == fb["feedback_id"])
            | ((ResponseFeedback.response_id == fb["response_id"]) & (ResponseFeedback.actor_id == fb["actor_id"]))
        ).first()
        if not existing:
            if not db.query(ChatSession).filter_by(session_id=fb["session_id"]).first():
                db.add(ChatSession(session_id=fb["session_id"], audit_id=default_audit_id))
                db.commit()
            try:
                db.add(ResponseFeedback(**fb))
                db.commit()
                count += 1
            except Exception as e:
                logger.warning("Could not add baseline feedback row: %s", e)
                db.rollback()

    logger.info("Populated %d baseline response_feedback records into data.db", count)
    return count


def populate_unified_evaluation_records(db: Session) -> int:
    """Populate unified_evaluation_records linking feedback and query evidence."""
    count = 0
    records = [
        {
            "session_id": "4d5f72d3-a66a-4a89-b1e2-39e0de73e7fe",
            "response_id": "resp_0aadfe67d35b",
            "entry_route": "hitl",
            "feedback_ref": "fb_seed_001",
            "evidence_snapshot_ref": "resp_0aadfe67d35b",
            "root_cause": "compliance",
            "severity": "medium",
            "lifecycle_status": "resolved",
            "repair": False,
            "repair_target": None,
            "adjudication_verdict": "valid",
            "adjudication_confidence": 0.94,
        }
    ]

    for rec in records:
        # Check evidence exists
        if not db.query(QueryEvidence).filter_by(response_id=rec["evidence_snapshot_ref"]).first():
            continue
        existing = db.query(UnifiedEvaluationRecord).filter_by(
            session_id=rec["session_id"], response_id=rec["response_id"]
        ).first()
        if not existing:
            db.add(UnifiedEvaluationRecord(**rec))
            count += 1

    db.commit()
    logger.info("Populated %d unified_evaluation_records into data.db", count)
    return count


def populate_data_db() -> Dict[str, Any]:
    """Master population entrypoint for data.db."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    results = {}
    try:
        results["fund_schemes"] = populate_fund_schemes(db)
        results["compliance_rules"] = populate_compliance_rules(db)
        audits, violations = populate_audit_metadata_and_violations(db)
        results["audit_metadata"] = audits
        results["violations"] = violations
        sessions, evidence = populate_chat_sessions_and_query_evidence(db)
        results["chat_sessions"] = sessions
        results["query_evidence"] = evidence
        results["response_feedback"] = populate_response_feedback(db)
        results["unified_evaluation_records"] = populate_unified_evaluation_records(db)
        logger.info("All data.db tables populated successfully: %s", results)
    finally:
        db.close()
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Beginning migration and population of data.db...")
    res = populate_data_db()
    print("Migration finished successfully! Summary:")
    for table, count in res.items():
        print(f"  {table}: {count} rows added/verified")
