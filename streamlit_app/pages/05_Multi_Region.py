# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
05_Multi_Region.py
==================
Multi-jurisdiction regulatory alignment report and side-by-side comparison
across SEBI (India), SEC (US), and ESMA (EU) compliance standards.
"""
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Multi-Region Regulatory Matrix", page_icon="🌐", layout="wide")

st.title("🌐 Multi-Jurisdiction Regulatory Comparison")
st.caption("Cross-Border Harmonization: SEBI (India) • US SEC (USA) • ESMA (Europe)")

API_BASE = "http://localhost:8000/api/compliance"

# Scorecards comparison row
st.subheader("📊 Regional Scorecards Comparison")
r1, r2, r3 = st.columns(3)

with r1:
    st.markdown("### 🇮🇳 SEBI (India)")
    st.metric("Compliance Score", "91.2%", "+1.5%")
    st.caption("Regulations: 52 Circulars | Rules: 32 Rules")

with r2:
    st.markdown("### 🇺🇸 US SEC (USA)")
    st.metric("Compliance Score", "86.5%", "-0.8%")
    st.caption("Regulations: 105 Items | Rules: 54 Rules")

with r3:
    st.markdown("### 🇪🇺 ESMA (European Union)")
    st.metric("Compliance Score", "89.0%", "+2.1%")
    st.caption("Regulations: 105 Articles | Rules: 54 Rules")

st.divider()

# Statutory Threshold Comparison Matrix
st.subheader("⚖️ Regulatory Threshold Benchmark Matrix")

comparison_table = [
    {
        "Regulatory Area": "Single Holding Concentration Limit",
        "SEBI (India)": "15.0% Maximum",
        "US SEC (USA)": "5.0% Maximum (12d-1)",
        "ESMA (Europe)": "10.0% Maximum (5/10/40 rule)",
        "Strictest Jurisdiction": "US SEC (5.0%)",
    },
    {
        "Regulatory Area": "Sector Concentration Limit",
        "SEBI (India)": "30.0% Maximum",
        "US SEC (USA)": "25.0% Maximum",
        "ESMA (Europe)": "30.0% Maximum",
        "Strictest Jurisdiction": "US SEC (25.0%)",
    },
    {
        "Regulatory Area": "Daily NAV Disclosure Cutoff",
        "SEBI (India)": "21:00 IST (Daily)",
        "US SEC (USA)": "16:00 ET (4:00 PM)",
        "ESMA (Europe)": "Daily Publication",
        "Strictest Jurisdiction": "US SEC / SEBI",
    },
    {
        "Regulatory Area": "Board Independence Mandate",
        "SEBI (India)": "50% Independent Trustees",
        "US SEC (USA)": "40% Independent Directors",
        "ESMA (Europe)": "45% Independent Members",
        "Strictest Jurisdiction": "SEBI (50.0%)",
    },
    {
        "Regulatory Area": "Liquidity Buffer Requirement",
        "SEBI (India)": "5.0% Liquid Cash Buffer",
        "US SEC (USA)": "15.0% Highly Liquid Assets",
        "ESMA (Europe)": "80% Tradable in 5 Days",
        "Strictest Jurisdiction": "ESMA (80% 5-Day)",
    },
    {
        "Regulatory Area": "ESG / Sustainability Disclosures",
        "SEBI (India)": "BRSR Framework (Top 1000)",
        "US SEC (USA)": "Climate Risk Proposed Rules",
        "ESMA (Europe)": "SFDR Article 8/9 Mandatory",
        "Strictest Jurisdiction": "ESMA (SFDR Mandatory)",
    },
]

st.dataframe(pd.DataFrame(comparison_table), use_container_width=True, hide_index=True)

st.divider()

# Cross-Border Global Audit Simulation
st.subheader("🌍 Run Global Multi-Jurisdiction Audit")
st.write("Simulate audit of a fund scheme evaluated simultaneously against all 3 regulatory regimes.")

g_col1, g_col2 = st.columns([3, 1])
with g_col1:
    global_fund = st.selectbox("Select Global Scheme", ["GLOBAL_EQUITY_001 (Cross-Border Global Opportunity Fund)"])
with g_col2:
    st.write("")
    st.write("")
    run_global = st.button("🚀 Audit All 3 Jurisdictions", type="primary", use_container_width=True)

if run_global:
    with st.spinner("Evaluating SEBI, SEC, and ESMA rule sets simultaneously..."):
        st.success("Global Audit Completed! Evaluated 140 rules across 3 jurisdictions in 48ms.")
        global_results = {
            "fund_id": "GLOBAL_EQUITY_001",
            "jurisdictions_evaluated": ["SEBI", "SEC", "ESMA"],
            "total_rules_evaluated": 140,
            "overall_harmonized_score": "88.2%",
            "regional_findings": {
                "SEBI": {"status": "COMPLIANT", "breaches": 0},
                "SEC": {"status": "NON_COMPLIANT", "breaches": 1, "detail": "Single holding 8.5% exceeds 5.0% SEC limit"},
                "ESMA": {"status": "COMPLIANT", "breaches": 0, "detail": "Complies with 10% UCITS cap"},
            }
        }
        st.json(global_results)
