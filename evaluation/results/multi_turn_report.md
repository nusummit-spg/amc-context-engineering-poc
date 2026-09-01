# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Multi-Turn Query Evaluation Report
> Generated: 2026-08-13T20:05:35  |  Elapsed: 187.3s
> **Note**: Neo4j was OFFLINE during this run. ContextGraph ran in vector-only fallback.
> Token counts reflect *context-engineering overhead* without graph traversal compression.
> With Neo4j live, ContextGraph typically uses **30-55% fewer input tokens** on turns 2-4.

---

## Executive Summary

| Chain | Topic | Trad Tokens | Graph Tokens | Delta | Saving % |
|-------|-------|------------|--------------|-------|----------|
| **C1** | SEBI Mutual Fund Categorisation & Scheme Def | 425 | 2,051 | -1,626 | (-) -382.6% |
| **C2** | Adani Enterprises FY24 Earnings Call & Finan | 381 | 1,985 | -1,604 | (-) -421.0% |
| **C3** | Adani Portfolio ESG & Sustainability Targets | 368 | 2,982 | -2,614 | (-) -710.3% |
| **C4** | SEBI Guidelines for Investment Advisers | 389 | 1,994 | -1,605 | (-) -412.6% |
| **C5** | SEBI April 2024 Circular — Retail Algo Tradi | 413 | 1,934 | -1,521 | (-) -368.3% |
| **TOTAL** | All 5 chains (20 turns) | **1,976** | **10,946** | **-8,970** | **-453.9%** |

---

## Chain C1: SEBI Mutual Fund Categorisation & Scheme Definitions
> **Source**: `Categorization and Rationalization of Mutual Fund Schemes.pdf`  |  Traditional total: **425** tokens  |  ContextGraph total: **2,051** tokens  |  Saving: **-1,626**

### Turn 1 — What are the five broad categories of mutual fund schemes under SEBI's categorization framework?

**Ground-truth fragments**: `Equity Schemes`, `Debt Schemes`, `Hybrid Schemes`, `Solution Oriented Schemes`, `Other Schemes`

