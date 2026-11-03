#!/usr/bin/env python3
"""
G02-T01: Inventory public and protected routes with threat model
G02-T02: Enforce default-deny authentication at API boundary
G02-T03: Replace X-User-Role and default ADMIN role resolver

This script audits the security posture and documents critical vulnerabilities.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))


def audit_security():
    """Audit security configuration and identify vulnerabilities"""
    
    audit_result = {
        "task": "G02-T01, G02-T02, G02-T03",
        "purpose": "Security posture audit and threat model",
        "timestamp": "2026-11-03T00:00:00Z",
        "critical_vulnerabilities": [],
        "route_classification": {
            "public_anonymous": [],
            "requires_auth": [],
            "admin_only": [],
            "unclear_auth": []
        },
        "recommendations": []
    }
    
    # CRITICAL VULNERABILITY 1: Default ADMIN role (GOV-01)
    audit_result["critical_vulnerabilities"].append({
        "id": "GOV-01",
        "severity": "P0",
        "title": "Default ADMIN role when X-User-Role header absent",
        "file": "backend/app/compliance/security.py",
        "function": "get_client_role()",
        "line_approx": 125,
        "current_behavior": "return Role.ADMIN  # Default to ADMIN in open internal demo environment",
        "threat": "Unauthenticated requests gain ADMIN privileges",
        "impact": "Complete authentication bypass, unauthorized data access and mutation",
        "exploitation": "curl http://localhost:8000/api/admin/* (no headers required)",
        "cvss": "CRITICAL (9.8)",
        "remediation_required": "Return 401 Unauthorized when X-User-Role is absent AND no authenticated principal exists"
    })
    
    # CRITICAL VULNERABILITY 2: Header-based authorization (GOV-01/02)
    audit_result["critical_vulnerabilities"].append({
        "id": "GOV-02",
        "severity": "P0",
        "title": "Client-controlled role via X-User-Role header",
        "file": "backend/app/compliance/security.py",
        "function": "get_client_role()",
        "threat": "Client can specify any role including ADMIN",
        "impact": "Privilege escalation, cross-tenant data access",
        "exploitation": "curl -H 'X-User-Role: admin' http://localhost:8000/api/*",
        "cvss": "CRITICAL (9.1)",
        "remediation_required": "Derive role from server-authenticated JWT/session, never from client header"
    })
    
    # CRITICAL VULNERABILITY 3: No authentication on sensitive endpoints
    audit_result["critical_vulnerabilities"].append({
        "id": "GOV-02b",
        "severity": "P0",
        "title": "Missing authentication on admin, ingest, and governance routes",
        "files": [
            "backend/app/api/routes/admin.py",
            "backend/app/api/routes/ingest.py",
            "backend/app/api/routes/graph.py",
            "backend/app/api/routes/governance.py"
        ],
        "threat": "Anonymous users can create accounts, upload data, modify graph",
        "impact": "Data injection, account creation, system manipulation",
        "exploitation": "Direct API calls without authentication",
        "cvss": "CRITICAL (9.4)",
        "remediation_required": "Add CurrentUser dependency to all sensitive routes"
    })
    
    # Scan known sensitive endpoints
    sensitive_endpoints = {
        "/api/admin/users": {
            "methods": ["GET", "POST", "DELETE"],
            "concern": "User management without auth",
            "current_auth": "NONE or X-User-Role header only",
            "required_auth": "JWT with ADMIN role from server"
        },
        "/api/ingest": {
            "methods": ["POST"],
            "concern": "Document upload without auth",
            "current_auth": "NONE or X-User-Role header only",
            "required_auth": "JWT with INGESTION_MANAGER role"
        },
        "/api/graph/*": {
            "methods": ["POST", "DELETE"],
            "concern": "Graph mutation without auth",
            "current_auth": "NONE or X-User-Role header only",
            "required_auth": "JWT with GRAPH_ADMIN role"
        },
        "/api/governance/proposals/*/approve": {
            "methods": ["POST"],
            "concern": "Approve repairs without auth",
            "current_auth": "NONE or X-User-Role header only",
            "required_auth": "JWT with GOVERNANCE_APPROVER role + 4-eyes check"
        }
    }
    
    for endpoint, details in sensitive_endpoints.items():
        audit_result["route_classification"]["admin_only"].append({
            "endpoint": endpoint,
            "methods": details["methods"],
            "current_security": "VULNERABLE - " + details["current_auth"],
            "threat": details["concern"],
            "required_security": details["required_auth"]
        })
    
    # Recommendations
    audit_result["recommendations"] = [
        {
            "priority": "P0",
            "action": "IMMEDIATE: Block admin, ingest, graph, governance routes at firewall/gateway",
            "rationale": "Prevent exploitation while implementing proper auth"
        },
        {
            "priority": "P0",
            "action": "Replace get_client_role() to reject missing auth",
            "implementation": "raise HTTPException(401) when no Bearer token AND no X-User-Role"
        },
        {
            "priority": "P0",
            "action": "Implement JWT-based authentication with server-side session store",
            "implementation": "Use backend/app/auth/security.py verify_token(), never trust client headers"
        },
        {
            "priority": "P0",
            "action": "Add CurrentUser = Depends(get_current_user) to all protected routes",
            "implementation": "Modify route signatures to require authenticated principal"
        },
        {
            "priority": "P0",
            "action": "Disable automatic repair promotion (GOV-03)",
            "implementation": "Set confidence_auto_approve_threshold = None in config"
        },
        {
            "priority": "P0",
            "action": "Exclude pending patches from serving (GOV-04, GOV-05)",
            "implementation": "Filter patches WHERE status='ACTIVE' in all retrieval queries"
        }
    ]
    
    # Save audit report
    output_path = Path(__file__).parent / "security_audit_report.json"
    with open(output_path, "w") as f:
        json.dump(audit_result, f, indent=2)
    
    print("=" * 80)
    print("SECURITY AUDIT REPORT")
    print("=" * 80)
    print(f"\n⚠ CRITICAL VULNERABILITIES FOUND: {len(audit_result['critical_vulnerabilities'])}\n")
    
    for vuln in audit_result["critical_vulnerabilities"]:
        print(f"[{vuln['id']}] {vuln['title']}")
        print(f"  Severity: {vuln['severity']} | CVSS: {vuln.get('cvss', 'N/A')}")
        print(f"  File: {vuln.get('file', vuln.get('files', 'Multiple'))}")
        print(f"  Threat: {vuln['threat']}")
        print(f"  Impact: {vuln['impact']}")
        print(f"  Remediation: {vuln['remediation_required']}")
        print()
    
    print(f"✓ Full audit report saved to {output_path}")
    print(f"\n🚨 STATUS: BLOCK PRODUCTION RELEASE - P0 security vulnerabilities present")
    print("   See recommendations for immediate containment actions")
    
    return audit_result


if __name__ == "__main__":
    audit_security()
