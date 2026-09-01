# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Implementation Plan — Enterprise Role-Based Access Control (RBAC) & AMC Admin Panel

This implementation plan details the architecture and step-by-step implementation for **Role-Based Access Control (RBAC)** in the **AMC Context Engineering Platform**, designed specifically from an **Asset Management Company (AMC) POV**.

---

## User Review Required

> [!IMPORTANT]
> **5 Industry-Grade AMC Roles Selected**:
> We have modeled 5 distinct AMC organizational personas with granular access control matrices:
> 
> 1. 🛡️ **`Compliance & Regulatory Officer`** *(Level 1 — Unrestricted Access)*:
>    - **Scope**: Full access to all SEBI circulars, internal compliance audit logs, unredacted audit metrics, Cypher read tools, and full administrative panel.
> 2. 📈 **`Fund Manager / Portfolio Manager`** *(Level 2 — Investment Scope)*:
>    - **Scope**: Fund performance, holdings, EBITDA/Revenue financial metrics, ESG disclosures, and benchmark comparisons. Restricted from raw investor PII and internal compliance audit logs.
> 3. 🌿 **`ESG & Sustainability Analyst`** *(Level 3 — ESG & Climate Scope)*:
>    - **Scope**: ESG sustainability reports, BRSR filings, decarbonization targets, carbon emissions. Restricted from financial trading logs and investor PII.
> 4. 💼 **`Sales & Distribution Manager`** *(Level 4 — Commercial Scope)*:
>    - **Scope**: Scheme Information Documents (SID/KIM), Total Expense Ratio (TER), Exit load, NAV history, investor FAQs. Strictly masked from internal compliance notes and Cypher tools.
> 5. 👤 **`Retail Investor / Public Client`** *(Level 5 — Restricted Public Scope)*:
>    - **Scope**: Public scheme facts only. Mandatory SEBI Risk Disclaimer enforced, SEBI RIA Financial Advice Shield strictly active (cannot receive personalized buy/sell recommendations), all PII 100% scrubbed. Restricted from Compare, Analytics, and Admin tabs.

---

## Proposed Changes

### 1. RBAC Engine & User Storage Module

#### [NEW] [rbac.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/rbac.py)
- Defines the `Role` enum, role metadata, domain access matrix, and feature permission matrix.
- Implements `RBACManager` for loading, saving, and managing user profiles (`config/users_rbac.json`).
- Pre-populates 5 default user profiles mapping to the 5 AMC roles.
- Implements `filter_chunks_by_role(hits, role)` and `filter_graph_by_role(graph_result, role)` to enforce data boundary scoping during retrieval.

---

### 2. Streamlit UI Integration & Admin Panel

#### [MODIFY] [app.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py)
- Adds a **Sidebar Active Profile Switcher** allowing instant switching between user roles with dynamic badge indicators.
- Adds a **4th Tab**: `"👥 Admin & RBAC Governance"` (accessible to Compliance & Admin roles).
- Enforces tab visibility: Hides Analytics, Compare, and Admin tabs for restricted roles like `Retail Investor`.

#### [NEW] [admin_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/admin_view.py)
- Builds the Admin Panel UI:
  - **User Management Table**: List all registered users, roles, departments, and status.
  - **Add/Edit User Form**: Create new users with assigned AMC roles.
  - **Role Matrix Inspection View**: Interactive visual matrix showing domain permissions, tab access, and security rules per role.
  - **System Audit Log Inspector**: View real-time security events, blocked queries, and PII redaction metrics.

---

### 3. Retrieval Engine Access Scoping

#### [MODIFY] [chat_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py)
- Passes active user profile & role to `retrieval.hybrid_graphrag()`.
- Renders active user role badge in chat header.

#### [MODIFY] [compare_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/compare_view.py)
- Passes active user profile & role to `taxonomy_retrieval.run_v2_dual_regime_taxonomy()`.

#### [MODIFY] [retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)
- Calls `rbac.filter_chunks_by_role(hits, role)` and `rbac.filter_graph_by_role(graph_result, role)` before prompt assembly.

#### [MODIFY] [taxonomy_retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)
- Filters taxonomy graph nodes and vector chunks according to role clearance.

---

## Verification Plan

### Automated Tests
Create `scratch/test_rbac_governance.py` verifying:
1. `RBACManager` user profile creation, role assignment, and JSON persistence.
2. `filter_chunks_by_role` ensuring `Retail Investor` role cannot see internal compliance notes.
3. `filter_graph_by_role` verifying domain restrictions per AMC role.
4. End-to-end `retrieval.py` query test with different active roles confirming differential access.

### Manual Verification
1. Launch Streamlit (`streamlit run app.py`).
2. Switch between `Compliance Officer`, `Fund Manager`, `ESG Analyst`, `Sales Manager`, and `Retail Investor` profiles in the sidebar.
3. Verify that the 4th `"👥 Admin & RBAC Governance"` tab appears for Compliance Officer and is hidden for Retail Investor.
4. Create a new user in the Admin Panel and verify role switching works seamlessly.
