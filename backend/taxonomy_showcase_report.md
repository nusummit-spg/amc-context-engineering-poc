# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Taxonomy RAG Showcase Report

## Executive Summary

| Metric | Traditional RAG | Hybrid RAG |
|:---|:---|:---|
| Avg Input Tokens | 817 | 750 |
| Avg Token Savings | — | **9.9%** |
| Total Graph Edges Used | 0 | **28** |
| Factual Answer Rate | 10/10 | 10/10 |

---

## Turn-by-Turn Breakdown

### Turn 1
**Query:** What are the five broad categories of mutual fund schemes under SEBI's categorization framework, and which specific SEBI circular established these categories?

#### Traditional RAG
- Input Tokens: `872` | Output Tokens: `234` | Latency: `29279.4ms`
- Sources: `CIRCULAR_PRIMARY, HYB_ARBITRAGE, HYB_MULTI_ASSET`
```
Based on the provided context, I cannot provide a complete answer to this question.

The context provided contains detailed information about **Hybrid Schemes** (specifically Arbitrage Fund, Multi Asset Allocation Fund, Conservative Hybrid Fund, and Equity Savings Fund), and references **SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2017/114** titled "Categorization and Rationalization of Mutual Fund Schemes" dated 2017-10-06 as the regulatory basis.

However, the context does not explicitly list the **five broad categories** of mutual fund schemes under SEBI's categorization framework. While the circul...
```

#### Hybrid RAG
- Input Tokens: `872` | Output Tokens: `406` | Latency: `6173.8ms`
- Graph Edges Used: `2` | Nodes Matched: `0` | **Token Savings: `0.0%`**
```
# Five Broad Categories of Mutual Fund Schemes Under SEBI's Categorization Framework

Based on the available **Graph Knowledge and Vector Context**, I can confirm that:

## Regulatory Foundation
The **SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2017/114** titled *"Categorization and Rationalization of Mutual Fund Schemes"* (dated **2017-10-06**) established the categorization framework for mutual fund schemes.

## Broad Categories
The framework establishes the following **five broad categories**:

1. **Equity Schemes** (including Large Cap, Mid Cap, Small Cap, Multi Cap, Flexi Cap, Sectoral/Thematic, ...
```

---

### Turn 2
**Query:** Within equity schemes, compare the minimum equity allocation required for Large Cap Fund, Mid Cap Fund, and Small Cap Fund. Which one is most restrictive in terms of market cap?

#### Traditional RAG
- Input Tokens: `674` | Output Tokens: `213` | Latency: `2700.6ms`
- Sources: `EQ_LARGE_MID_CAP, SECTION_I_SUMMARY, EQ_MID_CAP`
```
# Comparison of Minimum Equity Allocation Requirements

Based on the provided context, here are the minimum equity allocation requirements for each fund type:

| Fund Type | Minimum Equity Allocation | Market Cap Tier |
|-----------|--------------------------|-----------------|
| **Large Cap Fund** | 80% in large cap companies | Large Cap |
| **Mid Cap Fund** | 65% in mid cap companies | Mid Cap |
| **Small Cap Fund** | 65% in small cap companies | Small Cap |

## Most Restrictive Fund

**Large Cap Fund is the most restrictive** in terms of market cap concentration. It requires a **minimum of ...
```

#### Hybrid RAG
- Input Tokens: `479` | Output Tokens: `315` | Latency: `6889.0ms`
- Graph Edges Used: `0` | Nodes Matched: `0` | **Token Savings: `28.9%`**
```
# Comparison of Minimum Equity Allocation Requirements

Based on the available information, I can provide a partial answer:

## Known Allocations:

| Fund Category | Minimum Equity Allocation | Market Cap Focus |
|---|---|---|
| **Mid Cap Fund** | Minimum 65% in mid cap equities | Mid Cap |
| **Large & Mid Cap Fund** | Minimum 35% in large cap + Minimum 35% in mid cap | Large & Mid Cap |

## Known Information:
- **Mid Cap Fund** has the most restrictive allocation mandate at **65% minimum** in a single market cap tier (mid cap only)
- **Large & Mid Cap Fund** requires dual allocations but with...
```

