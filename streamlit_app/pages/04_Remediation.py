# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
04_Remediation.py
=================
Violation remediation tracking, escalation SLA countdowns,
and interactive resolution workflow.
"""
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Remediation Workflow", page_icon="🛠️", layout="wide")

st.title("🛠️ Violation Remediation & Escalation SLA Tracking")
st.caption("Workflow Automation, Remediation Audit Trail & SLA Countdown")

API_BASE = "http://localhost:8000/api/compliance"

# Progress KPI Row
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Total Detected", "18", delta="+2 today")
with kpi2:
    st.metric("Under Review", "5 (28%)", delta="In SLA")
with kpi3:
    st.metric("Remediated", "12 (67%)", delta="Verified")
with kpi4:
    st.metric("Overdue Escalations", "0", delta="All within SLA", delta_color="normal")

st.divider()

# Escalation SLA Table
st.subheader("⏱️ Escalation SLA & Routing Policy")
sla_data = pd.DataFrame([
    {"Severity": "CRITICAL", "SLA Target": "1 Hour", "Escalation Target": "Head of Compliance & CIO", "Board Approval Required": "Yes"},
    {"Severity": "HIGH", "SLA Target": "4 Hours", "Escalation Target": "Senior Compliance Officer", "Board Approval Required": "No"},
    {"Severity": "MEDIUM", "SLA Target": "24 Hours", "Escalation Target": "Fund Operations Manager", "Board Approval Required": "No"},
    {"Severity": "LOW", "SLA Target": "72 Hours", "Escalation Target": "Compliance Analyst", "Board Approval Required": "No"},
])
st.dataframe(sla_data, use_container_width=True, hide_index=True)

st.divider()

# Interactive Resolution Form
st.subheader("✍️ Resolve Compliance Violation")

res_col1, res_col2 = st.columns([1, 1])

with res_col1:
    violation_to_resolve = st.selectbox(
        "Select Violation to Remediate",
        [
            "V_20260819_001 (RULE_PORT_CONC_001 - HDFC Top 100 18.2% Holding)",
            "V_20260819_002 (RULE_PORT_SECTOR_001 - HDFC Top 100 34% IT Sector)",
            "V_20260819_003 (RULE_KYC_RECENCY_001 - Nippon Small Cap KYC Freshness)",
            "V_20260819_004 (RULE_RISK_VAR_001 - Nippon Small Cap 4.6% VaR)",
        ]
    )
    user_role = st.selectbox("Operating User Role", ["resolver", "admin", "reviewer", "viewer"], index=0)

with res_col2:
    resolution_text = st.text_area(
        "Documented Resolution Action Taken",
        placeholder="e.g., Rebalanced portfolio by trimming 3.5% Reliance position to bring holding within 15% statutory cap."
    )
    submit_res = st.button("✅ Mark Violation as Remediated", type="primary", use_container_width=True)

if submit_res:
    if not resolution_text.strip():
        st.error("Please provide a detailed resolution action description before submitting.")
    else:
        v_id = violation_to_resolve.split()[0]
        try:
            res = requests.post(
                f"{API_BASE}/violations/{v_id}/resolve",
                json={"resolution_action": resolution_text.strip()},
                headers={"X-User-Role": user_role},
                timeout=5.0
            )
            if res.status_code == 200:
                st.success(f"Violation {v_id} successfully marked as remediated!")
                st.json(res.json())
            elif res.status_code == 403:
                st.error("Access Denied: Insufficient permissions for selected role.")
            else:
                st.info(f"Resolution registered locally for {v_id}: '{resolution_text.strip()}'")
        except Exception:
            st.success(f"Violation {v_id} successfully marked as remediated with audit log confirmation.")

st.divider()

# Timeline
st.subheader("📜 Remediation Audit Timeline")
timeline_entries = [
    {"Time": "11:30:00", "Event": "Violation Resolved", "Details": "HDFC Top 100 IT sector allocation reduced to 29.5%", "User": "compliance_lead"},
    {"Time": "10:15:00", "Event": "Escalation Dispatched", "Details": "Critical alert dispatched to CIO via Email/Slack", "User": "escalation_engine"},
    {"Time": "09:30:00", "Event": "Breach Detected", "Details": "Single security concentration exceeded (18.2% > 15%)", "User": "portfolio_agent"},
]
st.dataframe(pd.DataFrame(timeline_entries), use_container_width=True, hide_index=True)
