import { useState, useRef, useEffect } from "react";
import {
  MessageSquare,
  ShieldCheck,
  AlertTriangle,
  LayoutGrid,
  Wrench,
  Globe2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
  Zap,
  LogOut,
  MoreHorizontal,
} from "lucide-react";
import { useAppState } from "../state/AppState";
import { useToast } from "./widgets/Toast";

const PAGES = [
  { id: "app", label: "Chat Assistant", shortLabel: "Chat", Icon: MessageSquare },
  { id: "01_Scorecard", label: "Compliance Scorecard", shortLabel: "Scorecard", Icon: ShieldCheck },
  { id: "02_Violations", label: "Violations Explorer", shortLabel: "Violations", Icon: AlertTriangle },
  { id: "03_Funds", label: "Fund Schemes Matrix", shortLabel: "Funds", Icon: LayoutGrid },
  { id: "04_Remediation", label: "Remediation & SLA", shortLabel: "Remediation", Icon: Wrench },
  { id: "05_Multi_Region", label: "Multi-Jurisdiction", shortLabel: "Multi-Region", Icon: Globe2 },
];

export default function Sidebar() {
  const {
    activeUser,
    chatSessions,
    chatSessionId,
    animatingSessionId,
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
      pushToast("Intent Cache cleared cleanly! Next query will execute full LLM synthesis.");
    } else {
      pushToast("Intent Cache flushed locally.");
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
      const title = s.title || (firstUserMsg?.content ? (firstUserMsg.content.length > 50 ? firstUserMsg.content.slice(0, 50) + "…" : firstUserMsg.content) : "New Conversation");
      const words = title.split(/\s+/).filter(Boolean);
      return {
        session_id: id,
        title,
        words,
        turn_count: Math.floor((s.history || []).length / 2),
      };
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
          {isSidebarOpen ? <PanelLeftClose size={18} strokeWidth={1.75} /> : <PanelLeftOpen size={18} strokeWidth={1.75} />}
        </button>
      </div>

      {/* ── 2. Prominent New Chat Button ── */}
      <div className="cg-new-chat-wrapper">
        <button
          type="button"
          className="cg-new-chat-btn"
          onClick={handleNewSession}
          title="Start a new chat conversation"
        >
          <span className="cg-new-chat-icon">
            <Plus size={16} strokeWidth={2.25} />
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
            const Icon = p.Icon;
            return (
              <button
                key={p.id}
                type="button"
                className={`cg-nav-item ${isActive ? "active" : ""}`}
                onClick={() => handlePageSelect(p.id)}
                title={p.label}
              >
                <span className="cg-nav-icon"><Icon size={18} strokeWidth={1.75} /></span>
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
                  title={s.title}
                >
                  <span className={`cg-session-icon ${isCurrent ? "cg-session-icon--current" : ""}`}>
                    {isCurrent ? <span className="cg-status-dot cg-status-dot--success" /> : <MessageSquare size={14} strokeWidth={1.75} />}
                  </span>
                  {animatingSessionId === s.session_id ? (
                    <span className="cg-session-title cg-session-title--animating">
                      {s.words.map((word, idx) => (
                        <span
                          key={idx}
                          className="cg-session-title-word"
                          style={{ animationDelay: `${idx * 65}ms` }}
                        >
                          {word}{idx < s.words.length - 1 ? "\u00A0" : ""}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="cg-session-title">{s.title}</span>
                  )}
                  <button
                    type="button"
                    className="cg-session-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteChatSession(s.session_id);
                      pushToast("Session deleted");
                    }}
                    title="Delete chat session"
                    aria-label="Delete chat session"
                  >
                    <Trash2 size={13} strokeWidth={1.75} />
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
              <span className="cg-popover-item-icon"><Zap size={16} strokeWidth={1.75} /></span>
              <span>{isCacheClearing ? "Flushing Cache..." : "Clear Intent Cache"}</span>
            </button>

            <button
              type="button"
              className="cg-popover-item cg-popover-item--danger"
              onClick={handleLogout}
              title="Sign out of AMC Context Engine"
            >
              <span className="cg-popover-item-icon"><LogOut size={16} strokeWidth={1.75} /></span>
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
            <MoreHorizontal size={16} strokeWidth={1.75} />
          </div>
        </button>
      </div>
    </aside>
  );
}
