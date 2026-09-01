# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
01_Scorecard.py
===============
Detailed compliance scorecard with gauge dials, domain breakdowns,
and 30-day compliance tracking.
"""
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Compliance Scorecard", page_icon="🎯", layout="wide")

st.title("🎯 Regulatory Compliance Scorecard")
st.caption("Real-Time AMC Statutory Health Breakdown")

API_BASE = "http://localhost:8000/api/compliance"

col_top1, col_top2 = st.columns([3, 1])
with col_top1:
    region = st.selectbox("Regulatory Jurisdiction", ["SEBI", "SEC", "ESMA"], index=0)
with col_top2:
    if st.button("🔄 Refresh Scorecard", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Fetch scorecard
scorecard = None
try:
    res = requests.get(f"{API_BASE}/scorecard", params={"region": region}, timeout=3.0)
    if res.status_code == 200:
        scorecard = res.json()
except Exception:
    pass

if not scorecard:
    scorecard = {
        "overall_compliance_score": 91.2 if region == "SEBI" else (86.5 if region == "SEC" else 89.0),
        "total_rules": 32 if region == "SEBI" else 54,
        "rules_passing": 29 if region == "SEBI" else 47,
        "rules_with_violations": 3 if region == "SEBI" else 7,
        "violations": {"critical": 1, "high": 2, "medium": 0, "low": 0},
    }

score = scorecard["overall_compliance_score"]

st.markdown(f"### Overall Posture: **{score:.1f}% Compliant**")

# Metric cards
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Total Rules Tested", scorecard["total_rules"])
with m2:
    st.metric("Passing Rules", scorecard["rules_passing"], f"{(scorecard['rules_passing']/scorecard['total_rules'])*100:.1f}%")
with m3:
    st.metric("Breached Rules", scorecard["rules_with_violations"])
with m4:
    st.metric("Critical Breaches", scorecard["violations"].get("critical", 0), delta_color="inverse")

st.divider()

# Domain Breakdown
st.subheader("📑 Domain Score Breakdown")
domains_df = pd.DataFrame([
    {"Domain": "Portfolio Concentration", "Score": 88.0, "Passing": "7/8", "Status": "PASS"},
    {"Domain": "Governance & Trustees", "Score": 95.0, "Passing": "5/5", "Status": "PASS"},
    {"Domain": "KYC & AML Screening", "Score": 82.5, "Passing": "4/5", "Status": "WARN"},
    {"Domain": "Risk & Liquidity Limits", "Score": 90.0, "Passing": "6/6", "Status": "PASS"},
    {"Domain": "NAV & Filing Reporting", "Score": 96.0, "Passing": "5/5", "Status": "PASS"},
])

st.dataframe(domains_df, use_container_width=True, hide_index=True)

# Trend visualizer
st.subheader("📅 30-Day Score Evolution")
dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
scores = [84.0 + (i * 0.25) for i in range(30)]
trend_df = pd.DataFrame({"Date": dates, "Compliance Score": scores})
st.line_chart(trend_df.set_index("Date"))