---

### Turn 3
**Query:** Following from the equity scheme categories — which equity fund type was introduced by a SEBI amendment in September 2020, and what change did that same circular make to the Multi Cap Fund mandate?

#### Traditional RAG
- Input Tokens: `938` | Output Tokens: `228` | Latency: `2896.4ms`
- Sources: `CIRCULAR_PRIMARY, HYB_EQUITY_SAVINGS, EQ_DIVIDEND_YIELD`
```
Based on the provided context:

**Flexi Cap Fund** was the equity fund type introduced by a SEBI amendment in September 2020 (via SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2020/175 dated 2020-09-11).

The same circular made the following change to the Multi Cap Fund mandate: It **converted some Multi Cap Fund mandates** (as stated in the amendment summary). Additionally, a prior circular from 2020-02-06 (SEBI/HO/IMD/DF3/CIR/P/2020/26) had tightened the Multi Cap Fund mandate to require a **minimum of 25% each in large cap, mid cap, and small cap stocks**.

The introduction of the Flexi Cap Fund, whi...
```

#### Hybrid RAG
- Input Tokens: `895` | Output Tokens: `278` | Latency: `5198.1ms`
- Graph Edges Used: `2` | Nodes Matched: `0` | **Token Savings: `4.6%`**
```
# Answer

Based on the Graph Knowledge provided:

**Equity Fund Type Introduced (September 2020):**
The **Flexi Cap Fund** was introduced as a new equity category by SEBI amendment SEBI/HO/IMD/DF3/CIR/P/2020/175 dated 2020-09-11.

**Change to Multi Cap Fund Mandate:**
The same amendment circular converted some Multi Cap Fund mandates to Flexi Cap Funds. However, the specific tightening of the Multi Cap Fund mandate—requiring a **minimum of 25% each in large-cap, mid-cap, and small-cap stocks**—was implemented separately by an earlier amendment, SEBI/HO/IMD/DF3/CIR/P/2020/26, dated 2020-02-06.
...
```

---

### Turn 4
**Query:** Can a single AMC simultaneously offer both a Value Fund and a Contra Fund? What about offering both a Balanced Hybrid Fund and an Aggressive Hybrid Fund? What SEBI rules govern these restrictions?

#### Traditional RAG
- Input Tokens: `868` | Output Tokens: `331` | Latency: `3124.5ms`
- Sources: `MUTUAL_EXCLUSIONS, HYB_BALANCED, HYB_AGGRESSIVE`
```
# SEBI Mutual Exclusion Rules for AMCs

## Value Fund and Contra Fund

**No**, a single AMC cannot simultaneously offer both a Value Fund (EQ_VALUE) and a Contra Fund (EQ_CONTRA).

**SEBI Rule:** An AMC may offer either a Value Fund or a Contra Fund, not both simultaneously.

**Regulatory Basis:** SEBI/HO/IMD/DF3/CIR/P/2017/114 — Categorization and Rationalization of Mutual Fund Schemes

---

## Balanced Hybrid Fund and Aggressive Hybrid Fund

**No**, a single AMC cannot simultaneously offer both a Balanced Hybrid Fund (HYB_BALANCED) and an Aggressive Hybrid Fund (HYB_AGGRESSIVE).

**SEBI Rule...
```

#### Hybrid RAG
- Input Tokens: `866` | Output Tokens: `420` | Latency: `6021.2ms`
- Graph Edges Used: `2` | Nodes Matched: `0` | **Token Savings: `0.2%`**
```
# SEBI Restrictions on Simultaneous Scheme Offerings

## Value Fund and Contra Fund

**No.** A single AMC **cannot simultaneously offer both a Value Fund and a Contra Fund.**

**Governing Rule:** SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2017/114 — *Categorization and Rationalization of Mutual Fund Schemes* establishes a mutual exclusion rule between these two equity categories. An AMC must choose to offer either a Value Fund (EQ_VALUE) **or** a Contra Fund (EQ_CONTRA), but not both.

---

## Balanced Hybrid Fund and Aggressive Hybrid Fund

**No.** A single AMC **cannot simultaneously offer both a B...
```

