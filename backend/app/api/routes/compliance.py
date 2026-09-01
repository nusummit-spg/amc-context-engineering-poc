# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
routes/compliance.py
====================
FastAPI REST endpoints for AMC Compliance Auditing, Scorecards, Remediation,
and Autonomous Domain Agents.
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import Container, get_container
from app.compliance.audit_integration import log_resolution_audit, store_agent_metrics
from app.compliance.escalation_engine import EscalationEngine
from app.compliance.security import get_client_role, limit_requests, require_roles
from app.schemas.compliance_models import (
    AggregatedAgentMetrics,
    AuditReportResponse,
    ComplianceAuditResultResponse,
    ComplianceScorecard,
    RegionEnum,
    ResolveViolationRequest,
    Role,
    SeverityEnum,
    ViolationResponse,
    ViolationStatusEnum,
)

logger = logging.getLogger("api.routes.compliance")
router = APIRouter(prefix="/compliance", tags=["compliance"])

# In-memory scorecard cache with 60-second TTL
_SCORECARD_CACHE: Dict[str, Dict[str, Any]] = {}
_SCORECARD_CACHE_TTL_SEC = 60.0


class MultiAgentAuditRequest(BaseModel):
    fund_id: str = Field(..., pattern="^[A-Za-z0-9_\\-]+$", description="Fund ID must be alphanumeric")
    fund_data: Optional[Dict[str, Any]] = None
    region: Optional[RegionEnum] = RegionEnum.SEBI


@router.post("/audit", response_model=ComplianceAuditResultResponse)
@limit_requests(max_requests=100, window_seconds=60)
async def run_compliance_audit(
    request: Request,
    region: RegionEnum = Query(RegionEnum.SEBI, description="Regulatory jurisdiction: SEBI, SEC, ESMA"),
    container: Container = Depends(get_container),
):
    """Trigger automated compliance audit across all registered funds in region."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    result = await detector.audit_all_funds(region=region.value)

    # Invalidate cached scorecard for region upon new audit
    _SCORECARD_CACHE.pop(region.value, None)

    return ComplianceAuditResultResponse(
        audit_id=result.audit_id,
        audit_started_at=result.audit_started_at,
        audit_completed_at=result.audit_completed_at,
        total_funds=result.total_funds,
        total_rules_evaluated=result.total_rules_evaluated,
        total_violations=result.total_violations,
        critical_violations=result.critical_violations,
        high_violations=result.high_violations,
        medium_violations=result.medium_violations,
        low_violations=result.low_violations,
        violations_by_fund=result.violations_by_fund,
        violations_by_rule=result.violations_by_rule,
        regions=result.regions,
        violations=[
            ViolationResponse(
                violation_id=v.violation_id,
                rule_id=v.rule_id,
                fund_id=v.fund_id,
                severity=SeverityEnum(v.severity),
                confidence=v.confidence,
                actual_value=v.actual_value,
                threshold_value=v.threshold_value,
                description=v.description,
                detected_at=v.detected_at,
                status=ViolationStatusEnum(v.status),
                region=RegionEnum(v.region),
                evidence_docs=v.evidence_docs,
            )
            for v in result.violations
        ],
    )


@router.get("/violations", response_model=List[ViolationResponse])
@limit_requests(max_requests=100, window_seconds=60)
async def get_violations(
    request: Request,
    region: RegionEnum = Query(RegionEnum.SEBI),
    severity: Optional[SeverityEnum] = Query(None, description="Filter by severity"),
    fund_id: Optional[str] = Query(None, description="Filter by specific fund ID"),
    status: Optional[ViolationStatusEnum] = Query(ViolationStatusEnum.DETECTED),
    limit: int = Query(100, le=10000),
    container: Container = Depends(get_container),
):
    """Query compliance violations with multi-parameter filtering."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    violations = await detector.get_violations(
        region=region.value,
        severity=severity.value if severity else None,
        fund_id=fund_id,
        status=status.value if status else None,
        limit=limit,
    )

    return [
        ViolationResponse(
            violation_id=v.violation_id,
            rule_id=v.rule_id,
            fund_id=v.fund_id,
            severity=SeverityEnum(v.severity),
            confidence=v.confidence,
            actual_value=v.actual_value,
            threshold_value=v.threshold_value,
            description=v.description,
            detected_at=v.detected_at,
            status=ViolationStatusEnum(v.status),
            region=RegionEnum(v.region),
            evidence_docs=v.evidence_docs,
            resolved_at=v.resolved_at,
            resolution_action=v.resolution_action,
        )
        for v in violations
    ]


