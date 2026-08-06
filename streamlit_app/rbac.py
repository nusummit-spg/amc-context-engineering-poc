"""
AMC Context Engineering — Enterprise Role-Based Access Control (RBAC) Engine
Defines 5 AMC Organizational Roles, Domain Authorization Scopes, PII Visibility Rules,
and Document/Graph Access Filters.
"""

import os
import json
from enum import Enum
from pathlib import Path
from typing import Dict, List, Set, Any, Optional

class AMCRole(str, Enum):
    COMPLIANCE_OFFICER = "Compliance & Regulatory Officer"  # Level 1 (Full Access)
    FUND_MANAGER       = "Fund Manager / Portfolio Manager"  # Level 2 (Investment Scope)
    ESG_ANALYST        = "ESG & Sustainability Analyst"     # Level 3 (ESG & Climate Scope)
    SALES_MANAGER      = "Sales & Distribution Manager"      # Level 4 (Commercial Scope)
    RETAIL_INVESTOR    = "Retail Investor / Public Client"   # Level 5 (Restricted Public Scope)


# ── Domain Authorization Matrix ─────────────────────────────────────────────
# Specifies which domain intents each role is authorized to access
ROLE_DOMAIN_ACCESS: Dict[AMCRole, Set[str]] = {
    AMCRole.COMPLIANCE_OFFICER: {
        "sebi_regulation", "esg_sustainability", "financial_performance",
        "fund_performance", "corporate_governance"
    },
    AMCRole.FUND_MANAGER: {
        "sebi_regulation", "esg_sustainability", "financial_performance",
        "fund_performance", "corporate_governance"
    },
    AMCRole.ESG_ANALYST: {
        "esg_sustainability", "sebi_regulation", "corporate_governance"
    },
    AMCRole.SALES_MANAGER: {
        "fund_performance", "sebi_regulation", "financial_performance"
    },
    AMCRole.RETAIL_INVESTOR: {
        "fund_performance", "sebi_regulation"
    },
}

# ── Feature & Tool Permission Matrix ────────────────────────────────────────
ROLE_PERMISSIONS: Dict[AMCRole, Dict[str, bool]] = {
    AMCRole.COMPLIANCE_OFFICER: {
        "can_view_admin_panel": True,
        "can_view_audit_logs": True,
        "can_view_unredacted_pii": True,
        "can_run_cypher_tools": True,
        "enforce_sebi_advice_shield": True,
        "can_access_compare_tab": True,
        "can_access_analytics_tab": True,
    },
    AMCRole.FUND_MANAGER: {
        "can_view_admin_panel": False,
        "can_view_audit_logs": False,
        "can_view_unredacted_pii": False,
        "can_run_cypher_tools": True,
        "enforce_sebi_advice_shield": True,
        "can_access_compare_tab": True,
        "can_access_analytics_tab": True,
    },
    AMCRole.ESG_ANALYST: {
        "can_view_admin_panel": False,
        "can_view_audit_logs": False,
        "can_view_unredacted_pii": False,
        "can_run_cypher_tools": False,
        "enforce_sebi_advice_shield": True,
        "can_access_compare_tab": True,
        "can_access_analytics_tab": True,
    },
    AMCRole.SALES_MANAGER: {
        "can_view_admin_panel": False,
        "can_view_audit_logs": False,
        "can_view_unredacted_pii": False,
        "can_run_cypher_tools": False,
        "enforce_sebi_advice_shield": True,
        "can_access_compare_tab": False,
        "can_access_analytics_tab": False,
    },
    AMCRole.RETAIL_INVESTOR: {
        "can_view_admin_panel": False,
        "can_view_audit_logs": False,
        "can_view_unredacted_pii": False,
        "can_run_cypher_tools": False,
        "enforce_sebi_advice_shield": True,
        "can_access_compare_tab": False,
        "can_access_analytics_tab": False,
    },
}