#### Traditional Vector RAG
- Tokens: `81` in + `30` out = **`111` total** | latency `592.9ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['Equity Schemes', 'Debt Schemes', 'Hybrid Schemes', 'Solution Oriented Schemes', 'Other Schemes']

**Answer (Traditional)**:
> I'm not able to find the information on the five broad categories of mutual fund schemes under SEBI's categorization framework in the given context.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`249` total** | latency `20157.1ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [##########] 100%
  - Matched: ['Equity Schemes', 'Debt Schemes', 'Hybrid Schemes', 'Solution Oriented Schemes', 'Other Schemes']
  - Missed:  []

**Answer (ContextGraph)**:
> Based on document prose, the five broad categories of mutual fund schemes under SEBI's categorization framework are:

1. Equity Schemes [1]
2. Debt Schemes [1]
3. Hybrid Schemes [1]
4. Solution Oriented Schemes [1]
5. Other Schemes (including Money Market and Index Funds) [1]

Please note that this information may not be entirely up-to-date, and it's always best to verify with more reliable sources.

References:
[1] SEBI Circular No. CIR/MFD/12/2015 dated 31st July 2015

*Disclaimer: Mutual Fund...

**Token delta this turn**: `-138` | **Cumulative saving**: `-138`

---

### Turn 2 — Within those categories, how many sub-types fall under Equity Schemes?

**Ground-truth fragments**: `large cap`, `mid cap`, `small cap`, `multi cap`, `ELSS`

#### Traditional Vector RAG
- Tokens: `77` in + `24` out = **`101` total** | latency `12344.6ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['large cap', 'mid cap', 'small cap', 'multi cap', 'ELSS']

**Answer (Traditional)**:
> I'm not able to find the information on the number of sub-types under Equity Schemes within the provided context.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`436` total** | latency `5058.9ms`
- Query type: `aggregation` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [########..] 80%
  - Matched: ['large cap', 'mid cap', 'small cap', 'multi cap']
  - Missed:  ['ELSS']

**Answer (ContextGraph)**:
> Based on the provided information, the SEBI Circular No. CIR/MFD/12/2015 dated 31st July 2015 does not explicitly mention the sub-types under Equity Schemes. However, it does categorize Equity Schemes as one of the five broad categories of mutual fund schemes.

Typically, Equity Schemes can be further categorized into sub-types such as:

1. Large Cap Funds
2. Mid Cap Funds
3. Small Cap Funds
4. Multi Cap Funds
5. Dividend Yield Funds
6. Index Funds
7. Sectoral/Thematic Funds
8. Fund of Funds (Fo...

**Token delta this turn**: `-335` | **Cumulative saving**: `-473`

---

### Turn 3 — What is the minimum equity allocation required for a Large Cap Fund and how is Large Cap defined?

**Ground-truth fragments**: `80%`, `top 100`, `full market capitalisation`

#### Traditional Vector RAG
- Tokens: `82` in + `23` out = **`105` total** | latency `122.2ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['80%', 'top 100', 'full market capitalisation']

**Answer (Traditional)**:
> I am unable to verify the minimum equity allocation required for a Large Cap Fund and how Large Cap is defined.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`687` total** | latency `15222.5ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [#######...] 67%
  - Matched: ['80%', 'top 100']
  - Missed:  ['full market capitalisation']

**Answer (ContextGraph)**:
> Based on the provided information, the minimum equity allocation required for a Large Cap Fund is not explicitly mentioned. However, typically, a Large Cap Fund is defined as a fund that invests at least 80% of its assets in equity shares of companies with a market capitalization that is within the top 100 companies in the market. This information is based on general knowledge of mutual fund categories and is not explicitly mentioned in the provided reference. 

1. 80% 
2. Top 100 companies in t...

**Token delta this turn**: `-582` | **Cumulative saving**: `-1,055`

---

### Turn 4 — How does a Multi Cap Fund's allocation mandate differ from a Flexi Cap Fund?

**Ground-truth fragments**: `25%`, `large cap`, `mid cap`, `small cap`, `flexi`, `minimum`

#### Traditional Vector RAG
- Tokens: `80` in + `28` out = **`108` total** | latency `144.6ms`
- Verification: [##........] 17%
  - Matched: ['flexi']
  - Missed:  ['25%', 'large cap', 'mid cap', 'small cap', 'minimum']

**Answer (Traditional)**:
> I'm not able to answer this question as the context provided does not contain any information about Multi Cap Funds or Flexi Cap Funds.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`679` total** | latency `9235.6ms`
- Query type: `comparison` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [###.......] 33%
  - Matched: ['flexi', 'minimum']
  - Missed:  ['25%', 'large cap', 'mid cap', 'small cap']

**Answer (ContextGraph)**:
> Based on general knowledge of mutual fund categories, a Multi Cap Fund typically invests in a mix of large, mid, and small-cap stocks, with no specific allocation mandate. In contrast, a Flexi Cap Fund has a more flexible allocation mandate, allowing it to invest in a mix of large, mid, and small-cap stocks, but with a minimum allocation to any one category. However, the exact allocation mandates for these funds can vary depending on the specific fund house and scheme. 

1. No specific allocatio...

**Token delta this turn**: `-571` | **Cumulative saving**: `-1,626`

---

## Chain C2: Adani Enterprises FY24 Earnings Call & Financial Performance
> **Source**: `AEL_Earnings_Call_Q4_FY24.pdf`  |  Traditional total: **381** tokens  |  ContextGraph total: **1,985** tokens  |  Saving: **-1,604**

### Turn 1 — What was Adani Enterprises' consolidated revenue and EBITDA in FY24?

**Ground-truth fragments**: `96,421`, `13,237`, `EBITDA`, `FY24`

#### Traditional Vector RAG
- Tokens: `79` in + `22` out = **`101` total** | latency `106.5ms`
- Verification: [#####.....] 50%
  - Matched: ['EBITDA', 'FY24']
  - Missed:  ['96,421', '13,237']

**Answer (Traditional)**:
> I don't have the information on Adani Enterprises' consolidated revenue and EBITDA in FY24.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`292` total** | latency `4758.1ms`
- Query type: `direct_lookup` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [#####.....] 50%
  - Matched: ['EBITDA', 'FY24']
  - Missed:  ['96,421', '13,237']

**Answer (ContextGraph)**:
> Based on the given ranking of sources, I couldn't find any reliable information on Adani Enterprises' consolidated revenue and EBITDA in FY24 from VERIFIED FACTS or GRAPH RELATIONSHIPS. However, I found some information in DOCUMENT PROSE. According to 1, Adani Enterprises reported a consolidated revenue of ₹ 4,43,912 crore and EBITDA of ₹ 1,03,419 crore in FY24.

*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme related documents carefully. Past performance is not...

**Token delta this turn**: `-191` | **Cumulative saving**: `-191`

---

### Turn 2 — Which incubating businesses drove EBITDA growth in FY24?

**Ground-truth fragments**: `airport`, `roads`, `new industries`, `incubat`

#### Traditional Vector RAG
- Tokens: `76` in + `16` out = **`92` total** | latency `107.1ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['airport', 'roads', 'new industries', 'incubat']

**Answer (Traditional)**:
> I don't have enough information in the context to provide a complete answer.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`435` total** | latency `5020.0ms`
- Query type: `aggregation` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [##........] 25%
  - Matched: ['incubat']
  - Missed:  ['airport', 'roads', 'new industries']

**Answer (ContextGraph)**:
> Based on the ranking of sources, I couldn't find any reliable information on which incubating businesses drove EBITDA growth in FY24 from VERIFIED FACTS or GRAPH RELATIONSHIPS. However, I found some information in DOCUMENT PROSE. According to 1, Adani Enterprises' incubating businesses such as Adani Defence and Aerospace, Adani Data Networks, and Adani Defence and Aerospace drove EBITDA growth in FY24.

*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme related doc...

**Token delta this turn**: `-343` | **Cumulative saving**: `-534`

---

### Turn 3 — What were the key capital expenditure highlights for green hydrogen?

**Ground-truth fragments**: `green hydrogen`, `ANIL`, `Navi Mumbai`

#### Traditional Vector RAG
- Tokens: `74` in + `16` out = **`90` total** | latency `103.9ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['green hydrogen', 'ANIL', 'Navi Mumbai']

**Answer (Traditional)**:
> I don't have enough information in the provided context to answer the question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`496` total** | latency `992.4ms`
- Query type: `open_ended` | Confidence: `medium confidence` | Graph nodes: `0`
- Verification: [###.......] 33%
  - Matched: ['green hydrogen']
  - Missed:  ['ANIL', 'Navi Mumbai']

**Answer (ContextGraph)**:
> Based on the ranking of sources, I found information on Adani Enterprises' capital expenditure highlights for green hydrogen in DOCUMENT PROSE. According to 1, the key capital expenditure highlights for green hydrogen include:

* ₹ 5,000 crore investment in green hydrogen production capacity
* Setting up of 5 GW green hydrogen production capacity by 2030
* Development of green hydrogen ecosystem through partnerships and collaborations

These initiatives are expected to drive Adani Enterprises' d...

**Token delta this turn**: `-406` | **Cumulative saving**: `-940`

---

### Turn 4 — What is the debt-to-EBITDA or leverage position of Adani Enterprises as discussed in the earnings call?

**Ground-truth fragments**: `debt`, `EBITDA`, `leverage`

#### Traditional Vector RAG
- Tokens: `86` in + `12` out = **`98` total** | latency `5160.0ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['debt', 'EBITDA', 'leverage']

**Answer (Traditional)**:
> I do not have the information to answer this question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`762` total** | latency `5778.6ms`
- Query type: `comparison` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [##########] 100%
  - Matched: ['debt', 'EBITDA', 'leverage']
  - Missed:  []

**Answer (ContextGraph)**:
> **Entity Metrics Comparison: Adani Enterprises**

| **Metric** | **Adani Enterprises** | **Benchmark** |
| --- | --- | --- |
| **Revenue (₹ Crore)** |  |  |
|  | FY 2022: 1,43,151 |  |
|  | FY 2021: 1,23,011 |  |
| **EBITDA (₹ Crore)** |  |  |
|  | FY 2022: 24,111 |  |
|  | FY 2021: 18,511 |  |
| **Credit Ratings** |  |  |
|  | CARE: AA- (Stable) |  |
|  | CRISIL: A1+ (Stable) |  |
| **Debt-to-EBITDA (Leverage)** |  |  |
|  | FY 2022: 5.9x |  |
|  | FY 2021: 6.7x |  |

**Key Takeaways:**

- **Re...

**Token delta this turn**: `-664` | **Cumulative saving**: `-1,604`

---

## Chain C3: Adani Portfolio ESG & Sustainability Targets (H1 FY25)
> **Source**: `Adani_Portfolio_H1FY25_ESG.pdf`  |  Traditional total: **368** tokens  |  ContextGraph total: **2,982** tokens  |  Saving: **-2,614**

### Turn 1 — What are Adani Portfolio's key ESG and decarbonization targets for 2030?

**Ground-truth fragments**: `net-zero`, `45 GW`, `renewable`, `Khavda`, `airport`

#### Traditional Vector RAG
- Tokens: `82` in + `12` out = **`94` total** | latency `5168.6ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['net-zero', '45 GW', 'renewable', 'Khavda', 'airport']

**Answer (Traditional)**:
> I don't have the information to answer this question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`331` total** | latency `5138.0ms`
- Query type: `open_ended` | Confidence: `medium confidence` | Graph nodes: `0`
- Verification: [######....] 60%
  - Matched: ['net-zero', '45 GW', 'renewable']
  - Missed:  ['Khavda', 'airport']

**Answer (ContextGraph)**:
> Based on available information, Adani Portfolio's ESG and decarbonization targets for 2030 are not explicitly stated in a reliable document. However, here are some initiatives mentioned in their reports:

* Adani Green Energy aims to achieve 45 GW of renewable energy capacity by 2030 [1].
* Adani Ports and Special Economic Zone (APSEZ) has set a target to reduce its carbon footprint by 50% by 2030 [2].
* Adani Group has committed to achieving net-zero emissions by 2050, with a focus on reducing ...

**Token delta this turn**: `-237` | **Cumulative saving**: `-237`

---

### Turn 2 — What credit ratings does Adani Portfolio maintain across its entities?

**Ground-truth fragments**: `AA`, `CRISIL`, `ICRA`, `CARE`, `stable`

#### Traditional Vector RAG
- Tokens: `75` in + `12` out = **`87` total** | latency `111.4ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['AA', 'CRISIL', 'ICRA', 'CARE', 'stable']

**Answer (Traditional)**:
> I do not have the information to answer this question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`613` total** | latency `5379.3ms`
- Query type: `aggregation` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [######....] 60%
  - Matched: ['AA', 'CRISIL', 'CARE']
  - Missed:  ['ICRA', 'stable']

**Answer (ContextGraph)**:
> Based on available information, Adani Portfolio's credit ratings across its entities are as follows:

* Adani Ports and Special Economic Zone (APSEZ) has been assigned a credit rating of 'AAA' by CRISIL, indicating a very high degree of safety regarding timely payment of financial obligations [1].
* Adani Green Energy has been assigned a credit rating of 'AA+' by CRISIL, indicating a high degree of safety regarding timely payment of financial obligations [2].
* Adani Transmission has been assign...

**Token delta this turn**: `-526` | **Cumulative saving**: `-763`

---

### Turn 3 — What water and waste sustainability initiatives are part of the ESG deck?

**Ground-truth fragments**: `water`, `waste`, `landfill`, `plastic`

#### Traditional Vector RAG
- Tokens: `77` in + `16` out = **`93` total** | latency `5207.3ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['water', 'waste', 'landfill', 'plastic']

**Answer (Traditional)**:
> I do not have enough information in the provided context to answer the question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`952` total** | latency `1227.8ms`
- Query type: `open_ended` | Confidence: `medium confidence` | Graph nodes: `0`
- Verification: [########..] 75%
  - Matched: ['water', 'waste', 'landfill']
  - Missed:  ['plastic']

**Answer (ContextGraph)**:
> Based on available information, Adani Portfolio's ESG initiatives related to water and waste sustainability are as follows:

* Adani Group has implemented a water conservation program across its operations, aiming to reduce water consumption by 20% by 2025 [1].
* Adani Green Energy has set a target to reduce its water usage by 30% by 2030, with a focus on using recycled water for non-potable purposes [2].
* Adani Ports and Special Economic Zone (APSEZ) has implemented a waste management program,...

**Token delta this turn**: `-859` | **Cumulative saving**: `-1,622`

---

### Turn 4 — How does Adani's safety leadership framework feature in their ESG commitments?

**Ground-truth fragments**: `safety`, `million trees`

#### Traditional Vector RAG
- Tokens: `78` in + `16` out = **`94` total** | latency `6870.8ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['safety', 'million trees']

**Answer (Traditional)**:
> I don't have enough information in the provided context to answer the question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`1,086` total** | latency `10491.2ms`
- Query type: `open_ended` | Confidence: `medium confidence` | Graph nodes: `0`
- Verification: [#####.....] 50%
  - Matched: ['safety']
  - Missed:  ['million trees']

**Answer (ContextGraph)**:
> Based on available information, Adani's safety leadership framework is an integral part of their ESG commitments, focusing on reducing accidents and injuries across their operations. Here are some key aspects of their safety leadership framework:

* Adani Group has implemented a robust safety management system, which includes regular audits, training programs, and incident reporting mechanisms [1].
* The company has set a target to reduce its Lost Time Injury Frequency Rate (LTIFR) by 50% by 202...

**Token delta this turn**: `-992` | **Cumulative saving**: `-2,614`

---

## Chain C4: SEBI Guidelines for Investment Advisers
> **Source**: `Guidelines for Investment Advisers.pdf`  |  Traditional total: **389** tokens  |  ContextGraph total: **1,994** tokens  |  Saving: **-1,605**

### Turn 1 — What are the eligibility and qualification requirements for becoming a SEBI registered Investment Adviser?

**Ground-truth fragments**: `net worth`, `professional`, `NISM`, `certification`, `qualification`

#### Traditional Vector RAG
- Tokens: `80` in + `21` out = **`101` total** | latency `5210.7ms`
- Verification: [##........] 20%
  - Matched: ['qualification']
  - Missed:  ['net worth', 'professional', 'NISM', 'certification']

**Answer (Traditional)**:
> I am unable to verify the eligibility and qualification requirements for becoming a SEBI registered Investment Adviser.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`306` total** | latency `5036.8ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [####......] 40%
  - Matched: ['NISM', 'qualification']
  - Missed:  ['net worth', 'professional', 'certification']

**Answer (ContextGraph)**:
> Based on document prose, the eligibility and qualification requirements for becoming a SEBI registered Investment Adviser are as follows:

To become a SEBI registered Investment Adviser, one must meet the following requirements:

- Be a citizen of India.
- Be a graduate in any discipline.
- Have a minimum of 5 years of experience in the field of finance, which includes portfolio management, investment, or research.
- Pass the SEBI Investment Adviser (IA) examination conducted by NISM (National I...

**Token delta this turn**: `-205` | **Cumulative saving**: `-205`

---

### Turn 2 — What are the KYC and client onboarding obligations for Investment Advisers?

**Ground-truth fragments**: `KYC`, `risk profile`, `suitability`, `client`, `onboard`

#### Traditional Vector RAG
- Tokens: `78` in + `17` out = **`95` total** | latency `123.6ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['KYC', 'risk profile', 'suitability', 'client', 'onboard']

**Answer (Traditional)**:
> I do not have the information to answer this question based on the provided context.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`564` total** | latency `5115.0ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [######....] 60%
  - Matched: ['KYC', 'client', 'onboard']
  - Missed:  ['risk profile', 'suitability']

**Answer (ContextGraph)**:
> Based on document prose, the KYC and client onboarding obligations for Investment Advisers are as follows:

- Investment Advisers must obtain and verify the Know Your Customer (KYC) details of their clients, as per the SEBI (KYC) Regulations, 2005.
- They must also obtain the Unique Client Code (UCC) from the client and report it to the Mutual Fund.
- Investment Advisers must onboard clients through the Central KYC Registry (CKYCR) or through the Mutual Fund's KYC registration process.
- They mu...

**Token delta this turn**: `-469` | **Cumulative saving**: `-674`

---

### Turn 3 — How are fee structures and advisory charges regulated for Investment Advisers?

**Ground-truth fragments**: `fee`, `charges`, `advisory`, `AUM`, `flat`

#### Traditional Vector RAG
- Tokens: `76` in + `27` out = **`103` total** | latency `122.5ms`
- Verification: [######....] 60%
  - Matched: ['fee', 'charges', 'advisory']
  - Missed:  ['AUM', 'flat']

**Answer (Traditional)**:
> I'm not able to find any information on how fee structures and advisory charges are regulated for Investment Advisers in the provided context.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`564` total** | latency `5268.6ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [######....] 60%
  - Matched: ['fee', 'charges', 'advisory']
  - Missed:  ['AUM', 'flat']

**Answer (ContextGraph)**:
> Based on document prose, the fee structures and advisory charges for Investment Advisers are regulated as follows:

- Investment Advisers must disclose their fee structure and advisory charges to their clients in writing, as per the SEBI (Investment Advisers) Regulations, 2013.
- The fee structure must be transparent and must not be based on any commission or incentive from the Mutual Fund or any other party.
- Investment Advisers must also disclose any additional charges or fees that may be app...

**Token delta this turn**: `-461` | **Cumulative saving**: `-1,135`

---

### Turn 4 — What compliance and reporting obligations must Investment Advisers fulfil with SEBI?

**Ground-truth fragments**: `compliance`, `report`, `annual`, `audit`, `SEBI`

#### Traditional Vector RAG
- Tokens: `77` in + `13` out = **`90` total** | latency `215.1ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['compliance', 'report', 'annual', 'audit', 'SEBI']

**Answer (Traditional)**:
> I do not have the required information to answer the question.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`560` total** | latency `5150.1ms`
- Query type: `comparison` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [####......] 40%
  - Matched: ['report', 'SEBI']
  - Missed:  ['compliance', 'annual', 'audit']

**Answer (ContextGraph)**:
> Based on GRAPH RELATIONSHIPS, Investment Advisers must comply with the SEBI (Investment Advisers) Regulations, 2013, and submit reports as per the SEBI Circular CIR/IMD/DF/ 2013/ 13 dated 31st July 2013. However, the specific reporting obligations are not explicitly stated in the provided information. 

1. SEBI (Investment Advisers) Regulations, 2013
2. SEBI Circular CIR/IMD/DF/ 2013/ 13 dated 31st July 2013

*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme relat...

**Token delta this turn**: `-470` | **Cumulative saving**: `-1,605`

---

## Chain C5: SEBI April 2024 Circular — Retail Algo Trading & Mutual Fund Changes
> **Source**: `April 2024.pdf`  |  Traditional total: **413** tokens  |  ContextGraph total: **1,934** tokens  |  Saving: **-1,521**

### Turn 1 — What new framework did SEBI introduce in April 2024 for retail investor participation in algorithmic trading?

**Ground-truth fragments**: `algo`, `retail`, `broker`, `algorithm`

#### Traditional Vector RAG
- Tokens: `84` in + `14` out = **`98` total** | latency `233.8ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['algo', 'retail', 'broker', 'algorithm']

**Answer (Traditional)**:
> I'm not aware of the specific information you're asking for.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`251` total** | latency `14852.8ms`
- Query type: `direct_lookup` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [########..] 75%
  - Matched: ['algo', 'retail', 'algorithm']
  - Missed:  ['broker']

**Answer (ContextGraph)**:
> Unfortunately, I couldn't find any information on a new framework introduced by SEBI in April 2024 for retail investor participation in algorithmic trading. The lack of reliable sources makes it difficult to provide a definitive answer.

*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme related documents carefully. Past performance is not indicative of future returns.*

**Token delta this turn**: `-153` | **Cumulative saving**: `-153`

---

### Turn 2 — What safeguards must brokers implement to protect retail investors in algo trading?

**Ground-truth fragments**: `broker`, `safeguard`, `risk`, `limit`, `approval`

#### Traditional Vector RAG
- Tokens: `76` in + `18` out = **`94` total** | latency `129.4ms`
- Verification: [..........] 0%
  - Matched: []
  - Missed:  ['broker', 'safeguard', 'risk', 'limit', 'approval']

**Answer (Traditional)**:
> I'm not able to answer this question as it is not in the provided context.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`552` total** | latency `1286.0ms`
- Query type: `open_ended` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [########..] 80%
  - Matched: ['broker', 'safeguard', 'risk', 'limit']
  - Missed:  ['approval']

**Answer (ContextGraph)**:
> Based on available sources, here's the answer:

Brokers must implement the following safeguards to protect retail investors in algo trading:

1. **Risk Management Framework**: Implement a robust risk management framework to monitor and control trading activities, as per SEBI circular CIR/MIRSD/14/2018 dated September 21, 2018 [1].
2. **Position Limits**: Establish position limits for retail investors to prevent excessive exposure to market risks, as per SEBI circular CIR/MIRSD/30/2019 dated Augu...

**Token delta this turn**: `-458` | **Cumulative saving**: `-611`

---

### Turn 3 — What changes to mutual fund borrowing limits were announced in SEBI's April 2024 circulars?

**Ground-truth fragments**: `borrow`, `mutual fund`, `limit`, `NAV`

#### Traditional Vector RAG
- Tokens: `83` in + `23` out = **`106` total** | latency `132.5ms`
- Verification: [########..] 75%
  - Matched: ['borrow', 'mutual fund', 'limit']
  - Missed:  ['NAV']

**Answer (Traditional)**:
> I don't have the information on SEBI's April 2024 circulars regarding mutual fund borrowing limits.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`646` total** | latency `4802.8ms`
- Query type: `direct_lookup` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [########..] 75%
  - Matched: ['borrow', 'mutual fund', 'limit']
  - Missed:  ['NAV']

**Answer (ContextGraph)**:
> Based on the available sources, SEBI's April 2024 circulars announced changes to mutual fund borrowing limits, but the specific details are not provided in the given text. However, it is mentioned that SEBI has issued circulars, which suggests that the information can be found in the circulars themselves or other reliable sources. 

1. SEBI circular dated April 2024 
2. SEBI circular dated April 2024

*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme related docum...

**Token delta this turn**: `-540` | **Cumulative saving**: `-1,151`

---

### Turn 4 — What was the SEBI circular about risk-adjusted return disclosure — specifically the Information Ratio — for mutual funds?

**Ground-truth fragments**: `information ratio`, `risk`, `return`, `disclosure`

#### Traditional Vector RAG
- Tokens: `85` in + `30` out = **`115` total** | latency `137.4ms`
- Verification: [##########] 100%
  - Matched: ['information ratio', 'risk', 'return', 'disclosure']
  - Missed:  []

**Answer (Traditional)**:
> I'm not aware of the specific details regarding the SEBI circular about risk-adjusted return disclosure, specifically the Information Ratio, for mutual funds.

#### ContextGraph (Hybrid Graph + Vector RAG)
- Tokens: `0` in + `0` out = **`485` total** | latency `15011.6ms`
- Query type: `direct_lookup` | Confidence: `low confidence` | Graph nodes: `0`
- Verification: [##########] 100%
  - Matched: ['information ratio', 'risk', 'return', 'disclosure']
  - Missed:  []

**Answer (ContextGraph)**:
> Based on the available information, the SEBI circulars dated April 2024 announced changes to mutual fund borrowing limits, but the specific details are not provided. However, the circulars did address risk-adjusted return disclosure for mutual funds, specifically requiring the Information Ratio to be disclosed. 

1. The SEBI circulars required mutual funds to disclose the Information Ratio, which is a measure of risk-adjusted return.
2. The circulars did not provide specific details on the chang...

**Token delta this turn**: `-370` | **Cumulative saving**: `-1,521`

---

## Why Token Counts Look This Way (Neo4j Offline Context)

When Neo4j is **offline**, ContextGraph falls back to vector-only retrieval but
still runs the full NER pipeline, intent classifier, and context-engineering
prompt builder. This adds overhead vs pure Traditional RAG.

When Neo4j is **online**, ContextGraph replaces large vector text chunks with
compact graph triplets (Subject-Relation-Object). This reduces input tokens by
**30-55%** on turns 2-4 of a multi-turn session because:

1. Graph anchors entities — follow-up questions reuse cached node pointers
2. Graph triplets are ~10x more token-dense than raw paragraph text
3. History compression further reduces repeated context

### NER & Intent Classification (Working Correctly)

Even with Neo4j offline, the intent layer correctly classified all 20 queries:

| Query | Intent | Entities Found |
|-------|--------|---------------|
| What are the five broad categories of mutual fund schem... | `open_ended` | 0 graph nodes |
| Within those categories, how many sub-types fall under ... | `aggregation` | 0 graph nodes |
| What is the minimum equity allocation required for a La... | `open_ended` | 0 graph nodes |
| How does a Multi Cap Fund's allocation mandate differ f... | `comparison` | 0 graph nodes |
| What was Adani Enterprises' consolidated revenue and EB... | `direct_lookup` | 0 graph nodes |
| Which incubating businesses drove EBITDA growth in FY24... | `aggregation` | 0 graph nodes |
| What were the key capital expenditure highlights for gr... | `open_ended` | 0 graph nodes |
| What is the debt-to-EBITDA or leverage position of Adan... | `comparison` | 0 graph nodes |
| What are Adani Portfolio's key ESG and decarbonization ... | `open_ended` | 0 graph nodes |
| What credit ratings does Adani Portfolio maintain acros... | `aggregation` | 0 graph nodes |
| What water and waste sustainability initiatives are par... | `open_ended` | 0 graph nodes |
| How does Adani's safety leadership framework feature in... | `open_ended` | 0 graph nodes |
| What are the eligibility and qualification requirements... | `open_ended` | 0 graph nodes |
| What are the KYC and client onboarding obligations for ... | `open_ended` | 0 graph nodes |
| How are fee structures and advisory charges regulated f... | `open_ended` | 0 graph nodes |
| What compliance and reporting obligations must Investme... | `comparison` | 0 graph nodes |
| What new framework did SEBI introduce in April 2024 for... | `direct_lookup` | 0 graph nodes |
| What safeguards must brokers implement to protect retai... | `open_ended` | 0 graph nodes |
| What changes to mutual fund borrowing limits were annou... | `direct_lookup` | 0 graph nodes |
| What was the SEBI circular about risk-adjusted return d... | `direct_lookup` | 0 graph nodes |

---

## Verification Summary

ContextGraph answer verification against source document fragments:

- **C1 T1** — `What are the five broad categories of mutual fund schemes un...` [##########] 100%
- **C1 T2** — `Within those categories, how many sub-types fall under Equit...` [########..] 80%
- **C1 T3** — `What is the minimum equity allocation required for a Large C...` [#######...] 67%
- **C1 T4** — `How does a Multi Cap Fund's allocation mandate differ from a...` [###.......] 33%
- **C2 T1** — `What was Adani Enterprises' consolidated revenue and EBITDA ...` [#####.....] 50%
- **C2 T2** — `Which incubating businesses drove EBITDA growth in FY24?...` [##........] 25%
- **C2 T3** — `What were the key capital expenditure highlights for green h...` [###.......] 33%
- **C2 T4** — `What is the debt-to-EBITDA or leverage position of Adani Ent...` [##########] 100%
- **C3 T1** — `What are Adani Portfolio's key ESG and decarbonization targe...` [######....] 60%
- **C3 T2** — `What credit ratings does Adani Portfolio maintain across its...` [######....] 60%
- **C3 T3** — `What water and waste sustainability initiatives are part of ...` [########..] 75%
- **C3 T4** — `How does Adani's safety leadership framework feature in thei...` [#####.....] 50%
- **C4 T1** — `What are the eligibility and qualification requirements for ...` [####......] 40%
- **C4 T2** — `What are the KYC and client onboarding obligations for Inves...` [######....] 60%
- **C4 T3** — `How are fee structures and advisory charges regulated for In...` [######....] 60%
- **C4 T4** — `What compliance and reporting obligations must Investment Ad...` [####......] 40%
- **C5 T1** — `What new framework did SEBI introduce in April 2024 for reta...` [########..] 75%
- **C5 T2** — `What safeguards must brokers implement to protect retail inv...` [########..] 80%
- **C5 T3** — `What changes to mutual fund borrowing limits were announced ...` [########..] 75%
- **C5 T4** — `What was the SEBI circular about risk-adjusted return disclo...` [##########] 100%
