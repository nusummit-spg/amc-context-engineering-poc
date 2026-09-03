import Button from "./widgets/Button";
import Alert from "./widgets/Alert";
import Progress from "./widgets/Progress";
import { useAppState } from "../state/AppState";
import { useToast } from "./widgets/Toast";

const PAGES = [
  { id: "app", label: "app", icon: "💬" },
  { id: "01_Scorecard", label: "01_Scorecard", icon: "🎯" },
  { id: "02_Violations", label: "02_Violations", icon: "⚠️" },
  { id: "03_Funds", label: "03_Funds", icon: "🏢" },
  { id: "04_Remediation", label: "04_Remediation", icon: "🛠️" },
  { id: "05_Multi_Region", label: "05_Multi_Region", icon: "🌐" },
];

export default function Sidebar() {
  const {
    activeUser,
    chatSessions, chatSessionId, loadChatSession, deleteChatSession, startNewChatSession,
    indexingTasks, clearCache, isCacheClearing,
    activePage, setActivePage, isSidebarOpen, toggleSidebar,
    logout,
  } = useAppState();
  const pushToast = useToast();

  const handleClearCache = async () => {
    const ok = await clearCache();
    if (ok) {
      pushToast("Intent Cache cleared cleanly! Next query will execute full LLM synthesis.", "⚡");
    } else {
      pushToast("Intent Cache flushed locally.", "⚡");
    }
  };

  const activeIndexing = indexingTasks.filter((t) => t.status === "PROCESSING").slice(0, 5);

  const sessions = Object.entries(chatSessions)
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .slice(0, 20)
    .map(([id, s]) => {
      const firstUserMsg = (s.history || []).find((m) => m.role === "user");
      const firstQuery = s.title || firstUserMsg?.content || "";
      const preview = firstQuery.length > 38 ? firstQuery.slice(0, 38) + "…" : firstQuery;
      return { session_id: id, preview, turn_count: Math.floor((s.history || []).length / 2) };
    });

  return (
    <div className={`stSidebar ${isSidebarOpen ? "" : "stSidebar--collapsed"}`}>
      <div className="stSidebar-topbar">
        <span className="stSidebar-brand">Pages</span>
        <button
          className="stSidebarCollapseButton"
          onClick={toggleSidebar}
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
        >
          «
        </button>
      </div>

      {/* Streamlit Multipage Navigation */}
      <nav className="stSidebarNav" aria-label="Pages Navigation">
        <ul className="stSidebarNav-list">
          {PAGES.map((p) => {
            const isActive = activePage === p.id;
            return (
              <li key={p.id} className="stSidebarNav-item">
                <button
                  type="button"
                  className={`stSidebarNav-link ${isActive ? "active" : ""}`}
                  onClick={() => setActivePage(p.id)}
                  title={p.label}
                >
                  <span className="stSidebarNav-icon">{p.icon}</span>
                  <span className="stSidebarNav-label">{p.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <hr />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "0.5rem" }}>
        <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#6e6e6e", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Current Session
        </span>
        <button
          type="button"
          onClick={logout}
          style={{
            background: "none",
            border: "none",
            color: "#b08d57",
            fontSize: "0.8rem",
            cursor: "pointer",
            fontWeight: 600,
            padding: "2px 4px",
            textDecoration: "underline",
          }}
          title="Sign out and return to authentication screen"
        >
          Sign out
        </button>
      </div>

      <blockquote className="stMarkdownBlockquote" style={{ marginTop: "0.4rem" }}>
        <b>User</b>: <code>{activeUser.full_name}</code>
        <br />
        <b>Role</b>: <code>{activeUser.role}</code>
        <br />
        <b>Dept</b>: <code>{activeUser.department}</code>
      </blockquote>

      <Button
        kind="secondary"
        fullWidth
        disabled={isCacheClearing}
        onClick={handleClearCache}
        title="Flush in-memory and disk intent cache so all queries execute fresh LLM synthesis"
      >
        {isCacheClearing ? "Flushing Cache..." : "🗑️ Clear Intent Cache"}
      </Button>

      {activeIndexing.length > 0 && (
        <>
          <hr />
          <h3>⚙️ Background Indexing</h3>
          {activeIndexing.map((t) => (
            <div key={t.task_id}>
              <Alert type="info">
                Indexing <b>{t.filename}</b>...
                <br />
                <br />
                <i>{t.stage}</i>
              </Alert>
              <Progress value={t.progress} />
            </div>
          ))}
        </>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "1rem" }}>
        <h3 style={{ margin: 0 }}>💬 Chat Sessions</h3>
        <button
          onClick={() => startNewChatSession()}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: "0.85rem",
            color: "#0e76a8",
            fontWeight: 600,
          }}
          title="Start a new chat session"
        >
          ➕ New
        </button>
      </div>

      {sessions.length === 0 ? (
        <div className="stCaption" style={{ marginTop: 6 }}>
          No saved sessions yet — start a conversation in the Chat tab.
        </div>
      ) : (
        sessions.map((s) => {
          const isCurrent = s.session_id === chatSessionId;
          return (
            <div
              key={s.session_id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                marginBottom: 6,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <Button
                  kind="secondary"
                  fullWidth
                  disabled={isCurrent}
                  title={`${s.turn_count} turn(s) · ${s.session_id}`}
                  onClick={() => loadChatSession(s.session_id)}
                >
                  {isCurrent ? "🟢 " : ""}
                  {s.preview || "(empty)"}
                </Button>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteChatSession(s.session_id);
                  pushToast("Session deleted", "🗑️");
                }}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "#999",
                  fontSize: "0.9rem",
                  padding: "4px 6px",
                }}
                title="Delete session"
              >
                ✕
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}