# ── Default User Profiles ───────────────────────────────────────────────────
DEFAULT_USER_PROFILES = [
    {
        "username": "sarah_compliance",
        "full_name": "Sarah Jenkins",
        "role": AMCRole.COMPLIANCE_OFFICER.value,
        "department": "Regulatory & Legal Compliance",
        "email": "s.jenkins@amc.com",
        "status": "Active"
    },
    {
        "username": "vikram_pm",
        "full_name": "Vikram Mehta",
        "role": AMCRole.FUND_MANAGER.value,
        "department": "Equity Investment Management",
        "email": "v.mehta@amc.com",
        "status": "Active"
    },
    {
        "username": "ananya_esg",
        "full_name": "Ananya Sharma",
        "role": AMCRole.ESG_ANALYST.value,
        "department": "Sustainable Investing & ESG",
        "email": "a.sharma@amc.com",
        "status": "Active"
    },
    {
        "username": "rahul_sales",
        "full_name": "Rahul Verma",
        "role": AMCRole.SALES_MANAGER.value,
        "department": "Institutional & Retail Distribution",
        "email": "r.verma@amc.com",
        "status": "Active"
    },
    {
        "username": "public_investor",
        "full_name": "Guest Client / Retail Investor",
        "role": AMCRole.RETAIL_INVESTOR.value,
        "department": "External Client Portal",
        "email": "client@public.com",
        "status": "Active"
    }
]


class RBACManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path(__file__).parent / "config" / "users_rbac.json")
        self.users: List[Dict[str, Any]] = []
        self._load_users()

    def _load_users(self) -> None:
        if not os.path.exists(self.db_path):
            self.users = list(DEFAULT_USER_PROFILES)
            self.save_users()
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                self.users = json.load(f)
        except Exception as exc:
            print(f"  [RBAC Warning] Could not load user store: {exc}", flush=True)
            self.users = list(DEFAULT_USER_PROFILES)

    def save_users(self) -> None:
        try:
            os.makedirs(Path(self.db_path).parent, exist_ok=True)
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2)
        except Exception as exc:
            print(f"  [RBAC Error] Could not save user store: {exc}", flush=True)

    def add_user(self, username: str, full_name: str, role: str, department: str, email: str) -> Dict[str, Any]:
        user = {
            "username": username.strip().lower(),
            "full_name": full_name.strip(),
            "role": role,
            "department": department.strip(),
            "email": email.strip(),
            "status": "Active"
        }
        # Update existing or append new
        self.users = [u for u in self.users if u["username"] != user["username"]]
        self.users.append(user)
        self.save_users()
        return user

    def delete_user(self, username: str) -> None:
        self.users = [u for u in self.users if u["username"] != username]
        self.save_users()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        for u in self.users:
            if u["username"] == username:
                return u
        return None


# Global Singleton Manager
_rbac_instance: Optional[RBACManager] = None

def get_rbac_manager() -> RBACManager:
    global _rbac_instance
    if _rbac_instance is None:
        _rbac_instance = RBACManager()
    return _rbac_instance


def filter_chunks_by_role(hits: List[Dict[str, Any]], role_str: str) -> List[Dict[str, Any]]:
    """Filters vector hits according to the role's clearance level."""
    if not hits:
        return []

    try:
        role = AMCRole(role_str)
    except ValueError:
        role = AMCRole.RETAIL_INVESTOR

    filtered = []
    for h in hits:
        text = h.get("parent_text", "").lower()
        # Restricted confidential internal notes for Sales & Retail roles
        if role in (AMCRole.SALES_MANAGER, AMCRole.RETAIL_INVESTOR):
            if "confidential internal compliance note" in text or "internal audit memo" in text:
                continue
        filtered.append(h)

    return filtered


def filter_graph_by_role(graph_result: Dict[str, Any], role_str: str) -> Dict[str, Any]:
    """Filters Knowledge Graph nodes & edges according to role clearance."""
    if not graph_result or not graph_result.get("edges"):
        return graph_result

    try:
        role = AMCRole(role_str)
    except ValueError:
        role = AMCRole.RETAIL_INVESTOR

    if role == AMCRole.COMPLIANCE_OFFICER:
        return graph_result

    # Mask sensitive internal nodes for restricted roles
    clean_edges = []
    for e in graph_result.get("edges", []):
        s_text = str(e.get("s", "")).lower()
        o_text = str(e.get("o", "")).lower()
        rel = str(e.get("rel", "")).upper()

        if role in (AMCRole.SALES_MANAGER, AMCRole.RETAIL_INVESTOR):
            if "audit" in s_text or "audit" in o_text or "penalty" in rel.lower():
                continue
        clean_edges.append(e)

    nodes = list({e["s"] for e in clean_edges} | {e["o"] for e in clean_edges})
    res_copy = dict(graph_result)
    res_copy["edges"] = clean_edges
    res_copy["nodes"] = nodes
    return res_copy
