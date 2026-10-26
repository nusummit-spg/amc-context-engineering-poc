// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// ===========================================================================

/**
 * AMC Context Engineering — Enterprise Role-Based Access Control (RBAC) Engine
 * Defines AMC Organizational Roles, Domain Authorization Scopes, Feature Permissions,
 * and Default User Profiles.
 */

export const AMCRole = {
  COMPLIANCE_OFFICER: "Compliance & Regulatory Officer",
  FUND_MANAGER: "Fund Manager / Portfolio Manager",
  ESG_ANALYST: "ESG & Sustainability Analyst",
  SALES_MANAGER: "Sales & Distribution Manager",
  RETAIL_INVESTOR: "Retail Investor / Public Client",
};

export const ROLE_DOMAIN_ACCESS = {
  [AMCRole.COMPLIANCE_OFFICER]: [
    "sebi_regulation",
    "esg_sustainability",
    "financial_performance",
    "fund_performance",
    "corporate_governance",
  ],
  [AMCRole.FUND_MANAGER]: [
    "sebi_regulation",
    "esg_sustainability",
    "financial_performance",
    "fund_performance",
    "corporate_governance",
  ],
  [AMCRole.ESG_ANALYST]: [
    "esg_sustainability",
    "sebi_regulation",
    "corporate_governance",
  ],
  [AMCRole.SALES_MANAGER]: [
    "fund_performance",
    "sebi_regulation",
    "financial_performance",
  ],
  [AMCRole.RETAIL_INVESTOR]: [
    "fund_performance",
    "sebi_regulation",
  ],
};

export const ROLE_PERMISSIONS = {
  [AMCRole.COMPLIANCE_OFFICER]: {
    can_view_admin_panel: true,
    can_view_audit_logs: true,
    can_view_unredacted_pii: true,
    can_run_cypher_tools: true,
    enforce_sebi_advice_shield: true,
    can_access_compare_tab: true,
    can_access_analytics_tab: true,
    can_review_answers: true,
  },
  [AMCRole.FUND_MANAGER]: {
    can_view_admin_panel: false,
    can_view_audit_logs: false,
    can_view_unredacted_pii: false,
    can_run_cypher_tools: true,
    enforce_sebi_advice_shield: true,
    can_access_compare_tab: true,
    can_access_analytics_tab: true,
    can_review_answers: true,
  },
  [AMCRole.ESG_ANALYST]: {
    can_view_admin_panel: false,
    can_view_audit_logs: false,
    can_view_unredacted_pii: false,
    can_run_cypher_tools: false,
    enforce_sebi_advice_shield: true,
    can_access_compare_tab: true,
    can_access_analytics_tab: true,
    can_review_answers: false,
  },
  [AMCRole.SALES_MANAGER]: {
    can_view_admin_panel: false,
    can_view_audit_logs: false,
    can_view_unredacted_pii: false,
    can_run_cypher_tools: false,
    enforce_sebi_advice_shield: true,
    can_access_compare_tab: false,
    can_access_analytics_tab: false,
    can_review_answers: false,
  },
  [AMCRole.RETAIL_INVESTOR]: {
    can_view_admin_panel: false,
    can_view_audit_logs: false,
    can_view_unredacted_pii: false,
    can_run_cypher_tools: false,
    enforce_sebi_advice_shield: true,
    can_access_compare_tab: false,
    can_access_analytics_tab: false,
    can_review_answers: false,
  },
};

export const DEFAULT_USER_PROFILES = [
  {
    username: "sarah.compliance",
    full_name: "Sarah Kapoor",
    role: AMCRole.COMPLIANCE_OFFICER,
    department: "Regulatory & Legal Compliance",
    email: "s.kapoor@amc.com",
    status: "Active",
  },
  {
    username: "vikram.pm",
    full_name: "Vikram Mehta",
    role: AMCRole.FUND_MANAGER,
    department: "Equity Investment Management",
    email: "v.mehta@amc.com",
    status: "Active",
  },
  {
    username: "ananya.esg",
    full_name: "Ananya Sharma",
    role: AMCRole.ESG_ANALYST,
    department: "Sustainable Investing & ESG",
    email: "a.sharma@amc.com",
    status: "Active",
  },
  {
    username: "rahul.sales",
    full_name: "Rahul Verma",
    role: AMCRole.SALES_MANAGER,
    department: "Institutional & Retail Distribution",
    email: "r.verma@amc.com",
    status: "Active",
  },
  {
    username: "priya.investor",
    full_name: "Priya Nair",
    role: AMCRole.RETAIL_INVESTOR,
    department: "External Client Portal",
    email: "p.nair@public.com",
    status: "Active",
  },
];
