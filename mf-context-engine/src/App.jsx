import Sidebar from "./components/Sidebar";
import Tabs from "./components/widgets/Tabs";
import ChatTab from "./views/ChatTab";
import CompareTab from "./views/CompareTab";
import AnalyticsTab from "./views/AnalyticsTab";
import AdminUsersTab from "./views/admin/AdminUsersTab";
import AdminRbacTab from "./views/admin/AdminRbacTab";
import AdminAuditTab from "./views/admin/AdminAuditTab";
import AdminIngestTab from "./views/admin/AdminIngestTab";
import ScorecardPage from "./views/pages/ScorecardPage";
import ViolationsPage from "./views/pages/ViolationsPage";
import FundsPage from "./views/pages/FundsPage";
import RemediationPage from "./views/pages/RemediationPage";
import MultiRegionPage from "./views/pages/MultiRegionPage";
import { useAppState } from "./state/AppState";
import { ROLE_PERMISSIONS } from "./data/rbac";
import { API_BASE } from "./services/api";

function AdminView() {
  const { adminSubTab, setAdminSubTab } = useAppState();
  const tabNames = [
    "[USERS] User Profile Management",
    "[RBAC] Role Access Matrix",
    "[AUDIT] Security & Audit Logs",
    "[INGEST] Authorized Ingest & Pipeline",
  ];
  return (
    <div>
      <h2 className="stHeader2">👥 Admin Panel &amp; Enterprise RBAC Governance</h2>
      <div className="stCaption">
        Manage user profiles, assign AMC organizational roles, inspect clearance boundaries, and view audit trails.
      </div>
      <Tabs tabs={tabNames} active={adminSubTab} onChange={setAdminSubTab} />
      <div className="stTabs-panel">
        {adminSubTab === 0 && <AdminUsersTab />}
        {adminSubTab === 1 && <AdminRbacTab />}
        {adminSubTab === 2 && <AdminAuditTab />}
        {adminSubTab === 3 && <AdminIngestTab />}
      </div>
    </div>
  );
}

export default function App() {
  const { activeUser, activeTab, setActiveTab, activePage, isSidebarOpen, toggleSidebar } = useAppState();
  const role = activeUser?.role || "Compliance & Regulatory Officer";
  const perms = ROLE_PERMISSIONS[role] || {};

  const canCompare = perms.can_access_compare_tab ?? true;
  const canAnalytics = perms.can_access_analytics_tab ?? true;
  const canAdmin = perms.can_view_admin_panel ?? false;

  const tabNames = ["💬 Chat"];
  if (canCompare) tabNames.push("⚖️ Compare");
  if (canAnalytics) tabNames.push("📊 Analytics");
  if (canAdmin) tabNames.push("👥 Admin & Governance");

  const clampedTab = activeTab >= tabNames.length ? 0 : activeTab;

  let idx = 0;
  const chatIdx = idx++;
  const compareIdx = canCompare ? idx++ : -1;
  const analyticsIdx = canAnalytics ? idx++ : -1;
  const adminIdx = canAdmin ? idx++ : -1;

  return (
    <div className="stApp" data-sidebar-collapsed={!isSidebarOpen}>
      {!isSidebarOpen && (
        <button
          className="stSidebarOpenButton"
          onClick={toggleSidebar}
          title="Expand sidebar"
          aria-label="Expand sidebar"
        >
          »
        </button>
      )}

      <Sidebar />

      <div className="stMain">
        <header className="stHeader" />
        <div className="block-container stAppBottom">
          {activePage === "01_Scorecard" && <ScorecardPage />}
          {activePage === "02_Violations" && <ViolationsPage />}
          {activePage === "03_Funds" && <FundsPage />}
          {activePage === "04_Remediation" && <RemediationPage />}
          {activePage === "05_Multi_Region" && <MultiRegionPage />}
          {(!activePage || activePage === "app") && (
            <>
              <Tabs tabs={tabNames} active={clampedTab} onChange={setActiveTab} />
              <div className="stTabs-panel">
                {clampedTab === chatIdx && (
                  <div>
                    <div className="stCaption">🟢 Backend: {API_BASE} | Role: {role}</div>
                    <ChatTab />
                  </div>
                )}
                {canCompare && clampedTab === compareIdx && <CompareTab role={role} />}
                {canAnalytics && clampedTab === analyticsIdx && <AnalyticsTab />}
                {canAdmin && clampedTab === adminIdx && <AdminView />}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
