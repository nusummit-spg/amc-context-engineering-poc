# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Phase 5 — Evaluation Benchmark Dataset: 25 Ground-Truth AMC Q&A Pairs.

Covers all 4 document tiers:
  - SEBI Master Circulars (Tier 1)
  - High-Value SEBI Circulars (Tier 2)
  - Adani Corporate Intelligence (Tier 3)
  - AMC Fund House SIDs (Tier 4)
"""
from typing import Any

EVALUATION_DATASET: list[dict[str, Any]] = [
    # --- Tier 1: SEBI Master Circulars (6 Qs) ---
    {
        "id": "Q01",
        "category": "sebi_master_circular",
        "query": "What are the five broad categories of mutual fund schemes under SEBI's categorization framework?",
        "ground_truth": "The five broad categories are Equity Schemes, Debt Schemes, Hybrid Schemes, Solution Oriented Schemes, and Other Schemes.",
    },
    {
        "id": "Q02",
        "category": "sebi_master_circular",
        "query": "What is the maximum investment limit for a mutual fund scheme in a single issuer's debt securities?",
        "ground_truth": "A mutual fund scheme shall not invest more than 10% of its NAV in debt instruments issued by a single issuer, extendable to 12% with prior approval of trustees.",
    },
    {
        "id": "Q03",
        "category": "sebi_master_circular",
        "query": "What guidelines govern Anti-Money Laundering (AML) standards for Asset Management Companies under PMLA?",
        "ground_truth": "AMCs must implement Client Due Diligence (CDD), appoint a Principal Officer and Designated Director, maintain transaction records for 5 years, and file STR/CTR reports with Financial Intelligence Unit-India (FIU-IND).",
    },
    {
        "id": "Q04",
        "category": "sebi_master_circular",
        "query": "What are the eligibility criteria and registration requirements for Portfolio Managers under SEBI regulations?",
        "ground_truth": "Portfolio Managers require a minimum net worth of ₹5 Crore, qualified principal officer with professional experience, and compliance officer.",
    },
    {
        "id": "Q05",
        "category": "sebi_master_circular",
        "query": "What is the minimum capital requirement for establishing an Alternative Investment Fund (AIF) Manager?",
        "ground_truth": "Category I and II AIFs require a minimum fund corpus of ₹20 Crore, while Angel Funds require ₹10 Crore.",
    },
    {
        "id": "Q06",
        "category": "sebi_master_circular",
        "query": "What are the key governance obligations for ESG Rating Providers (ERPs) under SEBI master circulars?",
        "ground_truth": "ERPs must maintain independence, disclose rating methodologies publicly, manage conflict of interest, and undergo periodic SEBI audits.",
    },

    # --- Tier 2: SEBI Circulars (6 Qs) ---
    {
        "id": "Q07",
        "category": "sebi_circular",
        "query": "What change did the September 2020 SEBI circular make to the Multi Cap Fund mandate?",
        "ground_truth": "Multi Cap Funds must invest a minimum of 75% in total equity, with at least 25% each in Large Cap, Mid Cap, and Small Cap stocks.",
    },
    {
        "id": "Q08",
        "category": "sebi_circular",
        "query": "What is a Specialized Investment Fund (SIF) under SEBI's 2024 regulatory framework?",
        "ground_truth": "SIF is a new investment vehicle for accredited investors with higher minimum investment thresholds (₹10 Lakh per investor) allowing flexible long-short strategies.",
    },
    {
        "id": "Q09",
        "category": "sebi_circular",
        "query": "What are the rebalancing timelines for mutual fund scheme portfolios in case of passive breaches?",
        "ground_truth": "AMCs must rebalance passive breaches within 30 business days. If not rebalanced, the investment committee must be notified and no new investments in the scheme allowed.",
    },
    {
        "id": "Q10",
        "category": "sebi_circular",
        "query": "What is the voluntary lock-in or debit freeze facility introduced for Mutual Fund folios?",
        "ground_truth": "Investors can voluntarily freeze/lock their mutual fund folios online or offline to prevent unauthorized redemption or transfer transactions during security concerns.",
    },
    {
        "id": "Q11",
        "category": "sebi_circular",
        "query": "What rules govern the reclassification of REITs as equity-related instruments for mutual funds?",
        "ground_truth": "REIT units held by mutual funds are categorized as equity-related instruments, permitting higher scheme allocation up to 10% NAV in single REIT/InvIT.",
    },
    {
        "id": "Q12",
        "category": "sebi_circular",
        "query": "What are the rules regarding transaction charges paid to Mutual Fund Distributors on investments?",
        "ground_truth": "Distributors get ₹150 for first-time mutual fund investors and ₹100 for existing investors for subscriptions of ₹10,000 and above, while no charges apply for direct plans.",
    },

    # --- Tier 3: Adani Corporate Intelligence (7 Qs) ---
    {
        "id": "Q13",
        "category": "adani_corporate",
        "query": "What was Adani Enterprises Ltd (AEL) Consolidated EBITDA and Revenue in FY24?",
        "ground_truth": "In FY24, AEL reported Consolidated Revenue of ₹96,421 Crore and Consolidated EBITDA of ₹13,237 Crore.",
    },
    {
        "id": "Q14",
        "category": "adani_corporate",
        "query": "What are the key ESG and decarbonization targets highlighted in Adani Portfolio H1FY25 ESG report?",
        "ground_truth": "Targets include achieving net-zero emissions for airports by 2030, installing 45 GW renewable capacity by 2030 at Khavda, and planting over 25 million trees.",
    },
    {
        "id": "Q15",
        "category": "adani_corporate",
        "query": "What credit rating updates were issued for Adani Portfolio entities in H1FY25?",
        "ground_truth": "Major portfolio companies maintained AA- to AAA stable credit ratings across domestic rating agencies (CRISIL, ICRA, CARE).",
    },
    {
        "id": "Q16",
        "category": "adani_corporate",
        "query": "What were the key takeaways from AEL Q4 FY25 earnings call regarding airport and green hydrogen capital expenditure?",
        "ground_truth": "Management highlighted milestone expansion at Navi Mumbai International Airport and commencement of ANIL green hydrogen ingot/wafer manufacturing facilities.",
    },
    {
        "id": "Q17",
        "category": "adani_corporate",
        "query": "How did Adani Enterprises perform financially in FY25 compared to FY24?",
        "ground_truth": "FY25 demonstrated double-digit EBITDA growth driven by incubational businesses (airports, roads, new industries ecosystem).",
    },
    {
        "id": "Q18",
        "category": "adani_corporate",
        "query": "What is the total debt and leverage ratio across the Adani Portfolio in H1FY25?",
        "ground_truth": "Run-rate EBITDA to Net Debt ratio improved to ~2.2x, demonstrating strong cash generation and debt coverage.",
    },
    {
        "id": "Q19",
        "category": "adani_corporate",
        "query": "What sustainability initiatives are detailed in the Adani June 2025 ESG deck?",
        "ground_truth": "Focuses on water positivity, single-use plastic reduction, zero waste to landfill certification, and safety leadership framework.",
    },

    # --- Tier 4: AMC Fund House SIDs (6 Qs) ---
    {
        "id": "Q20",
        "category": "fund_performance",
        "query": "What is the investment objective and exit load structure of HDFC Banking & Financial Services Fund?",
        "ground_truth": "The scheme aims to generate long-term capital appreciation by investing in banking and financial services sector companies. Exit load is 1% if redeemed within 1 year.",
    },
    {
        "id": "Q21",
        "category": "fund_performance",
        "query": "What is the asset allocation mandate of SBI Equity Hybrid Fund between equity and debt?",
        "ground_truth": "SBI Equity Hybrid Fund invests 65%-80% in equity & equity-related instruments and 20%-35% in debt & money market securities.",
    },
    {
        "id": "Q22",
        "category": "fund_performance",
        "query": "What is the lock-in period and asset allocation strategy of Axis Aggressive Hybrid Fund?",
        "ground_truth": "Axis Aggressive Hybrid Fund has no lock-in period (unlike ELSS) and maintains 65-80% equity allocation alongside active debt management.",
    },
    {
        "id": "Q23",
        "category": "fund_performance",
        "query": "What benchmark index does Tata Banking & Financial Services Fund track?",
        "ground_truth": "The scheme tracks NIFTY Financial Services TRI (Total Return Index) as its primary benchmark.",
    },
    {
        "id": "Q24",
        "category": "fund_performance",
        "query": "What is the expense ratio (TER) and scheme classification of Groww Aggressive Hybrid Fund?",
        "ground_truth": "Groww Aggressive Hybrid Fund is an open-ended hybrid scheme maintaining competitive Total Expense Ratio under SEBI regulatory limits.",
    },
    {
        "id": "Q25",
        "category": "fund_performance",
        "query": "How do lock-in terms compare across ELSS, Retirement Funds, and Children's Funds?",
        "ground_truth": "ELSS requires 3-year statutory lock-in; Retirement Funds have 5-year or retirement age lock-in; Children's Funds have 5-year or adulthood (18 yrs) lock-in.",
    },
]
