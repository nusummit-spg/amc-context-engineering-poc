# Role-Based Access Control (RBAC) Guide

## 1. Supported Roles & Permissions

The AMC Compliance Platform implements granular RBAC across 5 primary roles:

| Role | Label | Default User | Accessible Tabs |
|---|---|---|---|
| `COMPLIANCE_OFFICER` | Chief Compliance Officer | Sarah Williams | Chat, Compare, Scorecard, Violations, Funds, Remediation, Multi-Region, Admin |
| `FUND_MANAGER` | Fund Manager | John Patterson | Chat, Compare, Scorecard, Funds, Analytics |
| `ESG_ANALYST` | ESG Analyst | Maria Rodriguez | Chat, Compare, Scorecard, Analytics |
| `SALES_MANAGER` | Sales & Distribution | David Chen | Chat, Compare, Funds |
| `RETAIL_INVESTOR` | Retail Investor | Alice Johnson | Chat, Compare |

---

## 2. Tab Filtering & Switcher Integration

- Navigation tabs are filtered via `getVisibleTabs(user.role)`.
- The `UserProfileSwitcher` component permits instant switching between user personas to test and demonstrate role boundaries.
