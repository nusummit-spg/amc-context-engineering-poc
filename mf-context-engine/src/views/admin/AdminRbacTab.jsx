import DataFrame from "../../components/widgets/DataFrame";
import { AMCRole, ROLE_DOMAIN_ACCESS, ROLE_PERMISSIONS } from "../../data/rbac";

export default function AdminRbacTab() {
  const rows = Object.values(AMCRole).map((role) => {
    const domains = [...(ROLE_DOMAIN_ACCESS[role] || [])].sort().join(", ");
    const perms = ROLE_PERMISSIONS[role] || {};
    return {
      "Role Name": role,
      "Authorized Domains": domains,
      "Admin Access": perms.can_view_admin_panel ? "YES" : "NO",
      "Audit Logs": perms.can_view_audit_logs ? "YES" : "NO",
      "Unredacted PII": perms.can_view_unredacted_pii ? "YES" : "NO",
      "Cypher Tool": perms.can_run_cypher_tools ? "YES" : "NO",
      "Compare & Analytics": perms.can_access_compare_tab ? "YES" : "NO",
    };
  });

  return (
    <div>
      <h3 className="stSubheader">AMC Organizational Clearance &amp; Access Matrix</h3>
      <DataFrame
        columns={["Role Name", "Authorized Domains", "Admin Access", "Audit Logs", "Unredacted PII", "Cypher Tool", "Compare & Analytics"]}
        rows={rows}
      />

      <blockquote className="stMarkdownBlockquote">
        <b>Security Policy</b>:
        <br />- <b>Level 1 (Compliance Officer)</b>: Complete supervisory clearance across all domains, audit logs, and unredacted PII.
        <br />- <b>Level 2 (Fund Manager)</b>: Full investment analytics, scheme performance, holdings, and ESG disclosures.
        <br />- <b>Level 3 (ESG Analyst)</b>: Dedicated ESG sustainability, BRSR, and decarbonization report scope.
        <br />- <b>Level 4 (Sales Manager)</b>: Customer-facing SID/KIM, NAV, and TER document scope. Masked from internal compliance notes.
        <br />- <b>Level 5 (Retail Investor)</b>: Public facts only. Mandatory SEBI Risk Disclaimer enforced, SEBI RIA Advice Shield active.
      </blockquote>
    </div>
  );
}