@router.get("/fund/{fund_id}/violations", response_model=List[ViolationResponse])
@limit_requests(max_requests=100, window_seconds=60)
async def get_fund_violations(
    fund_id: str,
    request: Request,
    container: Container = Depends(get_container),
):
    """Get all violations for a specific fund scheme."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    violations = await detector.get_violations(fund_id=fund_id, status=None, limit=200)
    return [
        ViolationResponse(
            violation_id=v.violation_id,
            rule_id=v.rule_id,
            fund_id=v.fund_id,
            severity=SeverityEnum(v.severity),
            confidence=v.confidence,
            actual_value=v.actual_value,
            threshold_value=v.threshold_value,
            description=v.description,
            detected_at=v.detected_at,
            status=ViolationStatusEnum(v.status),
            region=RegionEnum(v.region),
            evidence_docs=v.evidence_docs,
            resolved_at=v.resolved_at,
            resolution_action=v.resolution_action,
        )
        for v in violations
    ]


@router.post("/violations/{violation_id}/resolve")
@limit_requests(max_requests=10, window_seconds=60)
@require_roles([Role.RESOLVER, Role.ADMIN])
async def resolve_violation(
    violation_id: str,
    req: ResolveViolationRequest,
    request: Request,
    current_role: Role = Depends(get_client_role),
    container: Container = Depends(get_container),
):
    """Mark a violation as remediated with RBAC enforcement and audit trail logging."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    result = await detector.resolve_violation(violation_id, req.resolution_action)

    # Invalidate cached scorecard
    _SCORECARD_CACHE.clear()

    # Immutable audit logging
    await log_resolution_audit(
        violation_id=violation_id,
        action=req.resolution_action,
        user_id=f"user_{current_role.value}",
        graph_client=container.graph,
    )

    return result


@router.get("/scorecard", response_model=ComplianceScorecard)
@limit_requests(max_requests=100, window_seconds=60)
async def get_compliance_scorecard(
    request: Request,
    region: RegionEnum = Query(RegionEnum.SEBI),
    container: Container = Depends(get_container),
):
    """Get real-time AMC compliance scorecard with 60-second in-memory caching for <500ms SLA."""
    now_ts = time.time()
    cache_entry = _SCORECARD_CACHE.get(region.value)
    if cache_entry and (now_ts - cache_entry["cached_at"]) < _SCORECARD_CACHE_TTL_SEC:
        scorecard = cache_entry["payload"]
    else:
        detector = getattr(container, "violation_detector", None)
        if not detector:
            from app.compliance.violation_detector import ViolationDetector
            detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

        scorecard = await detector.get_compliance_scorecard(region=region.value)
        _SCORECARD_CACHE[region.value] = {"cached_at": now_ts, "payload": scorecard}

    return ComplianceScorecard(
        overall_compliance_score=scorecard["overall_compliance_score"],
        compliance_percentage=scorecard["compliance_percentage"],
        total_rules=scorecard["total_rules"],
        rules_passing=scorecard["rules_passing"],
        rules_with_violations=scorecard["rules_with_violations"],
        violations=scorecard["violations"],
        region=region,
        last_audit_at=scorecard.get("last_audit_at"),
    )


@router.get("/agents/metrics", response_model=AggregatedAgentMetrics)
@limit_requests(max_requests=100, window_seconds=60)
async def get_agent_metrics(
    request: Request,
    region: RegionEnum = Query(RegionEnum.SEBI),
    container: Container = Depends(get_container),
):
    """Get performance telemetry, accuracy, and latency percentiles for all domain agents."""
    orchestrator = getattr(container, "compliance_orchestrator", None)
    if not orchestrator:
        from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator
        orchestrator = ComplianceAgentOrchestrator(container.graph, getattr(container, "rules_engine", None))

    agent_metrics = orchestrator.get_agent_metrics(region=region.value)

    # Persist to Neo4j / audit
    await store_agent_metrics(agent_metrics, graph_client=container.graph, region=region.value)

    # Calculate overall latency
    overall_latency = sum(m.avg_latency_ms for m in agent_metrics.values())

    return AggregatedAgentMetrics(
        agents=agent_metrics,
        overall_latency_ms=round(overall_latency, 2),
        violations_by_severity={
            "critical": sum(1 for m in agent_metrics.values() if m.violations_detected > 0),
            "high": sum(m.violations_detected for m in agent_metrics.values()),
            "medium": 0,
            "low": 0,
        },
        recorded_at=datetime.now().isoformat(),
        region=region,
    )