---

### Turn 5
**Query:** List all debt fund categories from shortest to longest Macaulay duration, along with their exact duration bands. Include the Overnight Fund at one end and the Gilt Fund with 10 Year Constant Duration at the other.

#### Traditional RAG
- Input Tokens: `835` | Output Tokens: `220` | Latency: `2235.7ms`
- Sources: `DEBT_GILT_10Y, DEBT_ULTRA_SHORT, DEBT_SHORT_DURATION`
```
Based on the provided context, I can list the debt fund categories with their Macaulay duration bands from shortest to longest:

1. **Ultra Short Duration Fund** (Code: DEBT_ULTRA_SHORT) — 3-6 Months
2. **Low Duration Fund** (Code: DEBT_LOW_DURATION) — 6-12 Months
3. **Short Duration Fund** (Code: DEBT_SHORT_DURATION) — 1-3 Years
4. **Long Duration Fund** (Code: DEBT_LONG_DURATION) — >7 Years
5. **Gilt Fund with 10 Year Constant Duration** (Code: DEBT_GILT_10Y) — Constant 10 Year

**Note:** The Overnight Fund is not included in the provided context, so it cannot be listed as requested. Only th...
```

#### Hybrid RAG
- Input Tokens: `869` | Output Tokens: `475` | Latency: `5554.8ms`
- Graph Edges Used: `15` | Nodes Matched: `0` | **Token Savings: `-4.1%`**
```
# Debt Fund Categories by Macaulay Duration (Shortest to Longest)

Based on SEBI Mutual Fund Regulations, here is the complete list ordered from shortest to longest Macaulay duration:

| Rank | Fund Category | Macaulay Duration Band |
|------|---------------|----------------------|
| 1 | **Overnight Fund** | 1 Day |
| 2 | **Money Market Fund** | Up to 1 Year |
| 3 | **Ultra Short Duration Fund** | 3-6 Months |
| 4 | **Low Duration Fund** | 6-12 Months |
| 5 | **Short Duration Fund** | 1-3 Years |
| 6 | **Medium Duration Fund** | 3-4 Years |
| 7 | **Medium to Long Duration Fund** | 4-7 Years |
...
```

---

### Turn 6
**Query:** What credit quality mandate separates a Corporate Bond Fund from a Credit Risk Fund? Which of these two is safer for a conservative investor and why?

#### Traditional RAG
- Input Tokens: `774` | Output Tokens: `210` | Latency: `2673.5ms`
- Sources: `DEBT_CREDIT_RISK, DEBT_CORPORATE_BOND, DEBT_GILT`
```
## Credit Quality Mandate Differences

**Corporate Bond Fund:**
- Credit Quality Mandate: **AA+ and above**
- Minimum 80% investment in corporate bonds rated AA+ and above

**Credit Risk Fund:**
- Credit Quality Mandate: **AA and below** (excluding AA+ rated instruments)
- Minimum 65% investment in corporate bonds rated AA and below

## Which is Safer for a Conservative Investor?

**Corporate Bond Fund is safer for a conservative investor.**

**Reason:**
A Corporate Bond Fund invests in higher-rated securities (AA+ and above), which represent companies with stronger credit quality and lower de...
```

#### Hybrid RAG
- Input Tokens: `533` | Output Tokens: `352` | Latency: `6544.8ms`
- Graph Edges Used: `0` | Nodes Matched: `0` | **Token Savings: `31.1%`**
```
# Credit Quality Mandate Comparison

## Key Distinction

Based on SEBI regulatory classifications:

| Scheme Type | Credit Quality Mandate |
|---|---|
| **Corporate Bond Fund** | AA+ and above |
| **Credit Risk Fund** | AA and below (excluding AA+) |

The **critical separator** is the inclusion of AA+ rated instruments:
- Corporate Bond Funds: **Required** to invest minimum 80% in AA+ and above
- Credit Risk Funds: **Explicitly exclude** AA+ rated instruments; focus on AA and below

## Safety Assessment for Conservative Investors

**Corporate Bond Fund is safer for conservative investors.**

#...
```

