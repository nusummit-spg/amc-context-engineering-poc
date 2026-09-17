# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# 📐 ContextGraph™ Frontend Wireframe Specifications & Architecture

> **Document Version**: 2.0  
> **Target Framework**: React 18 + TypeScript + Vite + Zustand + Tailwind CSS + TanStack Query  
> **Accompanying Interactive Prototype**: [`Docs/wireframe_prototype.html`](file:///C:/Users/Laptopadmin/Desktop/context-engineering/Docs/wireframe_prototype.html)  
> **Source Plan**: [`Docs/frontend_design.md`](file:///C:/Users/Laptopadmin/Desktop/context-engineering/Docs/frontend_design.md)

---

## 📑 Table of Contents
1. [Design System & Visual Tokens](#1-design-system--visual-tokens)
2. [Global Application Shell & Navigation](#2-global-application-shell--navigation)
3. [Screen 1: Authentication & MFA Flow (`/login`, `/mfa`)](#3-screen-1-authentication--mfa-flow)
4. [Screen 2: Comparison Showcase (`/compare` — Hero Feature)](#4-screen-2-comparison-showcase-hero-feature)
5. [Screen 3: Multi-Turn Chatbot (`/chat`)](#5-screen-3-multi-turn-chatbot)
6. [Screen 4: Citation & Provenance Drawer (`/citation`)](#6-screen-4-citation--provenance-drawer)
7. [Screen 5: Executive Analytics Dashboard (`/analytics`)](#7-screen-5-executive-analytics-dashboard)
8. [Screen 6: Admin & Enterprise RBAC Panel (`/admin`)](#8-screen-6-admin--enterprise-rbac-panel)
9. [Role-Based Dashboard Variations](#9-role-based-dashboard-variations)
10. [Responsive Breakpoint Behavior & Mobile Layouts](#10-responsive-breakpoint-behavior)

---

## 1. Design System & Visual Tokens

The user interface preserves the warmth and readability of financial publishing while providing crisp enterprise contrast.

### 🎨 Color Palette
| Token | Hex Value | Semantic Usage |
|---|---|---|
| `--color-rust-primary` | `#A8412C` | Primary brand action, ContextGraph highlights, active states, key data nodes |
| `--color-rust-light` | `#FDF4F2` | Selected tab backgrounds, hover highlights, active session backgrounds |
| `--color-forest-green` | `#3F6B42` | Grounded verification badges, high confidence (0.95+), cache hit indicators |
| `--color-green-light` | `#E4EEE1` | Verification pill background, positive KPI metric badges |
| `--color-warm-cream` | `#F8F7F3` | Primary page background, card container backgrounds |
| `--color-card-white` | `#FFFFFF` | Elevated card surfaces, comparison panels, chat bubbles |
| `--color-charcoal` | `#231F1C` | Primary typography, user chat bubbles, dark headers |
| `--color-slate` | `#5C574C` | Secondary typography, subtitle text, traditional RAG markers |
| `--color-stone-border` | `#E7E1D4` | Card borders, dividers, table borders, input strokes |
| `--color-amber-warn` | `#8A5A20` | Hallucination warnings, fallback indicators, low confidence flags |
| `--color-amber-light` | `#F3E4C9` | Warning banner backgrounds |

### 🔤 Typography Scale
- **Display H1**: `24px` / `700` weight (Tracking: `-0.02em`)
- **Page Title H2**: `18px` / `700` weight
- **Section Header H3**: `14px` / `700` weight (Uppercase tracking: `+0.05em`)
- **Body Regular**: `13px` / `400` weight (Line height: `1.55`)
- **Mono / Code**: `11.5px` / `500` weight (`ui-monospace`, `Courier New`)
- **Micro Labels / Pills**: `10.5px` / `700` weight (Uppercase tracking: `+0.05em`)

---

## 2. Global Application Shell & Navigation

```
+---------------------------------------------------------------------------------------------------------------+
|  [LOGO] ContextGraph™ [AMC AI]   |  [⚡ Compare]  [💬 Chatbot]  [📊 Analytics]  [🛡️ Governance]  | (P) alex_analyst |
+---------------------------------------------------------------------------------------------------------------+
|                                                                                                               |
|  <<< ACTIVE SCREEN ROUTE OUTLET (Vite React Router) >>>                                                       |
|                                                                                                               |
+---------------------------------------------------------------------------------------------------------------+
```

### Component Hierarchy
- `AppShell`
  - `GlobalHeader`
    - `BrandLogo` (`C` emblem + ContextGraph text)
    - `RoleBadge` (Dynamic role indicator)
    - `NavigationTabs` (`/compare`, `/chat`, `/analytics`, `/admin` with RBAC guard)
    - `UserProfileMenu` (Avatar, username, role clearance, logout)
  - `MainContainer`
    - `<RouterOutlet />`
  - `GlobalNotificationToast` (Error boundaries, background sync alerts)

---

## 3. Screen 1: Authentication & MFA Flow

```
+----------------------------------------------------------------------------------+
|                                                                                  |
|                        +--------------------------------+                        |
|                        |          [ C LOGO ]            |                        |
|                        |     Sign in to ContextGraph™   |                        |
|                        |  Enterprise Asset Management   |                        |
|                        +--------------------------------+                        |
|                        | [🔑 Sign in with Okta / Azure] |                        |
|                        | ------------ OR -------------- |                        |
|                        | ENTERPRISE USERNAME OR EMAIL   |                        |
|                        | [ alex_analyst@amc.com       ] |                        |
|                        | PASSWORD                       |                        |
|                        | [ •••••••••••••••••••••••••• ] |                        |
|                        | 2FA AUTHENTICATOR (TOTP) CODE  |                        |
|                        | [ 582 109                    ] |                        |
|                        |                                |                        |
|                        | [  Authenticate & Enter >>   ] |                        |
|                        +--------------------------------+                        |
|                                                                                  |
+----------------------------------------------------------------------------------+
```

### Technical Specs & States
- **Form Controls**: Email input, Password masked input with show/hide toggle, 6-digit TOTP token input with automatic focus forwarding.
- **State Store**: `authStore` (`user`, `token`, `role`, `permissions`, `isAuthenticated`).
- **Validation**: Client-side regex check + server-side rate-limited challenge (`POST /api/auth/login`).
- **Security**: JWT stored in HTTPOnly `Secure` cookie; CSRF token transmitted via header.

---

## 4. Screen 2: Comparison Showcase (Hero Feature)

```
+---------------------------------------------------------------------------------------------------------------+
|  [⚡ PROMPT INPUT BAR]                                                                                        |
|  [ What is the maximum TER allowed for equity schemes > ₹50,000 Cr under SEBI circulars?          ] [Execute] |
|  Sample Queries: [TER Slabs Equity] [HDFC vs ICICI Beta] [AT1 Bond Valuation] [Liquid Fund Cut-off Timing]    |
+-------------------------------------------------------+-------------------------------------------------------+
|  ⚪ Traditional Document Search (Vector Only)          |  🔴 ContextGraph™ Knowledge Engine (Hybrid + Neo4j)   |
+-------------------------------------------------------+-------------------------------------------------------+
|  FILES RETURNED, RANKED BY SIMILARITY:                |  [✓ 100% GROUNDED] [⚡ PILLAR 1: ZERO-TOKEN FAST HIT]  |
|                                                       |                                                       |
|  +-------------------------------------------------+  |  Under SEBI Circular [SEBI/HO/IMD/DF2/CIR/P/2018/137  |
|  | SEBI_Circular_MF_2018.pdf · p.14    [Score: 0.76]|  |  §4], the maximum TER for open-ended equity schemes   |
|  | "...expenses incurred by mutual fund schemes..."|  |  with daily net assets exceeding ₹50,000 Cr is capped |
|  +-------------------------------------------------+  |  at 1.05% with a 0.05% reduction per ₹5,000 Cr slab.  |
|  +-------------------------------------------------+  |                                                       |
|  | AMFI_Best_Practice_TER.pdf · p.3    [Score: 0.71]|  |  +-------------------------------------------------+  |
|  | "...all AMCs are required to disclose daily..." |  |  | 🕸️ GRAPH PATH: EquityScheme -> HAS_TER_CAP -> 1.05%|  |
|  +-------------------------------------------------+  |  | [Node: Equity] ---> (Slab Tier-7) ---> [Cap: 1.05%] |  |
|                                                       |  +-------------------------------------------------+  |
|  ⚠ Warning: Fragmented chunks returned. No consolidated|                                                       |
|    answer linking tiered slab thresholds.              |  +-------------------------------------------------+  |
|                                                       |  | 📌 DOCUMENT PROVENANCE: SEBI Circular 2018 §4 (p.14)|  |
|  SYNTHESIS ATTEMPT:                                   |  +-------------------------------------------------+  |
|  Regulation 52 defines base TER at 2.25%. Higher tier |                                                       |
|  slabs beyond ₹50,000 Cr were not present in top chunks|                                                       |
|                                                       |                                                       |
|  +-------------------------------------------------+  |  +-------------------------------------------------+  |
|  | ⚡ EXECUTION BREAKDOWN                           |  |  | ⚡ MICROSECOND TELEMETRY & TOKEN SAVINGS        |  |
|  | Vector DB Lookup (FAISS):              412.3 ms |  |  | Entity Resolution (NER):                 18.2 ms |  |
|  | Cross-Encoder Rerank:                  890.1 ms |  |  | Graph Traversal (UNWIND):               24.5 ms |  |
|  | LLM Synthesis:                       1,120.4 ms |  |  | Zero-Token Cache Hit:                    0.8 ms |  |
|  | Total Latency:          2,422.8 ms (1,840 toks) |  |  | Tokens Saved:         3,420 tokens (100% saved) |  |
|  |                                                 |  |  | Total Latency:          312.4 ms (7.7x FASTER!) |  |
|  +-------------------------------------------------+  |  +-------------------------------------------------+  |
+-------------------------------------------------------+-------------------------------------------------------+
```

### Key UI Features
- **Parallel Dispatch**: Client fires `Promise.allSettled()` against both pipelines. ContextGraph renders instantaneously (~300ms) without waiting for the slower traditional RAG pipeline (~2400ms).
- **Graph Traversal Visualization**: Cytoscape.js canvas showing the multi-hop relationship path traversed across Neo4j nodes.
- **Microsecond Telemetry Accordion**: Direct latency attribution per retrieval layer (Vector vs Graph vs NER vs LLM).

---

## 5. Screen 3: Multi-Turn Chatbot Interface

```
+------------------------+--------------------------------------------------------------------------------------+
| 💬 CONVERSATIONS       |  TER Slabs & SEBI Limits                                      [Export JSON] [Share]  |
| [+ New Chat]           +--------------------------------------------------------------------------------------+
|                        |                                                                                      |
| 🟢 TER Slabs & Limits  |  [User]: What are the liquidity requirements for overnight mutual funds?              |
|    4 turns · 2m ago    |                                                                                      |
|                        |  [ContextGraph Assistant]:                                                           |
| ⚪ HDFC vs Nippon Beta |  ✓ Grounded in SEBI Master Circulars                                                 |
|    2 turns · 1h ago    |  Under SEBI Mutual Fund Regulations [SEBI/HO/IMD/DF4/CIR/P/2019/102] [1]:            |
|                        |  • Residual maturity of all debt securities must be exactly 1 business day.           |
| ⚪ Dividend Mandate    |  • Minimum 0% illiquid securities and zero credit enhancements [2].                   |
|    6 turns · Yesterday |  • Exit load is strictly 0.00%.                                                      |
|                        |                                                                                      |
| ⚪ Side-pocketing Rule |  [📌 View 2 Citations]  [🕸️ Inspect Cypher Graph]  [📋 Copy]                        |
|    3 turns · Aug 14    |                                                                                      |
|                        |  [User]: Does this also apply to Liquid Funds, or do they require a 20% cash buffer? |
|                        |                                                                                      |
|                        |  [ContextGraph Assistant]: ⚡ (Streaming response...)                                 |
|                        |  No, Liquid Funds require a minimum 20% liquid asset buffer [3]...                   |
|                        |                                                                                      |
|                        +--------------------------------------------------------------------------------------+
|                        | [ Ask follow-up or explore related regulatory circulars...               ] [Send 🚀] |
+------------------------+--------------------------------------------------------------------------------------+
```

### Component Breakdown
- `ChatSidebar`: Collapsible session drawer with timestamped conversation cards, title search, and delete/archive actions.
- `ChatHistoryFeed`: Virtualized list (`react-virtualized`) rendering user queries, streaming assistant answers, markdown formatting, syntax highlighting, and clickable citation pill components.
- `ChatInputToolbar`: Auto-resizing textarea with keyboard shortcuts (`Cmd+Enter` to send), token counter, and prompt templates.

---

## 6. Screen 4: Citation & Provenance Drawer

```
+-------------------------------------------------------+-------------------------------------------------------+
| 📌 DOCUMENT PROVENANCE: SEBI Circular Section 52       | 🕸️ EXTRACTED TRIPLET LINEAGE (Neo4j)                  |
| Status: [ACTIVE / IN FORCE]   Effective: Oct 22, 2018 | Query: EquityScheme -> HAS_TER_CAP                    |
+-------------------------------------------------------+-------------------------------------------------------+
| SOURCE METADATA:                                      | SUBJECT           PREDICATE       OBJECT       CONF   |
| • Document: SEBI_Master_Circular_MF_2018.pdf          | ---------------------------------------------------   |
| • Clause: Section 52(6)(c)(vii)                       | EquityScheme      HAS_TER_CAP     1.05% (Max)  0.99   |
| • Page Number: Page 14 of 86                          | EquityScheme      GOVERNED_BY     SEBI Reg 52  1.00   |
| • SHA-256 Hash: 8f4a21e7d983...9b3c                   | TER_Reduction     STEP_SIZE       ₹5,000 Cr    0.98   |
|                                                       |                                                       |
| VERBATIM SOURCE TEXT EXTRACT:                         | REGULATORY TAXONOMY CLUSTER:                          |
| ----------------------------------------------------- | Category: Open-Ended Equity Schemes                   |
| "52(6)(c) In case of an open-ended equity scheme, the  | Parent Body: SEBI Mutual Funds Dept                  |
| total expense ratio shall be subject to:              | Direct Cross-References: Regulation 52, CIR-137       |
| (vii) on daily net assets exceeding Rs.50,000 crores: |                                                       |
| TER reduction of 0.05% for every increase of          |                                                       |
| Rs.5,000 crores of daily net assets, up to a maximum  |                                                       |
| cap of 1.05%."                                        |                                                       |
|                                                       |                                                       |
| [ 📥 Download Page PDF ]  [ 🔗 Copy Source Permalink ]| [ 🔍 Open Full Graph Explorer ]                       |
+-------------------------------------------------------+-------------------------------------------------------+
```

---

## 7. Screen 5: Executive Analytics Dashboard

```
+---------------------------------------------------------------------------------------------------------------+
|  📊 EXECUTIVE PERFORMANCE & TOKEN EFFICIENCY DASHBOARD                              [Date Range: Last 30 Days]|
+-----------------------+-----------------------+-----------------------+---------------------------------------+
| TOTAL MONTHLY QUERIES | ZERO-TOKEN CACHE RATE | CLOUD COST SAVINGS    | P95 LATENCY REDUCTION                 |
| 48,290                | 68.2%                 | $14,850               | 340 ms                                |
| ↑ 18.4% vs last month | ⚡ Pillar 1 Active    | 72% Cloud LLM Saved   | 7.7x Faster vs Vector RAG             |
+-----------------------+-----------------------+-----------------------+---------------------------------------+
| DAILY QUERY VOLUME & WARM HIT DISTRIBUTION (Recharts Area)    | QUERY INTENT CLUSTERS (Recharts Donut)        |
|                                                               |                                               |
|  Queries/Day                                                  |   • Compliance & SEBI Circulars (42%)         |
|  2500 |             __/\_/\_                                  |   • Portfolio & Fund Comparison (31%)         |
|  2000 |         _.-'        `--.    [Warm Cache Hits: 68%]    |   • NAV & Expense Accounting (18%)            |
|  1500 |     _.-'                `-.                           |   • Client / Advisor FAQs (9%)                |
|  1000 | _.-'                       `--. [Cold Runs: 32%]      |                                               |
|     0 +-------------------------------------------------      |                                               |
|        Day 1               Day 15                Day 30       |                                               |
+---------------------------------------------------------------+-----------------------------------------------+
```

---

## 8. Screen 6: Admin & Enterprise RBAC Panel

```
+---------------------------------------------------------------------------------------------------------------+
|  🛡️ ENTERPRISE RBAC GOVERNANCE & AUDIT CONSOLE                                                                 |
|  [👤 User Management]  [🛡️ Clearance Matrix]  [📋 Security Audit Trail]  [⚙️ Feature Flags & Ingest]         |
+---------------------------------------------------------------------------------------------------------------+
|  ACTIVE USER PROFILES & ROLES:                                                   [+ Provision New AMC User]   |
|                                                                                                               |
|  USERNAME           EMAIL               ROLE                DEPARTMENT            CLEARANCES      STATUS      |
|  -----------------------------------------------------------------------------------------------------------  |
|  sarah_compliance   sarah.c@amc.com     Compliance Officer  Legal & Regulatory    SEBI, AMFI, PII [Active]    |
|  alex_analyst       alex.a@amc.com      Portfolio Analyst   Equity Investments    NAV, Alpha, Risk [Active]   |
|  raj_manager        raj.m@amc.com       AMC Manager         Executive Management  Full Org + ROI  [Active]    |
|  priya_advisor      priya.a@amc.com     Financial Advisor   Retail Wealth         Factsheets, FAQ [Active]    |
+---------------------------------------------------------------------------------------------------------------+
|  SECURITY & QUERY AUDIT TRAIL:                                                  [📥 Export Compliance CSV]   |
|                                                                                                               |
|  TIMESTAMP            USER              EVENT TYPE      DETAILS / QUERY               RISK    LATENCY  ACTION |
|  -----------------------------------------------------------------------------------------------------------  |
|  2026-08-18 13:20:11  sarah_compliance  query_executed  "TER slab limits for equity"  LOW     312 ms   [View] |
|  2026-08-18 13:18:42  alex_analyst      citation_click  "Doc: SEBI_Circular_MF_2018"  LOW      18 ms   [View] |
|  2026-08-18 13:10:04  unknown_ip        auth_failed     "Invalid MFA token (3x retry)" HIGH     --     [Block]|
+---------------------------------------------------------------------------------------------------------------+
```

---

## 9. Role-Based Dashboard Variations

| Role | Default Landing Screen | Visible Modules | Data Masking / PII | Special Capabilities |
|---|---|---|---|---|
| **AMC Executive / Manager** | `/analytics` | All 6 Screens (Full Access) | Unredacted | ROI savings calculator, Organization rollup, System feature flags |
| **Portfolio Analyst** | `/compare` | `/compare`, `/chat`, `/citation`, `/analytics` | Unredacted portfolio data | Cypher query export, Alpha/Beta triplet explorer, Fund comparisons |
| **Compliance Officer** | `/admin` (Audit tab) | `/compare`, `/chat`, `/citation`, `/admin` | Unredacted PII & audit logs | Regulatory lifecycle tracking, SEBI provenance auditor, Export PDF |
| **Financial Advisor** | `/chat` | `/chat`, `/citation` (Simplified) | Redacted PII | Client-friendly summary generator, Factsheet quick-cards |

---

## 10. Responsive Breakpoint Behavior

```
+-------------------------+---------------------------------------------------------------------+
| BREAKPOINT              | ADAPTIVE LAYOUT BEHAVIOR                                            |
+-------------------------+---------------------------------------------------------------------+
| Desktop / Ultrawide     | Full dual-column side-by-side comparison.                           |
| (> 1024px)              | Persistent 3-column chat layout (Sidebar + Main + Citation Drawer).  |
+-------------------------+---------------------------------------------------------------------+
| Tablet                  | Collapsible accordion mode for Comparison Showcase.                 |
| (768px - 1024px)        | Slide-over drawer for Chat Sessions & Citation metadata.            |
+-------------------------+---------------------------------------------------------------------+
| Mobile                  | Tabbed segmented control switching between [Traditional] and        |
| (< 768px)               | [ContextGraph] views. Bottom sheet navigation for Citation audits.   |
+-------------------------+---------------------------------------------------------------------+
```

---

## 🚀 Verification & Next Steps
1. **Interactive Demo**: Launch [`Docs/wireframe_prototype.html`](file:///C:/Users/Laptopadmin/Desktop/context-engineering/Docs/wireframe_prototype.html) directly in any modern browser to test tab transitions, role switches, and citation interactions.
2. **React Implementation**: Component scaffolds match the directory structure:
   - `src/components/compare/ComparisonShowcase.tsx`
   - `src/components/chat/ChatLayout.tsx`
   - `src/components/citation/CitationDrawer.tsx`
   - `src/components/analytics/AnalyticsDashboard.tsx`
   - `src/components/admin/AdminGovernancePanel.tsx`
   - `src/components/auth/LoginView.tsx`