import re
from fastapi.responses import PlainTextResponse
from app.schemas.compliance_models import (
    AggregatedAgentMetrics,
    AuditBatchRequest,
    AuditFundRequest,
    AuditReportResponse,
    ComplianceAuditResultResponse,
    ComplianceScorecard,
    HealthCheckResponse,
    RegionEnum,
    ResolveViolationRequest,
    Role,
    SeverityEnum,
    ViolationResponse,
    ViolationStatusEnum,
)

_SERVICE_START_TIME = time.time()
_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FUND_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]+$")


@router.get("/health", response_model=HealthCheckResponse)
async def get_compliance_health(
    container: Container = Depends(get_container),
):
    """Detailed health check and diagnostic probe for AMC compliance services."""
    neo4j_ok = False
    try:
        if container.graph:
            neo4j_ok = await container.graph.ping()
    except Exception:
        neo4j_ok = False

    engine = getattr(container, "rules_engine", None)
    if not engine:
        from app.compliance.rules_engine import RulesEngine
        engine = RulesEngine(container.graph)

    cached_rules = engine._rule_cache or {}
    breakdown = {"SEBI": 0, "SEC": 0, "ESMA": 0}
    for r in cached_rules.values():
        reg = getattr(r, "region", "SEBI")
        if reg in breakdown:
            breakdown[reg] += 1

    uptime = time.time() - _SERVICE_START_TIME

    return HealthCheckResponse(
        status="healthy" if (neo4j_ok or len(cached_rules) > 0) else "degraded",
        service="amc-compliance-engine",
        version="3.0.0",
        neo4j_connected=neo4j_ok,
        rules_cached_count=len(cached_rules),
        rule_breakdown_by_region=breakdown,
        active_agents=[
            "PortfolioAgent",
            "GovernanceAgent",
            "KYCAgent",
            "RiskAgent",
            "ReportingAgent",
        ],
        scorecard_cache_entries=len(_SCORECARD_CACHE),
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.now().isoformat(),
    )


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(
    container: Container = Depends(get_container),
):
    """Expose Prometheus formatted metrics for scrapers."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    lines = [
        "# HELP amc_compliance_score_ratio Overall compliance score between 0.0 and 1.0",
        "# TYPE amc_compliance_score_ratio gauge",
    ]
    for reg in ["SEBI", "SEC", "ESMA"]:
        scorecard = await detector.get_compliance_scorecard(region=reg)
        ratio = scorecard["overall_compliance_score"] / 100.0
        lines.append(f'amc_compliance_score_ratio{{region="{reg}"}} {ratio:.4f}')

    lines.extend([
        "# HELP amc_compliance_violations_total Total active compliance violations count",
        "# TYPE amc_compliance_violations_total gauge",
    ])
    for reg in ["SEBI", "SEC", "ESMA"]:
        scorecard = await detector.get_compliance_scorecard(region=reg)
        for sev, count in scorecard.get("violations", {}).items():
            lines.append(f'amc_compliance_violations_total{{region="{reg}",severity="{sev}"}} {count}')

    lines.extend([
        "# HELP amc_compliance_uptime_seconds Engine process uptime in seconds",
        "# TYPE amc_compliance_uptime_seconds counter",
        f"amc_compliance_uptime_seconds {round(time.time() - _SERVICE_START_TIME, 2)}",
    ])

    return "\n".join(lines) + "\n"


@router.get("/audit-report", response_model=AuditReportResponse)
@limit_requests(max_requests=50, window_seconds=60)
async def generate_audit_report(
    request: Request,
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    region: Optional[RegionEnum] = Query(RegionEnum.SEBI),
    container: Container = Depends(get_container),
):
    """Generate regulatory compliance audit report for a historical date range with strict input validation."""
    if not _DATE_REGEX.match(start_date) or not _DATE_REGEX.match(end_date):
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. start_date and end_date must be in ISO format YYYY-MM-DD (e.g. 2024-01-01)",
        )
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=f"start_date ({start_date}) must be earlier than or equal to end_date ({end_date})",
        )

    cypher = """
    MATCH (v:Violation)
    WHERE v.detected_at >= $start_date AND v.detected_at <= $end_date
      AND ($region IS NULL OR v.region = $region)
    RETURN count(*) AS total_violations,
           sum(CASE WHEN v.severity = 'critical' THEN 1 ELSE 0 END) AS critical,
           sum(CASE WHEN v.status = 'remediated' THEN 1 ELSE 0 END) AS remediated
    """
    total_violations = 0
    critical = 0
    remediated = 0

    try:
        results = await container.graph.run(
            cypher,
            start_date=start_date,
            end_date=end_date + "T23:59:59",
            region=region.value if region else None,
        )
        if results and results[0]:
            total_violations = int(results[0].get("total_violations") or 0)
            critical = int(results[0].get("critical") or 0)
            remediated = int(results[0].get("remediated") or 0)
    except Exception:
        # Fallback offline calculations
        detector = getattr(container, "violation_detector", None)
        if detector and detector.rules_engine:
            v_cache = detector.rules_engine._violations_cache.values()
            filtered = [
                v for v in v_cache
                if v.detected_at >= start_date and (not region or v.region == region.value)
            ]
            total_violations = len(filtered)
            critical = sum(1 for v in filtered if v.severity == "critical")
            remediated = sum(1 for v in filtered if v.status == "remediated")

    remediation_rate = round((remediated / total_violations * 100.0), 1) if total_violations > 0 else 100.0

    return AuditReportResponse(
        period=f"{start_date} to {end_date}",
        total_violations=total_violations,
        critical_violations=critical,
        remediated_violations=remediated,
        remediation_rate=remediation_rate,
        generated_at=datetime.now().isoformat(),
        region=region,
    )


@router.post("/batch-audit")
@limit_requests(max_requests=20, window_seconds=60)
async def run_batch_audit(
    req: AuditBatchRequest,
    container: Container = Depends(get_container),
):
    """Run concurrent parallel audit across an arbitrary list of fund schemas."""
    orchestrator = getattr(container, "compliance_orchestrator", None)
    if not orchestrator:
        from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator
        orchestrator = ComplianceAgentOrchestrator(container.graph, getattr(container, "rules_engine", None))

    region_str = req.region.value if req.region else "SEBI"
    res = await orchestrator.audit_all_funds(
        funds=req.funds,
        region=region_str,
        concurrency=req.concurrency,
    )
    _SCORECARD_CACHE.clear()
    return res


@router.post("/load-rules")
async def load_rules(
    container: Container = Depends(get_container),
):
    """Reload all active compliance rules into memory cache."""
    engine = getattr(container, "rules_engine", None)
    if not engine:
        from app.compliance.rules_engine import RulesEngine
        engine = RulesEngine(container.graph)

    count = await engine.load_rules()
    _SCORECARD_CACHE.clear()
    return {"status": "success", "rules_loaded": count}


@router.post("/agents/audit")
async def run_multi_agent_audit(
    req: MultiAgentAuditRequest,
    container: Container = Depends(get_container),
):
    """Trigger parallel 5-agent domain compliance audit for a fund."""
    if not _FUND_ID_REGEX.match(req.fund_id):
        raise HTTPException(status_code=400, detail="Invalid fund_id: must be alphanumeric, hyphen, or underscore")

    orchestrator = getattr(container, "compliance_orchestrator", None)
    if not orchestrator:
        from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator
        orchestrator = ComplianceAgentOrchestrator(container.graph, getattr(container, "rules_engine", None))

    region_str = req.region.value if req.region else "SEBI"
    res = await orchestrator.audit_fund_all_domains(req.fund_id, req.fund_data, region=region_str)
    return res




@router.get("/export/violations-csv")
@limit_requests(max_requests=50, window_seconds=60)
async def export_violations_csv(
    request: Request,
    region: RegionEnum = Query(RegionEnum.SEBI),
    severity: Optional[SeverityEnum] = Query(None),
    container: Container = Depends(get_container),
):
    """Export violations as CSV for regulatory reporting."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    violations = await detector.get_violations(
        region=region.value,
        severity=severity.value if severity else None,
        limit=10000,
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "violation_id", "rule_id", "fund_id", "severity", "confidence",
            "actual_value", "threshold_value", "description", "detected_at",
            "status", "region", "evidence_docs"
        ]
    )
    writer.writeheader()
    for v in violations:
        writer.writerow({
            "violation_id": v.violation_id,
            "rule_id": v.rule_id,
            "fund_id": v.fund_id,
            "severity": v.severity,
            "confidence": f"{v.confidence:.2f}",
            "actual_value": v.actual_value,
            "threshold_value": v.threshold_value,
            "description": v.description,
            "detected_at": v.detected_at,
            "status": v.status,
            "region": v.region,
            "evidence_docs": "; ".join(v.evidence_docs) if v.evidence_docs else "",
        })

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=violations_{region.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@router.get("/fund/{fund_id}")
@limit_requests(max_requests=100, window_seconds=60)
async def get_fund_details(
    fund_id: str,
    request: Request,
    container: Container = Depends(get_container),
):
    """Get fund details including violation summary."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    violations = await detector.get_violations(fund_id=fund_id, status=None, limit=1000)
    
    severity_counts = {
        "critical": sum(1 for v in violations if v.severity == "critical"),
        "high": sum(1 for v in violations if v.severity == "high"),
        "medium": sum(1 for v in violations if v.severity == "medium"),
        "low": sum(1 for v in violations if v.severity == "low"),
    }

    return {
        "fund_id": fund_id,
        "total_violations": len(violations),
        "violations_by_severity": severity_counts,
        "latest_audit": max((v.detected_at for v in violations), default=None),
        "violations": [
            ViolationResponse(
                violation_id=v.violation_id,
                rule_id=v.rule_id,
                fund_id=v.fund_id,
                severity=SeverityEnum(v.severity),
                confidence=v.confidence,
                actual_value=v.actual_value,
                threshold_value=v.threshold_value,
                description=v.description,
                detected_at=v.detected_at,
                status=ViolationStatusEnum(v.status),
                region=RegionEnum(v.region),
                evidence_docs=v.evidence_docs,
            )
            for v in violations[:100]  # Limit to 100 most recent
        ],
    }


@router.get("/rules/{rule_id}/violations")
@limit_requests(max_requests=100, window_seconds=60)
async def get_rule_violations(
    rule_id: str,
    request: Request,
    region: Optional[RegionEnum] = Query(None),
    container: Container = Depends(get_container),
):
    """Get all violations triggered by a specific compliance rule."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    all_violations = await detector.get_violations(status=None, limit=10000)
    filtered = [v for v in all_violations if v.rule_id == rule_id]
    if region:
        filtered = [v for v in filtered if v.region == region.value]

    return {
        "rule_id": rule_id,
        "total_violations": len(filtered),
        "violations": [
            ViolationResponse(
                violation_id=v.violation_id,
                rule_id=v.rule_id,
                fund_id=v.fund_id,
                severity=SeverityEnum(v.severity),
                confidence=v.confidence,
                actual_value=v.actual_value,
                threshold_value=v.threshold_value,
                description=v.description,
                detected_at=v.detected_at,
                status=ViolationStatusEnum(v.status),
                region=RegionEnum(v.region),
                evidence_docs=v.evidence_docs,
            )
            for v in filtered
        ],
    }


@router.get("/status")
async def get_compliance_status(
    request: Request,
    container: Container = Depends(get_container),
):
    """Get overall compliance system status and operational metrics."""
    detector = getattr(container, "violation_detector", None)
    if not detector:
        from app.compliance.violation_detector import ViolationDetector
        detector = ViolationDetector(container.graph, getattr(container, "rules_engine", None))

    # Get aggregate statistics
    all_violations = await detector.get_violations(status=None, limit=100000)
    
    severity_counts = {
        "critical": sum(1 for v in all_violations if v.severity == "critical"),
        "high": sum(1 for v in all_violations if v.severity == "high"),
        "medium": sum(1 for v in all_violations if v.severity == "medium"),
        "low": sum(1 for v in all_violations if v.severity == "low"),
    }

    status_counts = {
        "detected": sum(1 for v in all_violations if v.status == "detected"),
        "remediated": sum(1 for v in all_violations if v.status == "remediated"),
        "reviewed": sum(1 for v in all_violations if v.status == "reviewed"),
    }

    region_breakdown = {}
    for v in all_violations:
        if v.region not in region_breakdown:
            region_breakdown[v.region] = 0
        region_breakdown[v.region] += 1

    return {
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "total_violations": len(all_violations),
        "violations_by_severity": severity_counts,
        "violations_by_status": status_counts,
        "violations_by_region": region_breakdown,
        "audit_history": len(detector._audit_history) if hasattr(detector, "_audit_history") else 0,
    }