---

### Turn 7
**Query:** Compare the lock-in conditions across the three scheme types that have a mandatory lock-in: ELSS, Retirement Fund, and Children's Fund. What are the exact lock-in terms for each?

#### Traditional RAG
- Input Tokens: `591` | Output Tokens: `162` | Latency: `2235.1ms`
- Sources: `SECTION_IV_SUMMARY, SECTION_I_SUMMARY, SOL_CHILDRENS`
```
# Lock-in Conditions Comparison

Based on the provided context, here is the lock-in information available:

## Children's Fund
**Lock-in Requirement:** 5 Years or Child Majority (whichever is earlier)

## ELSS (Equity Linked Savings Scheme)
**Lock-in Requirement:** Not specified in the provided context

## Retirement Fund
**Lock-in Requirement:** Not specified in the provided context

---

**Note:** The context provided contains complete lock-in details only for Children's Fund. While ELSS and Retirement Fund are identified as scheme categories in the document, their specific lock-in terms are...
```

#### Hybrid RAG
- Input Tokens: `478` | Output Tokens: `412` | Latency: `6002.9ms`
- Graph Edges Used: `3` | Nodes Matched: `3` | **Token Savings: `19.1%`**
```
# Lock-in Conditions Comparison: ELSS, Retirement Fund, and Children's Fund

Based on SEBI Mutual Fund Regulations, here are the exact lock-in terms for the three scheme types with mandatory lock-in:

## 1. **ELSS (Equity Linked Savings Scheme)**
- **Lock-in Period:** 3 Years
- **Section:** Equity Schemes (Section I)
- **Nature:** Fixed lock-in duration

## 2. **Retirement Fund**
- **Lock-in Period:** 5 Years **or** Retirement Age (whichever is applicable)
- **Section:** Solution Oriented Schemes (Section IV)
- **Nature:** Flexible lock-in based on retirement milestone

## 3. **Children's Fund...
```

---

### Turn 8
**Query:** What is a Multi Asset Allocation Fund and what is the minimum number of asset classes it must invest in? How does this differ from a Balanced Hybrid Fund?

#### Traditional RAG
- Input Tokens: `744` | Output Tokens: `321` | Latency: `3705.5ms`
- Sources: `HYB_MULTI_ASSET, SECTION_III_SUMMARY, HYB_BALANCED`
```
# Multi Asset Allocation Fund vs. Balanced Hybrid Fund

## Multi Asset Allocation Fund (HYB_MULTI_ASSET)

A Multi Asset Allocation Fund is a hybrid scheme with the following characteristics:

**Investment Mandate:** Minimum 10% each in at least **three distinct asset classes**.

**Equity Allocation Band:** Minimum 10% per asset class (across 3 or more classes)

**Minimum Number of Asset Classes:** **3 asset classes** (minimum)

---

## Key Differences from Balanced Hybrid Fund

| Aspect | Multi Asset Allocation | Balanced Hybrid Fund |
|--------|------------------------|----------------------|...
```

#### Hybrid RAG
- Input Tokens: `517` | Output Tokens: `392` | Latency: `6077.3ms`
- Graph Edges Used: `0` | Nodes Matched: `0` | **Token Savings: `30.5%`**
```
# Multi Asset Allocation Fund vs. Balanced Hybrid Fund

## Multi Asset Allocation Fund

**Definition & Classification:**
A Multi Asset Allocation Fund is a Hybrid Scheme category (Code: HYB_MULTI_ASSET) regulated under SEBI/HO/IMD/DF3/CIR/P/2017/114.

**Minimum Number of Asset Classes:**
A Multi Asset Allocation Fund must invest in **at least 3 distinct asset classes**, with a **minimum of 10% allocation to each asset class**.

**Investment Mandate:**
- Minimum 10% each in at least three distinct asset classes
- Provides diversification across multiple asset categories beyond the traditional e...
```

