import { MessageCircle, Scale, BarChart3, UserCog, Menu, X } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Tabs from "./components/widgets/Tabs";
import { Users, KeyRound, FileClock, UploadCloud } from "lucide-react";
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
import LoginScreen from "./components/auth/LoginScreen";
import { useAppState } from "./state/AppState";
import { ROLE_PERMISSIONS } from "./data/rbac";
import { API_BASE } from "./services/api";

function AdminView() {
  const { adminSubTab, setAdminSubTab } = useAppState();
  const tabNames = [
    { label: "User Profile Management", icon: Users },
    { label: "Role Access Matrix", icon: KeyRound },
    { label: "Security & Audit Logs", icon: FileClock },
    { label: "Authorized Ingest & Pipeline", icon: UploadCloud },
  ];
  return (
    <div>
      <h2 className="stHeader2">Admin Panel &amp; Enterprise RBAC Governance</h2>
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
  const { isAuthenticated, activeUser, activeTab, setActiveTab, activePage, isSidebarOpen, toggleSidebar } = useAppState();

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  const role = activeUser?.role || "Compliance & Regulatory Officer";
  const perms = ROLE_PERMISSIONS[role] || {};

  const canCompare = perms.can_access_compare_tab ?? true;
  const canAnalytics = perms.can_access_analytics_tab ?? true;
  const canAdmin = perms.can_view_admin_panel ?? false;

  const tabNames = [{ label: "Chat", icon: MessageCircle }];
  if (canCompare) tabNames.push({ label: "Compare", icon: Scale });
  if (canAnalytics) tabNames.push({ label: "Analytics", icon: BarChart3 });
  if (canAdmin) tabNames.push({ label: "Admin & Governance", icon: UserCog });

  const clampedTab = activeTab >= tabNames.length ? 0 : activeTab;

  let idx = 0;
  const chatIdx = idx++;
  const compareIdx = canCompare ? idx++ : -1;
  const analyticsIdx = canAnalytics ? idx++ : -1;
  const adminIdx = canAdmin ? idx++ : -1;

  return (
    <div className="stApp" data-sidebar-collapsed={!isSidebarOpen}>
      {/* Backdrop overlay for mobile & tablet drawer */}
      {isSidebarOpen && (
        <div
          className="stSidebarBackdrop"
          onClick={toggleSidebar}
          aria-label="Close sidebar backdrop"
        />
      )}

      <Sidebar />

      <div className="stMain">
        {/* Mobile & tablet top navigation bar */}
        <header className="stMobileHeader">
          <button
            type="button"
            className="stMobileNavToggle"
            onClick={toggleSidebar}
            title={isSidebarOpen ? "Close menu" : "Open navigation menu"}
            aria-label="Toggle navigation menu"
            aria-expanded={isSidebarOpen}
          >
            {isSidebarOpen ? <X size={18} strokeWidth={1.75} /> : <Menu size={18} strokeWidth={1.75} />}
          </button>
          <div className="stMobileHeader-center">
            <span className="stMobileHeader-brand">
              AMC <span>Context</span>
            </span>
            <span className="stMobileHeader-badge">
              {activePage && activePage !== "app"
                ? activePage.replace(/^\d+_/, "")
                : tabNames[clampedTab]?.label}
            </span>
          </div>
          <div className="stMobileHeader-right">
            <span className="stMobileHeader-userRole" title={role}>
              {activeUser?.full_name ? activeUser.full_name.split(" ")[0] : "User"}
            </span>
          </div>
        </header>

        <header className="stHeader">
          {(!activePage || activePage === "app") && (clampedTab === chatIdx || clampedTab === compareIdx) && (
            <div className="cg-top-status-indicator" title={`Backend: ${API_BASE} | Role: ${role}`}>
              <span className="cg-status-dot cg-status-dot--success" />
              <span className="cg-top-status-text">Backend: <code>{API_BASE}</code></span>
              <span className="cg-top-status-sep">|</span>
              <span className="cg-top-status-text">Role: <span className="cg-top-status-role">{role}</span></span>
            </div>
          )}
        </header>
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
                {clampedTab === chatIdx && <ChatTab />}
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
