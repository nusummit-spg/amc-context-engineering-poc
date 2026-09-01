# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
02_Violations.py
================
Detailed violation explorer, filtering by severity and domain,
leaderboard of most breached rules, and CSV export.
"""
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Compliance Violations", page_icon="⚠️", layout="wide")

st.title("⚠️ Compliance Violations Explorer")
st.caption("Active Regulatory Breaches, Rule Metrics & Resolution Tracking")

API_BASE = "http://localhost:8000/api/compliance"

# Filters bar
with st.expander("🔍 Filter Criteria", expanded=True):
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    with f_col1:
        region = st.selectbox("Region", ["SEBI", "SEC", "ESMA"], index=0)
    with f_col2:
        severity = st.multiselect("Severity", ["critical", "high", "medium", "low"], default=["critical", "high"])
    with f_col3:
        status = st.selectbox("Status", ["all", "detected", "reviewed", "remediated"], index=1)
    with f_col4:
        search_kw = st.text_input("Keyword Search", "")

# Fetch violations
violations = []
try:
    params = {"region": region}
    if status != "all":
        params["status"] = status
    res = requests.get(f"{API_BASE}/violations", params=params, timeout=3.0)
    if res.status_code == 200:
        violations = res.json()
except Exception:
    pass

if not violations:
    # Seed representative sample for demonstration
    violations = [
        {
            "violation_id": "V_20260819_001",
            "rule_id": "RULE_PORT_CONC_001",
            "fund_id": "SEBI_FUND_001",
            "severity": "critical",
            "confidence": 0.98,
            "actual_value": "18.2%",
            "threshold_value": "15.0%",
            "description": "Single Holding Concentration breached: Reliance Industries allocation is 18.2%",
            "detected_at": "2026-08-19 09:30:00",
            "status": "detected",
            "region": region,
        },
        {
            "violation_id": "V_20260819_002",
            "rule_id": "RULE_PORT_SECTOR_001",
            "fund_id": "SEBI_FUND_001",
            "severity": "high",
            "confidence": 0.92,
            "actual_value": "34.0%",
            "threshold_value": "30.0%",
            "description": "Sector Limit breached: Information Technology sector exposure is 34.0%",
            "detected_at": "2026-08-19 09:30:00",
            "status": "detected",
            "region": region,
        },
        {
            "violation_id": "V_20260819_003",
            "rule_id": "RULE_KYC_RECENCY_001",
            "fund_id": "SEBI_FUND_004",
            "severity": "high",
            "confidence": 0.90,
            "actual_value": "410 days",
            "threshold_value": "365 days",
            "description": "KYC Freshness breached: 42 investor records exceed 365-day review cycle",
            "detected_at": "2026-08-19 10:15:00",
            "status": "detected",
            "region": region,
        },
        {
            "violation_id": "V_20260819_004",
            "rule_id": "RULE_RISK_VAR_001",
            "fund_id": "SEBI_FUND_004",
            "severity": "high",
            "confidence": 0.95,
            "actual_value": "4.6%",
            "threshold_value": "4.0%",
            "description": "Daily 99% VaR exceeded: Current 1-day simulated VaR is 4.6%",
            "detected_at": "2026-08-19 11:00:00",
            "status": "detected",
            "region": region,
        },
    ]

# Apply in-memory severity filter
if severity:
    violations = [v for v in violations if v.get("severity") in severity]

# Apply keyword filter
if search_kw:
    kw = search_kw.lower()
    violations = [
        v for v in violations
        if kw in v.get("description", "").lower() or kw in v.get("rule_id", "").lower() or kw in v.get("fund_id", "").lower()
    ]

# Visual summaries
v_col1, v_col2 = st.columns([1, 2])

with v_col1:
    st.subheader("Severity Breakdown")
    sev_counts = pd.Series([v["severity"] for v in violations]).value_counts()
    st.bar_chart(sev_counts)

with v_col2:
    st.subheader("🏆 Top Violated Rules Leaderboard")
    top_rules = pd.Series([v["rule_id"] for v in violations]).value_counts().reset_index()
    top_rules.columns = ["Rule ID", "Breach Count"]
    st.dataframe(top_rules, use_container_width=True, hide_index=True)

st.divider()

# Violations Table
st.subheader(f"📋 Violations Register ({len(violations)} records)")

df_v = pd.DataFrame(violations)
if not df_v.empty:
    display_cols = ["violation_id", "rule_id", "fund_id", "severity", "actual_value", "threshold_value", "description", "status"]
    present_cols = [c for c in display_cols if c in df_v.columns]
    st.dataframe(df_v[present_cols], use_container_width=True, hide_index=True)

    # CSV export
    csv_data = df_v.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Violations to CSV",
        data=csv_data,
        file_name=f"compliance_violations_{region}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
else:
    st.success("✅ No violations match the selected filter criteria.")