---

### Turn 9
**Query:** Which mutual fund scheme categories allow an AMC to launch multiple schemes within the same category? What is the regulatory exception that permits this, and which SEBI circular grants it?

#### Traditional RAG
- Input Tokens: `986` | Output Tokens: `290` | Latency: `4313.2ms`
- Sources: `CIRCULAR_PRIMARY, EQ_SECTORAL_THEMATIC, OTHER_FOF_DOMESTIC`
```
# Mutual Fund Scheme Categories Allowing Multiple Schemes Per AMC

## Categories Permitting Multiple Schemes:

The following scheme categories allow an AMC to launch multiple schemes within the same category:

1. **Sectoral/Thematic Funds** – Multiple schemes permitted across distinct sectors/themes
2. **Index Funds** – Multiple schemes permitted across distinct indices
3. **Fund of Funds (Domestic)** – Multiple schemes permitted
4. **Fund of Funds (Overseas)** – Multiple schemes permitted
5. **ETFs** – Mentioned as an exception category (though specific details not elaborated in context)

## ...
```

#### Hybrid RAG
- Input Tokens: `1117` | Output Tokens: `463` | Latency: `6936.2ms`
- Graph Edges Used: `2` | Nodes Matched: `6` | **Token Savings: `-13.3%`**
```
# Mutual Fund Scheme Categories Allowing Multiple Schemes Per AMC

## Direct Answer from Graph Knowledge

The following scheme categories **permit multiple schemes per AMC** within the same category:

1. **Sectoral/Thematic Funds** [EQ_SECTORAL_THEMATIC]
2. **Index Funds** [OTHER_INDEX_FUND]
3. **Gold ETFs** [OTHER_GOLD_ETF]
4. **Other ETFs** [OTHER_ETF]
5. **Fund of Funds (Overseas)** [OTHER_FOF_OVERSEAS]
6. **Fund of Funds (Domestic)** [OTHER_FOF_DOMESTIC]

---

## Regulatory Exception & Legal Basis

### The General Rule
**SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2017/114** ('Categorization and R...
```

---

### Turn 10
**Query:** For a 55-year-old investor planning to retire in 5 years who wants tax efficiency and moderate equity exposure, which three scheme categories across different sections of the taxonomy are most relevant? Provide the exact SEBI investment mandate for each recommended category.

#### Traditional RAG
- Input Tokens: `890` | Output Tokens: `369` | Latency: `6760.0ms`
- Sources: `SOL_RETIREMENT, HYB_EQUITY_SAVINGS, EQ_ELSS`
```
# Recommended Scheme Categories for 55-Year-Old Investor Retiring in 5 Years

Based on the investor's profile (5-year horizon, retirement planning, tax efficiency, moderate equity exposure), here are the three most relevant scheme categories:

## 1. **Retirement Fund** (Solution Oriented Schemes)
**SEBI Category Identifier:** Solution Oriented Scheme - Retirement Fund

**Investment Mandate:** Solution-oriented scheme for retirement benefit; lock-in of 5 years or until retirement age, whichever is earlier.

---

## 2. **ELSS (Equity Linked Savings Scheme)** (Equity Schemes)
**SEBI Category Iden...
```

#### Hybrid RAG
- Input Tokens: `872` | Output Tokens: `494` | Latency: `6588.8ms`
- Graph Edges Used: `2` | Nodes Matched: `0` | **Token Savings: `2.0%`**
```
# Recommended Scheme Categories for a 55-Year-Old Pre-Retiree

Based on the investor's profile (5-year retirement horizon, tax efficiency needs, moderate equity exposure), here are the three most relevant scheme categories across different sections:

---

## 1. **Retirement Fund (Solution Oriented Schemes)**
**Code:** SOL_RETIREMENT

**SEBI Investment Mandate:** Solution-oriented scheme for retirement benefit; lock-in of 5 years or until retirement age, whichever is earlier.

**Relevance:** Perfect alignment—the 5-year lock-in matches the investor's 5-year retirement timeline, and the scheme i...
```

---
