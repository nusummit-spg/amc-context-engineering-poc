import { MessageCircle, Scale, BarChart3, UserCog, Menu, X } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Tabs from "./components/widgets/Tabs";
import { Users, KeyRound, FileClock, UploadCloud, AlertCircle } from "lucide-react";
import ChatTab from "./views/ChatTab";
import CompareTab from "./views/CompareTab";
import AnalyticsTab from "./views/AnalyticsTab";
import AdminUsersTab from "./views/admin/AdminUsersTab";
import AdminRbacTab from "./views/admin/AdminRbacTab";
import AdminAuditTab from "./views/admin/AdminAuditTab";
import AdminIngestTab from "./views/admin/AdminIngestTab";
import AdminFeedbackIssuesTab from "./views/admin/AdminFeedbackIssuesTab";
import MyFeedbackPage from "./views/pages/MyFeedbackPage";
import ScorecardPage from "./views/pages/ScorecardPage";
import ViolationsPage from "./views/pages/ViolationsPage";
import FundsPage from "./views/pages/FundsPage";
import RemediationPage from "./views/pages/RemediationPage";
import MultiRegionPage from "./views/pages/MultiRegionPage";
import GovernancePage from "./views/pages/GovernancePage";
import LoginScreen from "./components/auth/LoginScreen";
import { useAppState } from "./state/AppState";
import { ROLE_PERMISSIONS } from "./data/rbac";
import { FEATURES } from "./config/features";

function AdminView() {
  const { adminSubTab, setAdminSubTab } = useAppState();
  const tabNames = [
    { label: "User Profile Management", icon: Users },
    { label: "Role Access Matrix", icon: KeyRound },
    { label: "Security & Audit Logs", icon: FileClock },
    { label: "Authorized Ingest & Pipeline", icon: UploadCloud },
  ];

  const clampedSubTab = adminSubTab >= tabNames.length ? 0 : adminSubTab;

  return (
    <div>
      <h2 className="stHeader2">Admin &amp; Governance</h2>
      <div className="stCaption">
        Manage user profiles, assign AMC organizational roles, review security audit trails, and oversee document ingestion pipelines.
      </div>
      <Tabs tabs={tabNames} active={clampedSubTab} onChange={setAdminSubTab} />
      <div className="stTabs-panel">
        {clampedSubTab === 0 && <AdminUsersTab />}
        {clampedSubTab === 1 && <AdminRbacTab />}
        {clampedSubTab === 2 && <AdminAuditTab />}
        {clampedSubTab === 3 && <AdminIngestTab />}
      </div>
    </div>
  );
}

export default function App() {
  const { isAuthenticated, activeUser, activeTab, activePage, isSidebarOpen, toggleSidebar } = useAppState();

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
                ? (activePage === "feedback_triage" || activePage === "admin_feedback_issues"
                    ? "Feedback & Triage"
                    : activePage === "my_feedback"
                    ? "My Feedback"
                    : activePage.replace(/^\d+_/, ""))
                : tabNames[clampedTab]?.label}
            </span>
          </div>
          <div className="stMobileHeader-right">
            <span className="stMobileHeader-userRole" title={role}>
              {activeUser?.full_name ? activeUser.full_name.split(" ")[0] : "User"}
            </span>
          </div>
        </header>

        <div className="block-container stAppBottom">
          {activePage === "01_Scorecard" && <ScorecardPage />}
          {activePage === "02_Violations" && <ViolationsPage />}
          {activePage === "03_Funds" && <FundsPage />}
          {activePage === "04_Remediation" && <RemediationPage />}
          {activePage === "05_Multi_Region" && <MultiRegionPage />}
          {activePage === "06_Governance" && <GovernancePage />}
          {activePage === "my_feedback" && <MyFeedbackPage />}
          {(activePage === "feedback_triage" || activePage === "admin_feedback_issues") && (
            canAdmin ? (
              <AdminFeedbackIssuesTab />
            ) : (
              <div style={{ padding: "2.5rem 1rem", maxWidth: "600px", margin: "0 auto" }}>
                <div className="stAlert stAlert--error" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <AlertCircle size={22} />
                  <div>
                    <strong style={{ display: "block", marginBottom: "0.25rem" }}>Access Denied (403)</strong>
                    <span>Administrator privileges are required to access Feedback &amp; Triage.</span>
                  </div>
                </div>
              </div>
            )
          )}
          {(!activePage || activePage === "app") && (
            <div className="stTabs-panel">
              {clampedTab === chatIdx && <ChatTab />}
              {canCompare && clampedTab === compareIdx && <CompareTab role={role} />}
              {canAnalytics && clampedTab === analyticsIdx && <AnalyticsTab />}
              {canAdmin && clampedTab === adminIdx && <AdminView />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
