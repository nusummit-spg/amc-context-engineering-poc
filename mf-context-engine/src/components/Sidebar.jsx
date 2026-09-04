import { useState, useRef, useEffect } from "react";
import { useAppState } from "../state/AppState";
import { useToast } from "./widgets/Toast";

const PAGES = [
  { id: "app", label: "Chat Assistant", shortLabel: "Chat", icon: "💬" },
  { id: "01_Scorecard", label: "Compliance Scorecard", shortLabel: "Scorecard", icon: "🎯" },
  { id: "02_Violations", label: "Violations Explorer", shortLabel: "Violations", icon: "⚠️" },
  { id: "03_Funds", label: "Fund Schemes Matrix", shortLabel: "Funds", icon: "🏢" },
  { id: "04_Remediation", label: "Remediation & SLA", shortLabel: "Remediation", icon: "🛠️" },
  { id: "05_Multi_Region", label: "Multi-Jurisdiction", shortLabel: "Multi-Region", icon: "🌐" },
];

export default function Sidebar() {
  const {
    activeUser,
    chatSessions,
    chatSessionId,
    loadChatSession,
    deleteChatSession,
    startNewChatSession,
    indexingTasks,
    clearCache,
    isCacheClearing,
    activePage,
    setActivePage,
    isSidebarOpen,
    toggleSidebar,
    logout,
  } = useAppState();
  const pushToast = useToast();

  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const accountRef = useRef(null);

  // Close account popover on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (accountRef.current && !accountRef.current.contains(e.target)) {
        setIsAccountMenuOpen(false);
      }
    }
    if (isAccountMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isAccountMenuOpen]);

  const handleClearCache = async () => {
    const ok = await clearCache();
    if (ok) {
      pushToast("Intent Cache cleared cleanly! Next query will execute full LLM synthesis.", "⚡");
    } else {
      pushToast("Intent Cache flushed locally.", "⚡");
    }
    setIsAccountMenuOpen(false);
  };

  const handleLogout = () => {
    setIsAccountMenuOpen(false);
    logout();
    if (typeof window !== "undefined" && window.innerWidth <= 1024) {
      toggleSidebar();
    }
  };

  const activeIndexing = indexingTasks.filter((t) => t.status === "PROCESSING").slice(0, 3);

  const sessions = Object.entries(chatSessions)
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .slice(0, 30)
    .map(([id, s]) => {
      const firstUserMsg = (s.history || []).find((m) => m.role === "user");
      const firstQuery = s.title || firstUserMsg?.content || "New conversation";
      const preview = firstQuery.length > 30 ? firstQuery.slice(0, 30) + "…" : firstQuery;
      return { session_id: id, preview, turn_count: Math.floor((s.history || []).length / 2) };
    });

  const handlePageSelect = (pageId) => {
    setActivePage(pageId);
    if (typeof window !== "undefined" && window.innerWidth <= 1024) {
      toggleSidebar();
    }
  };

  const handleSessionSelect = (sessionId) => {
    loadChatSession(sessionId);
    if (activePage !== "app") {
      setActivePage("app");
    }
    if (typeof window !== "undefined" && window.innerWidth <= 1024) {
      toggleSidebar();
    }
  };

  const handleNewSession = () => {
    startNewChatSession();
    if (activePage !== "app") {
      setActivePage("app");
    }
    if (typeof window !== "undefined" && window.innerWidth <= 1024) {
      toggleSidebar();
    }
  };

  const initials = (activeUser?.full_name || activeUser?.username || "U")
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <aside className={`stSidebar ${isSidebarOpen ? "" : "stSidebar--collapsed"}`} aria-label="Sidebar navigation">
      {/* ── 1. Top Header Row with Brand & Collapse Toggle ── */}
      <div className="cg-sidebar-header">
        <div className="cg-sidebar-brand" title="AMC Context Engine">
          <span className="cg-sidebar-logo">AMC</span>
          <span className="cg-sidebar-brand-text">Context Engine</span>
        </div>
        <button
          type="button"
          className="cg-sidebar-toggle-btn"
          onClick={toggleSidebar}
          title={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          aria-label={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {isSidebarOpen ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2" />
              <path d="M9 3v18" />
              <path d="m14 9-3 3 3 3" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2" />
              <path d="M9 3v18" />
              <path d="m13 15 3-3-3-3" />
            </svg>
          )}
        </button>
      </div>

      {/* ── 2. Prominent ChatGPT-Style New Chat Button ── */}
      <div className="cg-new-chat-wrapper">
        <button
          type="button"
          className="cg-new-chat-btn"
          onClick={handleNewSession}
          title="Start a new chat conversation"
        >
          <span className="cg-new-chat-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </span>
          <span className="cg-new-chat-text">New chat</span>
        </button>
      </div>

      {/* ── 3. Navigation / Pages Section ── */}
      <div className="cg-nav-section">
        <div className="cg-section-label">Navigation</div>
        <nav className="cg-nav-list" aria-label="Main Navigation">
          {PAGES.map((p) => {
            const isActive = activePage === p.id;
            return (
              <button
                key={p.id}
                type="button"
                className={`cg-nav-item ${isActive ? "active" : ""}`}
                onClick={() => handlePageSelect(p.id)}
                title={p.label}
              >
                <span className="cg-nav-icon">{p.icon}</span>
                <span className="cg-nav-label">{p.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* ── 4. Chat History / Sessions Section ── */}
      <div className="cg-sessions-section">
        <div className="cg-sessions-header">
          <span className="cg-section-label">Recent Chats</span>
          {sessions.length > 0 && <span className="cg-session-count">{sessions.length}</span>}
        </div>
        <div className="cg-sessions-scroll">
          {sessions.length === 0 ? (
            <div className="cg-empty-sessions">No conversations yet</div>
          ) : (
            sessions.map((s) => {
              const isCurrent = s.session_id === chatSessionId && (!activePage || activePage === "app");
              return (
                <div
                  key={s.session_id}
                  className={`cg-session-item ${isCurrent ? "active" : ""}`}
                  onClick={() => handleSessionSelect(s.session_id)}
                  title={s.preview}
                >
                  <span className="cg-session-icon">{isCurrent ? "🟢" : "💬"}</span>
                  <span className="cg-session-title">{s.preview}</span>
                  <button
                    type="button"
                    className="cg-session-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteChatSession(s.session_id);
                      pushToast("Session deleted", "🗑️");
                    }}
                    title="Delete chat session"
                    aria-label="Delete chat session"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 6h18" />
                      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ── 5. Background Indexing Tasks Indicator (Compact) ── */}
      {activeIndexing.length > 0 && (
        <div className="cg-indexing-box" title={`Indexing ${activeIndexing[0].filename} (${activeIndexing[0].stage})`}>
          <div className="cg-indexing-head">
            <span className="cg-indexing-pulse" />
            <span className="cg-indexing-title">Indexing {activeIndexing.length} file(s)</span>
          </div>
          <div className="cg-indexing-name">{activeIndexing[0].filename}</div>
          <div className="cg-indexing-stage">{activeIndexing[0].stage}</div>
        </div>
      )}

      {/* ── 6. Bottom User Account Profile & Popover Menu ── */}
      <div className="cg-account-section" ref={accountRef}>
        {isAccountMenuOpen && (
          <div className="cg-account-popover" role="dialog" aria-label="Account Settings">
            <div className="cg-popover-header">
              <div className="cg-popover-avatar">{initials}</div>
              <div className="cg-popover-user">
                <div className="cg-popover-name">{activeUser?.full_name || "AMC Officer"}</div>
                <div className="cg-popover-email">{activeUser?.email || `${activeUser?.username || "user"}@amc.com`}</div>
              </div>
            </div>

            <div className="cg-popover-divider" />

            <div className="cg-popover-role-card">
              <div className="cg-popover-role-row">
                <span className="cg-popover-role-label">Role:</span>
                <span className="cg-popover-role-val">{activeUser?.role || "Compliance Officer"}</span>
              </div>
              <div className="cg-popover-role-row">
                <span className="cg-popover-role-label">Dept:</span>
                <span className="cg-popover-role-val">{activeUser?.department || "General"}</span>
              </div>
            </div>

            <div className="cg-popover-divider" />

            <button
              type="button"
              className="cg-popover-item"
              onClick={handleClearCache}
              disabled={isCacheClearing}
              title="Flush in-memory and disk intent cache so next query executes fresh LLM synthesis"
            >
              <span className="cg-popover-item-icon">⚡</span>
              <span>{isCacheClearing ? "Flushing Cache..." : "Clear Intent Cache"}</span>
            </button>

            <button
              type="button"
              className="cg-popover-item cg-popover-item--danger"
              onClick={handleLogout}
              title="Sign out of AMC Context Engine"
            >
              <span className="cg-popover-item-icon">🚪</span>
              <span>Sign out</span>
            </button>
          </div>
        )}

        <button
          type="button"
          className={`cg-account-btn ${isAccountMenuOpen ? "active" : ""}`}
          onClick={() => setIsAccountMenuOpen((prev) => !prev)}
          title={`${activeUser?.full_name || "User"} (${activeUser?.role || "Role"})`}
          aria-expanded={isAccountMenuOpen}
        >
          <div className="cg-account-avatar">{initials}</div>
          <div className="cg-account-info">
            <div className="cg-account-name">{activeUser?.full_name || "AMC User"}</div>
            <div className="cg-account-role">{activeUser?.role ? activeUser.role.split("/")[0].trim() : "Compliance"}</div>
          </div>
          <div className="cg-account-more">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="1" />
              <circle cx="19" cy="12" r="1" />
              <circle cx="5" cy="12" r="1" />
            </svg>
          </div>
        </button>
      </div>
    </aside>
  );
}
