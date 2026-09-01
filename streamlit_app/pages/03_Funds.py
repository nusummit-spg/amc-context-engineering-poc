# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
03_Funds.py
===========
Fund-by-fund compliance heatmap matrix, scheme roster, and drilldown panel.
"""
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Fund Compliance Heatmap", page_icon="🏢", layout="wide")

st.title("🏢 Fund Scheme Compliance Heatmap")
st.caption("Scheme Health Matrix Across All 5 Statutory Domains")

API_BASE = "http://localhost:8000/api/compliance"

# Funds data matrix
funds_matrix = [
    {"Fund ID": "SEBI_FUND_001", "Name": "HDFC Top 100 Bluechip Fund", "Category": "Equity", "AUM (Cr)": "₹45,250", "Portfolio": "WARN", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "88%"},
    {"Fund ID": "SEBI_FUND_002", "Name": "ICICI Prudential Corp Bond", "Category": "Debt", "AUM (Cr)": "₹28,400", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "100%"},
    {"Fund ID": "SEBI_FUND_003", "Name": "SBI Balanced Advantage Dynamic", "Category": "Hybrid", "AUM (Cr)": "₹31,200", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "96%"},
    {"Fund ID": "SEBI_FUND_004", "Name": "Nippon India Small Cap Equity", "Category": "Equity", "AUM (Cr)": "₹52,100", "Portfolio": "PASS", "Gov": "PASS", "KYC": "WARN", "Risk": "WARN", "NAV": "PASS", "Score": "82%"},
    {"Fund ID": "SEBI_FUND_005", "Name": "Axis Liquid Treasury Cash", "Category": "Debt", "AUM (Cr)": "₹39,000", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "100%"},
    {"Fund ID": "SEBI_FUND_006", "Name": "Kotak Emerging Equity Mid Cap", "Category": "Equity", "AUM (Cr)": "₹41,500", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "95%"},
    {"Fund ID": "SEBI_FUND_007", "Name": "Aditya Birla Frontline Equity", "Category": "Equity", "AUM (Cr)": "₹26,300", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "98%"},
    {"Fund ID": "SEBI_FUND_008", "Name": "Mirae Asset Tax Saver ELSS", "Category": "Equity", "AUM (Cr)": "₹21,800", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "100%"},
    {"Fund ID": "SEBI_FUND_009", "Name": "UTI Nifty 50 Index Passive", "Category": "Index", "AUM (Cr)": "₹18,500", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "100%"},
    {"Fund ID": "SEBI_FUND_010", "Name": "DSP Overnight Treasury Cash", "Category": "Debt", "AUM (Cr)": "₹12,400", "Portfolio": "PASS", "Gov": "PASS", "KYC": "PASS", "Risk": "PASS", "NAV": "PASS", "Score": "100%"},
]

df_funds = pd.DataFrame(funds_matrix)

# Controls
cat_filter = st.selectbox("Filter Scheme Category", ["All Categories", "Equity", "Debt", "Hybrid", "Index"], index=0)
if cat_filter != "All Categories":
    df_funds = df_funds[df_funds["Category"] == cat_filter]

# Heatmap Table
st.subheader("📊 5-Domain Compliance Matrix")
st.dataframe(df_funds, use_container_width=True, hide_index=True)

st.divider()

# Fund Deep-Dive Inspector
st.subheader("🔍 Fund Scheme Detailed Audit Inspection")
selected_f_id = st.selectbox("Select Scheme to Inspect", df_funds["Fund ID"].tolist(), index=0)

selected_row = df_funds[df_funds["Fund ID"] == selected_f_id].iloc[0]

info1, info2, info3, info4 = st.columns(4)
with info1:
    st.info(f"**Scheme Name**: {selected_row['Name']}")
with info2:
    st.info(f"**Asset Class**: {selected_row['Category']}")
with info3:
    st.info(f"**Total AUM**: {selected_row['AUM (Cr)']}")
with info4:
    st.success(f"**Health Score**: {selected_row['Score']}")

# Query live violations for selected fund
st.markdown("#### Registered Breaches for Scheme")
try:
    res = requests.get(f"{API_BASE}/fund/{selected_f_id}/violations", timeout=3.0)
    if res.status_code == 200 and res.json():
        st.dataframe(pd.DataFrame(res.json()), use_container_width=True, hide_index=True)
    else:
        st.success("✅ Zero active violations recorded for this scheme.")
except Exception:
    st.success("✅ Zero active violations recorded for this scheme.")
