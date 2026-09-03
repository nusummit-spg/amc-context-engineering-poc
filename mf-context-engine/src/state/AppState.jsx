import { createContext, useContext, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { DEFAULT_USER_PROFILES, ROLE_PERMISSIONS } from "../data/rbac";
import USERS from "../data/users.json";
import {
  fetchUsers,
  fetchAuditLogs,
  fetchIndexingTasks,
  fetchProposedEdges,
  fetchGraph,
  sendChat as apiSendChat,
  sendQuery as apiSendQuery,
  clearIntentCache as apiClearIntentCache,
  saveUser as apiSaveUser,
  deleteUser as apiDeleteUser,
  runIngestPipeline as apiRunIngestPipeline,
  checkStaleness as apiCheckStaleness,
  confirmProposedEdge as apiConfirmProposedEdge,
  rejectProposedEdge as apiRejectProposedEdge,
} from "../services/api";
import { generateTraditionalResult, generateHybridResult } from "../data/mockEngine";

const AppStateContext = createContext(null);

// ── Storage Keys ─────────────────────────────────────────────────────────────
const STORAGE_KEYS = {
  USERS: "ns_cg_users_v1",
  ACTIVE_USER: "ns_cg_active_user_v1",
  AUTH_SESSION: "ns_cg_auth_session_v1",
  CHAT_SESSIONS: "ns_cg_chat_sessions_v1",
  ACTIVE_SESSION_ID: "ns_cg_active_session_id_v1",
  COMPARE_SESSIONS: "ns_cg_compare_sessions_v1",
  ACTIVE_COMPARE_SESSION_ID: "ns_cg_active_compare_session_id_v1",
  COMPARISONS: "ns_cg_comparisons_v1",
  ACTIVE_TAB: "ns_cg_active_tab_v1",
  ADMIN_SUB_TAB: "ns_cg_admin_subtab_v1",
  ACTIVE_PAGE: "ns_cg_active_page_v1",
  SIDEBAR_OPEN: "ns_cg_sidebar_open_v1",
};

function safeStorageGet(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    console.warn(`Could not persist ${key} to localStorage:`, err);
  }
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ── Initial Mock Data ────────────────────────────────────────────────────────
const INITIAL_INDEXING_TASKS = [
  {
    task_id: "task-8f2c1a",
    filename: "April 2025.pdf",
    status: "COMPLETED",
    stage: "Finished",
    progress: 1.0,
    sha256_hash: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a1",
    started_at: "2026-08-28T09:12:04",
    completed_at: "2026-08-28T09:14:41",
    entities_count: 42,
    relations_count: 67,
    chunks_count: 118,
  },
  {
    task_id: "task-3ba9de",
    filename: "Safer participation of retail investors in Algorithmic trading.pdf",
    status: "COMPLETED",
    stage: "Finished",
    progress: 1.0,
    sha256_hash: "1c383cd30b7c298ab50293adfecb7b18",
    started_at: "2026-08-25T14:02:11",
    completed_at: "2026-08-25T14:05:33",
    entities_count: 28,
    relations_count: 39,
    chunks_count: 74,
  },
];

const INITIAL_AUDIT_LINES = [
  `{"ts": "2026-08-30T11:41:02Z", "user": "sarah_compliance", "role": "Compliance & Regulatory Officer", "query": "borrowing limits for mutual funds", "mode": "contextgraph", "latency_ms": 842}`,
  `{"ts": "2026-08-30T11:38:47Z", "user": "vikram_pm", "role": "Fund Manager / Portfolio Manager", "query": "categorization rules for equity schemes", "mode": "traditional", "latency_ms": 1204}`,
  `{"ts": "2026-08-30T10:55:19Z", "user": "ananya_esg", "role": "ESG & Sustainability Analyst", "query": "ESG disclosure requirements BRSR", "mode": "contextgraph", "latency_ms": 693}`,
  `{"ts": "2026-08-29T16:20:03Z", "user": "sarah_compliance", "role": "Compliance & Regulatory Officer", "query": "information ratio disclosure norms", "mode": "contextgraph", "latency_ms": 771}`,
  `{"ts": "2026-08-29T09:04:55Z", "user": "rahul_sales", "role": "Sales & Distribution Manager", "query": "SID KIM update timelines", "mode": "traditional", "latency_ms": 1330}`,
];

const INITIAL_USERS = [
  ...USERS.map((u) => ({
    username: u.username,
    full_name: u.display_name,
    role: u.role,
    department: u.department,
    email: u.email,
    avatar_initials: u.avatar_initials,
    status: "Active",
  })),
  ...DEFAULT_USER_PROFILES.filter((dp) => !USERS.some((u) => u.username === dp.username)),
];

export function AppStateProvider({ children }) {
  // ── 0. Auth Gate State ─────────────────────────────────────────────────────
  const [authSession, setAuthSessionState] = useState(() =>
    safeStorageGet(STORAGE_KEYS.AUTH_SESSION, { isAuthenticated: false, authedUsername: null })
  );
  const isAuthenticated = Boolean(authSession?.isAuthenticated);
  const authedUsername = authSession?.authedUsername || null;

  // ── 1. Users & RBAC State ──────────────────────────────────────────────────
  const [users, setUsersState] = useState(() => safeStorageGet(STORAGE_KEYS.USERS, INITIAL_USERS));
  const [activeUsername, setActiveUsernameState] = useState(() => {
    const saved = safeStorageGet(STORAGE_KEYS.ACTIVE_USER, null);
    if (saved) return saved;
    const initialSession = safeStorageGet(STORAGE_KEYS.AUTH_SESSION, null);
    return initialSession?.authedUsername || INITIAL_USERS[0].username;
  });

  const setUsers = useCallback((updater) => {
    setUsersState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      safeStorageSet(STORAGE_KEYS.USERS, next);
      return next;
    });
  }, []);

  const setActiveUsername = useCallback((username) => {
    setActiveUsernameState(username);
    safeStorageSet(STORAGE_KEYS.ACTIVE_USER, username);
  }, []);

  const login = useCallback(
    (inputUserId, inputPassword, autoCommit = false) => {
      const clean = (inputUserId || "").trim().toLowerCase();
      const matched = USERS.find((u) => u.username.toLowerCase() === clean);
      if (!matched || matched.password !== inputPassword) {
        return { success: false, error: "That User ID or password doesn't match our records." };
      }

      const commit = () => {
        const sessionData = { isAuthenticated: true, authedUsername: matched.username };
        setAuthSessionState(sessionData);
        safeStorageSet(STORAGE_KEYS.AUTH_SESSION, sessionData);
        setActiveUsername(matched.username);

        setUsersState((prev) => {
          if (prev.some((u) => u.username === matched.username)) return prev;
          const newProfile = {
            username: matched.username,
            full_name: matched.display_name,
            role: matched.role,
            department: matched.department,
            email: matched.email,
            avatar_initials: matched.avatar_initials,
            status: "Active",
          };
          const next = [newProfile, ...prev];
          safeStorageSet(STORAGE_KEYS.USERS, next);
          return next;
        });
      };

      if (autoCommit) {
        commit();
      }

      return { success: true, user: matched, commit };
    },
    [setActiveUsername]
  );

  const logout = useCallback(() => {
    const sessionData = { isAuthenticated: false, authedUsername: null };
    setAuthSessionState(sessionData);
    safeStorageSet(STORAGE_KEYS.AUTH_SESSION, sessionData);
  }, []);

  const activeUser = useMemo(() => {
    const found = users.find((u) => u.username === activeUsername);
    if (found) return found;
    const foundAuth = USERS.find((u) => u.username === activeUsername);
    if (foundAuth) {
      return {
        username: foundAuth.username,
        full_name: foundAuth.display_name,
        role: foundAuth.role,
        department: foundAuth.department,
        email: foundAuth.email,
        avatar_initials: foundAuth.avatar_initials,
        status: "Active",
      };
    }
    return users[0] || INITIAL_USERS[0] || DEFAULT_USER_PROFILES[0];
  }, [users, activeUsername]);

  const activePermissions = useMemo(() => {
    return ROLE_PERMISSIONS[activeUser.role] || {};
  }, [activeUser.role]);

  // ── 2. Navigation & Tabs State ─────────────────────────────────────────────
  const [activeTab, setActiveTabState] = useState(() => safeStorageGet(STORAGE_KEYS.ACTIVE_TAB, 0));
  const [adminSubTab, setAdminSubTabState] = useState(() => safeStorageGet(STORAGE_KEYS.ADMIN_SUB_TAB, 0));
  const [activePage, setActivePageState] = useState(() => safeStorageGet(STORAGE_KEYS.ACTIVE_PAGE, "app"));
  const [isSidebarOpen, setIsSidebarOpenState] = useState(() => safeStorageGet(STORAGE_KEYS.SIDEBAR_OPEN, true));

  const setActiveTab = useCallback((tab) => {
    setActiveTabState(tab);
    safeStorageSet(STORAGE_KEYS.ACTIVE_TAB, tab);
  }, []);

  const setAdminSubTab = useCallback((subTab) => {
    setAdminSubTabState(subTab);
    safeStorageSet(STORAGE_KEYS.ADMIN_SUB_TAB, subTab);
  }, []);

  const setActivePage = useCallback((page) => {
    setActivePageState(page);
    safeStorageSet(STORAGE_KEYS.ACTIVE_PAGE, page);
  }, []);

  const setIsSidebarOpen = useCallback((open) => {
    setIsSidebarOpenState(open);
    safeStorageSet(STORAGE_KEYS.SIDEBAR_OPEN, open);
  }, []);

  const toggleSidebar = useCallback(() => {
    setIsSidebarOpenState((prev) => {
      const next = !prev;
      safeStorageSet(STORAGE_KEYS.SIDEBAR_OPEN, next);
      return next;
    });
  }, []);

  // ── 3. Chat State (Multi-Session & Multi-Turn) ─────────────────────────────
  const [chatSessions, setChatSessionsState] = useState(() => safeStorageGet(STORAGE_KEYS.CHAT_SESSIONS, {}));
  const [chatSessionId, setChatSessionIdState] = useState(() => {
    const saved = safeStorageGet(STORAGE_KEYS.ACTIVE_SESSION_ID, null);
    return saved || uuid();
  });
  const [chatQuery, setChatQuery] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatError, setChatError] = useState(null);

  const setChatSessions = useCallback((updater) => {
    setChatSessionsState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      safeStorageSet(STORAGE_KEYS.CHAT_SESSIONS, next);
      return next;
    });
  }, []);

  const setChatSessionId = useCallback((id) => {
    setChatSessionIdState(id);
    safeStorageSet(STORAGE_KEYS.ACTIVE_SESSION_ID, id);
  }, []);

  const getChatHistory = useCallback(
    (id = chatSessionId) => {
      return chatSessions[id]?.history || [];
    },
    [chatSessions, chatSessionId]
  );

  const setChatHistory = useCallback(
    (id, historyOrFn) => {
      setChatSessions((prev) => {
        const current = prev[id]?.history || [];
        const next = typeof historyOrFn === "function" ? historyOrFn(current) : historyOrFn;
        const title = prev[id]?.title || (next.find((m) => m.role === "user")?.content?.slice(0, 45) || "New Conversation");
        return {
          ...prev,
          [id]: {
            id,
            title,
            history: next,
            createdAt: prev[id]?.createdAt || Date.now(),
            updatedAt: Date.now(),
          },
        };
      });
    },
    [setChatSessions]
  );

  const startNewChatSession = useCallback(
    (customTitle = null) => {
      const newId = uuid();
      setChatSessionId(newId);
      setChatQuery("");
      setChatError(null);
      setChatSessions((prev) => ({
        ...prev,
        [newId]: {
          id: newId,
          title: customTitle || "New Conversation",
          history: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        },
      }));
      return newId;
    },
    [setChatSessionId, setChatSessions]
  );

  const loadChatSession = useCallback(
    (id) => {
      if (chatSessions[id]) {
        setChatSessionId(id);
        setChatError(null);
        return true;
      }
      return false;
    },
    [chatSessions, setChatSessionId]
  );

  const deleteChatSession = useCallback(
    (id) => {
      setChatSessions((prev) => {
        const copy = { ...prev };
        delete copy[id];
        return copy;
      });
      if (chatSessionId === id) {
        startNewChatSession();
      }
    },
    [chatSessionId, setChatSessions, startNewChatSession]
  );

  const clearAllChatSessions = useCallback(() => {
    const freshId = uuid();
    setChatSessions({});
    setChatSessionId(freshId);
    setChatQuery("");
    safeStorageSet(STORAGE_KEYS.CHAT_SESSIONS, {});
    safeStorageSet(STORAGE_KEYS.ACTIVE_SESSION_ID, freshId);
  }, [setChatSessions, setChatSessionId]);

  const sendChatMessage = useCallback(
    async (queryText = chatQuery) => {
      const q = queryText.trim();
      if (!q || isChatLoading) return;

      const sid = chatSessionId;
      const history = getChatHistory(sid);
      const turnIndex = Math.floor(history.length / 2) + 1;

      const userMsg = { role: "user", content: q, turn_index: turnIndex, timestamp: Date.now() };
      const loadingMsg = { role: "assistant", loading: true, turn_index: turnIndex };

      setChatQuery("");
      setIsChatLoading(true);
      setChatError(null);
      setChatHistory(sid, (h) => [...h, userMsg, loadingMsg]);

      try {
        const resp = await apiSendChat({
          query: q,
          history,
          session_id: sid,
          mode: "contextgraph",
        });

        setChatHistory(sid, (h) => {
          const next = [...h];
          const idx = next.length - 1;
          next[idx] = {
            role: "assistant",
            loading: false,
            turn_index: turnIndex,
            hybrid: resp.hybrid,
            resolvedQuery: resp.resolvedQuery,
            content: resp.hybrid?.answer || "No answer generated.",
            timestamp: Date.now(),
          };
          return next;
        });
      } catch (err) {
        console.warn("Backend chat failed, falling back to mock synthesis:", err);
        const hybrid = generateHybridResult(q);

        setChatHistory(sid, (h) => {
          const next = [...h];
          const idx = next.length - 1;
          next[idx] = {
            role: "assistant",
            loading: false,
            turn_index: turnIndex,
            hybrid,
            content: hybrid.answer,
            timestamp: Date.now(),
          };
          return next;
        });
      } finally {
        setIsChatLoading(false);
      }
    },
    [chatQuery, isChatLoading, chatSessionId, getChatHistory, setChatHistory]
  );

  // ── 4. Compare State (Multi-Session & Multi-Turn Independent from Chat) ────
  const [compareSessions, setCompareSessionsState] = useState(() => safeStorageGet(STORAGE_KEYS.COMPARE_SESSIONS, {}));
  const [compareSessionId, setCompareSessionIdState] = useState(() => {
    const saved = safeStorageGet(STORAGE_KEYS.ACTIVE_COMPARE_SESSION_ID, null);
    return saved || uuid();
  });
  const [compareQuery, setCompareQuery] = useState("");
  const [isCompareLoading, setIsCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState(null);
  const [compareResult, setCompareResult] = useState(null);
  const [comparisons, setComparisonsState] = useState(() => safeStorageGet(STORAGE_KEYS.COMPARISONS, []));
  const [lastHybrid, setLastHybrid] = useState(null);
  const [lastTraditional, setLastTraditional] = useState(null);

  const setCompareSessions = useCallback((updater) => {
    setCompareSessionsState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      safeStorageSet(STORAGE_KEYS.COMPARE_SESSIONS, next);
      return next;
    });
  }, []);

  const setCompareSessionId = useCallback((id) => {
    setCompareSessionIdState(id);
    safeStorageSet(STORAGE_KEYS.ACTIVE_COMPARE_SESSION_ID, id);
  }, []);

  const getCompareHistory = useCallback(
    (id = compareSessionId) => {
      return compareSessions[id]?.history || [];
    },
    [compareSessions, compareSessionId]
  );

  const setCompareHistory = useCallback(
    (id, historyOrFn) => {
      setCompareSessions((prev) => {
        const current = prev[id]?.history || [];
        const next = typeof historyOrFn === "function" ? historyOrFn(current) : historyOrFn;
        const title = prev[id]?.title || (next.find((m) => m.role === "user")?.content?.slice(0, 45) || "New Comparison");
        return {
          ...prev,
          [id]: {
            id,
            title,
            history: next,
            createdAt: prev[id]?.createdAt || Date.now(),
            updatedAt: Date.now(),
          },
        };
      });
    },
    [setCompareSessions]
  );

  const startNewCompareSession = useCallback(
    (customTitle = null) => {
      const newId = uuid();
      setCompareSessionId(newId);
      setCompareQuery("");
      setCompareError(null);
      setCompareSessions((prev) => ({
        ...prev,
        [newId]: {
          id: newId,
          title: customTitle || "New Comparison",
          history: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        },
      }));
      return newId;
    },
    [setCompareSessionId, setCompareSessions]
  );

  const loadCompareSession = useCallback(
    (id) => {
      if (compareSessions[id]) {
        setCompareSessionId(id);
        setCompareError(null);
        return true;
      }
      return false;
    },
    [compareSessions, setCompareSessionId]
  );

  const deleteCompareSession = useCallback(
    (id) => {
      setCompareSessions((prev) => {
        const copy = { ...prev };
        delete copy[id];
        return copy;
      });
      if (compareSessionId === id) {
        startNewCompareSession();
      }
    },
    [compareSessionId, setCompareSessions, startNewCompareSession]
  );

  const clearAllCompareSessions = useCallback(() => {
    const freshId = uuid();
    setCompareSessions({});
    setCompareSessionId(freshId);
    setCompareQuery("");
    safeStorageSet(STORAGE_KEYS.COMPARE_SESSIONS, {});
    safeStorageSet(STORAGE_KEYS.ACTIVE_COMPARE_SESSION_ID, freshId);
  }, [setCompareSessions, setCompareSessionId]);

  const setComparisons = useCallback((updater) => {
    setComparisonsState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      safeStorageSet(STORAGE_KEYS.COMPARISONS, next);
      return next;
    });
  }, []);

  const clearComparisonsHistory = useCallback(() => {
    setComparisons([]);
    setLastHybrid(null);
    setLastTraditional(null);
    safeStorageSet(STORAGE_KEYS.COMPARISONS, []);
  }, [setComparisons]);

  const sendCompareMessage = useCallback(
    async (queryText = compareQuery) => {
      const q = queryText.trim();
      if (!q || isCompareLoading) return;

      const sid = compareSessionId;
      const history = getCompareHistory(sid);
      const turnIndex = Math.floor(history.length / 2) + 1;

      const userMsg = { role: "user", content: q, turn_index: turnIndex, timestamp: Date.now() };
      const loadingMsg = { role: "assistant", loading: true, turn_index: turnIndex };

      setCompareQuery("");
      setIsCompareLoading(true);
      setCompareError(null);
      setCompareHistory(sid, (h) => [...h, userMsg, loadingMsg]);

      try {
        const resp = await apiSendChat({
          query: q,
          history,
          session_id: sid,
          mode: "both",
        });

        setLastHybrid(resp.hybrid);
        setLastTraditional(resp.traditional);

        setCompareHistory(sid, (h) => {
          const next = [...h];
          const idx = next.length - 1;
          next[idx] = {
            role: "assistant",
            loading: false,
            turn_index: turnIndex,
            traditional: resp.traditional,
            hybrid: resp.hybrid,
            resolvedQuery: resp.resolvedQuery,
            timestamp: Date.now(),
          };
          return next;
        });

        setComparisons((prev) => [
          ...prev,
          {
            id: uuid(),
            query: q,
            traditional_time: resp.traditional?.total_time || 0,
            hybrid_time: resp.hybrid?.total_time || 0,
            traditional_tokens: resp.traditional?.total_tokens || 0,
            hybrid_tokens: resp.hybrid?.total_tokens || 0,
            timestamp: Date.now(),
          },
        ]);
      } catch (err) {
        console.warn("Backend compare failed, using fallback:", err);
        const hybrid = generateHybridResult(q);
        const traditional = generateTraditionalResult(q);

        setLastHybrid(hybrid);
        setLastTraditional(traditional);

        setCompareHistory(sid, (h) => {
          const next = [...h];
          const idx = next.length - 1;
          next[idx] = {
            role: "assistant",
            loading: false,
            turn_index: turnIndex,
            traditional,
            hybrid,
            timestamp: Date.now(),
          };
          return next;
        });

        setComparisons((prev) => [
          ...prev,
          {
            id: uuid(),
            query: q,
            traditional_time: traditional.total_time,
            hybrid_time: hybrid.total_time,
            traditional_tokens: traditional.total_tokens,
            hybrid_tokens: hybrid.total_tokens,
            timestamp: Date.now(),
          },
        ]);
      } finally {
        setIsCompareLoading(false);
      }
    },
    [compareQuery, isCompareLoading, compareSessionId, getCompareHistory, setCompareHistory, setComparisons]
  );

  const runComparison = useCallback(
    async (queryText = compareQuery) => {
      const q = queryText.trim();
      if (!q || isCompareLoading) return;

      setIsCompareLoading(true);
      try {
        const resp = await apiSendQuery({ query: q, mode: "both" });
        setCompareResult(resp);
        setLastHybrid(resp.hybrid);
        setLastTraditional(resp.traditional);

        setComparisons((prev) => [
          ...prev,
          {
            id: uuid(),
            query: q,
            traditional_time: resp.traditional?.total_time || 0,
            hybrid_time: resp.hybrid?.total_time || 0,
            traditional_tokens: resp.traditional?.total_tokens || 0,
            hybrid_tokens: resp.hybrid?.total_tokens || 0,
            timestamp: Date.now(),
          },
        ]);
        return resp;
      } catch (err) {
        console.warn("Backend compare query failed, using fallback:", err);
        const hybrid = generateHybridResult(q);
        const traditional = generateTraditionalResult(q);
        const fallbackResp = { traditional, hybrid };

        setCompareResult(fallbackResp);
        setLastHybrid(hybrid);
        setLastTraditional(traditional);

        setComparisons((prev) => [
          ...prev,
          {
            id: uuid(),
            query: q,
            traditional_time: traditional.total_time,
            hybrid_time: hybrid.total_time,
            traditional_tokens: traditional.total_tokens,
            hybrid_tokens: hybrid.total_tokens,
            timestamp: Date.now(),
          },
        ]);
        return fallbackResp;
      } finally {
        setIsCompareLoading(false);
      }
    },
    [compareQuery, isCompareLoading, setComparisons]
  );

  // ── 5. Analytics & Graph State ─────────────────────────────────────────────
  const [analyticsScope, setAnalyticsScope] = useState("Last query's graph");
  const [fullGraphData, setFullGraphData] = useState(null);
  const [isGraphLoading, setIsGraphLoading] = useState(false);

  const loadFullGraph = useCallback(async (limit = 60) => {
    setIsGraphLoading(true);
    try {
      const data = await fetchGraph(limit);
      if (data && data.edges && data.edges.length > 0) {
        const edges = data.edges.map((e) => ({
          s: e.source,
          rel: e.relationship_type || e.label || "REL",
          o: e.target,
          conf: 1.0,
        }));
        const nodes = data.nodes ? data.nodes.map((n) => n.label || n.id) : Array.from(new Set(edges.flatMap((x) => [x.s, x.o])));
        const sourceInfo = {};
        nodes.forEach((n) => {
          sourceInfo[n] = { label: "Entity", source: "Neo4j Knowledge Graph" };
        });
        const graphObj = { edgesToShow: edges, nodesToShow: nodes, sourceInfo };
        setFullGraphData(graphObj);
        return graphObj;
      }
    } catch (err) {
      console.warn("Backend graph fetch error:", err);
    } finally {
      setIsGraphLoading(false);
    }
  }, []);

  // ── 6. Admin, Indexing & Audit State ───────────────────────────────────────
  const [indexingTasks, setIndexingTasks] = useState(INITIAL_INDEXING_TASKS);
  const [auditLines, setAuditLines] = useState(INITIAL_AUDIT_LINES);
  const [proposedEdges, setProposedEdges] = useState([
    { edge_id: "pe-1", source: "April 2025 Master Circular", rel: "SUPERSEDES", target: "April 2024 Master Circular" },
    { edge_id: "pe-2", source: "Categorization and Rationalization Circular (2025)", rel: "SUPERSEDES", target: "Categorization and Rationalization Circular (2017)" },
  ]);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [isStalenessChecking, setIsStalenessChecking] = useState(false);

  const taskCounter = useRef(0);

  const addIndexingTask = useCallback((filename) => {
    taskCounter.current += 1;
    const id = `task-${Date.now()}-${taskCounter.current}`;
    const task = {
      task_id: id,
      filename,
      status: "PROCESSING",
      stage: "Extracting text & running NER pipeline...",
      progress: 0.15,
      sha256_hash: Array.from({ length: 24 }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join(""),
      started_at: new Date().toISOString(),
      completed_at: null,
      entities_count: 0,
      relations_count: 0,
      chunks_count: 0,
    };
    setIndexingTasks((prev) => [task, ...prev]);

    const stages = [
      [0.35, "Chunking document & generating embeddings..."],
      [0.65, "Writing vectors to FAISS index..."],
      [0.9, "Extracting entities & relations into Neo4j..."],
    ];
    stages.forEach(([progress, stage], i) => {
      setTimeout(() => {
        setIndexingTasks((prev) =>
          prev.map((t) => (t.task_id === id ? { ...t, progress, stage } : t))
        );
      }, 900 * (i + 1));
    });
    setTimeout(() => {
      setIndexingTasks((prev) =>
        prev.map((t) =>
          t.task_id === id
            ? {
                ...t,
                status: "COMPLETED",
                stage: "Finished",
                progress: 1.0,
                completed_at: new Date().toISOString(),
                entities_count: 18 + Math.floor(Math.random() * 30),
                relations_count: 22 + Math.floor(Math.random() * 40),
                chunks_count: 40 + Math.floor(Math.random() * 90),
              }
            : t
        )
      );
    }, 900 * (stages.length + 1));
    return id;
  }, []);

  const refreshIndexingTasks = useCallback(async (limit = 10) => {
    try {
      const resp = await fetchIndexingTasks(limit);
      if (resp && resp.tasks && resp.tasks.length > 0) {
        setIndexingTasks(resp.tasks);
        return resp.tasks;
      }
    } catch (err) {
      console.warn("Could not refresh indexing tasks:", err);
    }
  }, []);

  const refreshAuditLogs = useCallback(async (limit = 30) => {
    try {
      const resp = await fetchAuditLogs(limit);
      if (resp && resp.lines && resp.lines.length > 0) {
        setAuditLines(resp.lines);
        return resp.lines;
      }
    } catch (err) {
      console.warn("Could not refresh audit logs:", err);
    }
  }, []);

  const refreshProposedEdges = useCallback(async () => {
    try {
      const resp = await fetchProposedEdges();
      if (resp && resp.edges && resp.edges.length > 0) {
        setProposedEdges(resp.edges);
        return resp.edges;
      }
    } catch (err) {
      console.warn("Could not refresh proposed edges:", err);
    }
  }, []);

  const confirmEdge = useCallback(async (id, authorizedBy = "sarah_compliance") => {
    try {
      await apiConfirmProposedEdge(id, authorizedBy);
    } catch (err) {
      console.warn("Backend edge confirm error:", err);
    }
    setProposedEdges((prev) => prev.filter((p) => p.edge_id !== id));
  }, []);

  const rejectEdge = useCallback(async (id) => {
    try {
      await apiRejectProposedEdge(id);
    } catch (err) {
      console.warn("Backend edge reject error:", err);
    }
    setProposedEdges((prev) => prev.filter((p) => p.edge_id !== id));
  }, []);

  const saveUserProfile = useCallback(
    async (profile) => {
      try {
        await apiSaveUser(profile);
      } catch (err) {
        console.warn("Backend user save failed, applying locally:", err);
      }
      setUsers((prev) => {
        const filtered = prev.filter((u) => u.username !== profile.username);
        return [...filtered, profile];
      });
    },
    [setUsers]
  );

  const deleteUserProfile = useCallback(
    async (username) => {
      try {
        await apiDeleteUser(username);
      } catch (err) {
        console.warn("Backend user delete failed, applying locally:", err);
      }
      setUsers((prev) => prev.filter((u) => u.username !== username));
    },
    [setUsers]
  );

  // ── 7. System & Cache State ────────────────────────────────────────────────
  const [isCacheClearing, setIsCacheClearing] = useState(false);
  const [backendStatus, setBackendStatus] = useState("online");

  const clearCache = useCallback(async () => {
    setIsCacheClearing(true);
    try {
      await apiClearIntentCache();
      return true;
    } catch {
      return false;
    } finally {
      setIsCacheClearing(false);
    }
  }, []);

  // ── Initial Backend Sync ───────────────────────────────────────────────────
  useEffect(() => {
    async function loadBackendData() {
      try {
        const u = await fetchUsers();
        if (u && u.users && u.users.length > 0) {
          setUsers(u.users);
          setActiveUsername((prev) => (u.users.some((x) => x.username === prev) ? prev : u.users[0].username));
        }
      } catch {
        // use local storage / fallback
      }

      try {
        const audit = await fetchAuditLogs(30);
        if (audit && audit.lines && audit.lines.length > 0) {
          setAuditLines(audit.lines);
        }
      } catch {}

      try {
        const tasks = await fetchIndexingTasks(10);
        if (tasks && tasks.tasks && tasks.tasks.length > 0) {
          setIndexingTasks(tasks.tasks);
        }
      } catch {}

      try {
        const edges = await fetchProposedEdges();
        if (edges && edges.edges && edges.edges.length > 0) {
          setProposedEdges(edges.edges);
        }
      } catch {}
    }
    loadBackendData();
  }, [setUsers, setActiveUsername]);

  const value = {
    // Auth & Gate
    isAuthenticated,
    authedUsername,
    login,
    logout,

    // Users & RBAC
    users, setUsers,
    activeUsername, setActiveUsername,
    activeUser, activePermissions,
    saveUserProfile, deleteUserProfile,

    // Navigation & Tabs & Pages
    activeTab, setActiveTab,
    adminSubTab, setAdminSubTab,
    activePage, setActivePage,
    isSidebarOpen, setIsSidebarOpen, toggleSidebar,

    // Chat
    chatSessions, setChatSessions,
    chatSessionId, setChatSessionId,
    chatQuery, setChatQuery,
    isChatLoading, chatError, setChatError,
    getChatHistory, setChatHistory,
    startNewChatSession, loadChatSession, deleteChatSession, clearAllChatSessions,
    sendChatMessage,

    // Compare
    compareSessions, setCompareSessions,
    compareSessionId, setCompareSessionId,
    compareQuery, setCompareQuery,
    isCompareLoading, isCompareRunning: isCompareLoading,
    compareError, setCompareError,
    getCompareHistory, setCompareHistory,
    startNewCompareSession, loadCompareSession, deleteCompareSession, clearAllCompareSessions,
    sendCompareMessage,
    compareResult, setCompareResult,
    comparisons, setComparisons,
    lastHybrid, setLastHybrid,
    lastTraditional, setLastTraditional,
    runComparison, clearComparisonsHistory,

    // Analytics & Graph
    analyticsScope, setAnalyticsScope,
    fullGraphData, setFullGraphData,
    isGraphLoading, loadFullGraph,

    // Admin & Ingest
    indexingTasks, setIndexingTasks, addIndexingTask, refreshIndexingTasks,
    auditLines, setAuditLines, refreshAuditLogs,
    proposedEdges, setProposedEdges, refreshProposedEdges,
    confirmEdge, rejectEdge,
    isPipelineRunning, setIsPipelineRunning,
    isStalenessChecking, setIsStalenessChecking,

    // System & Cache
    isCacheClearing, clearCache,
    backendStatus, setBackendStatus,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}

export function useUser() {
  const {
    users,
    activeUser,
    activeUsername,
    setActiveUsername,
    activePermissions,
    saveUserProfile,
    deleteUserProfile,
    isAuthenticated,
    authedUsername,
    login,
    logout,
  } = useAppState();
  return {
    users,
    activeUser,
    activeUsername,
    setActiveUsername,
    permissions: activePermissions,
    saveUserProfile,
    deleteUserProfile,
    isAuthenticated,
    authedUsername,
    login,
    logout,
  };
}

export function useChat() {
  const {
    chatSessions, chatSessionId, chatQuery, setChatQuery,
    isChatLoading, chatError, getChatHistory, setChatHistory,
    startNewChatSession, loadChatSession, deleteChatSession, clearAllChatSessions,
    sendChatMessage,
  } = useAppState();
  return {
    chatSessions, chatSessionId, chatQuery, setChatQuery,
    isChatLoading, chatError, getChatHistory, setChatHistory,
    startNewChatSession, loadChatSession, deleteChatSession, clearAllChatSessions,
    sendChatMessage,
  };
}

export function useCompare() {
  const {
    compareSessions, compareSessionId,
    compareQuery, setCompareQuery,
    isCompareLoading, isCompareRunning,
    compareError, getCompareHistory, setCompareHistory,
    startNewCompareSession, loadCompareSession, deleteCompareSession, clearAllCompareSessions,
    sendCompareMessage,
    compareResult,
    comparisons, lastHybrid, lastTraditional, runComparison, clearComparisonsHistory,
  } = useAppState();
  return {
    compareSessions, compareSessionId,
    compareQuery, setCompareQuery,
    isCompareLoading, isCompareRunning,
    compareError, getCompareHistory, setCompareHistory,
    startNewCompareSession, loadCompareSession, deleteCompareSession, clearAllCompareSessions,
    sendCompareMessage,
    compareResult,
    comparisons, lastHybrid, lastTraditional, runComparison, clearComparisonsHistory,
  };
}

export function useAnalytics() {
  const {
    analyticsScope, setAnalyticsScope, fullGraphData, isGraphLoading,
    loadFullGraph, lastHybrid, comparisons,
  } = useAppState();
  return {
    analyticsScope, setAnalyticsScope, fullGraphData, isGraphLoading,
    loadFullGraph, lastHybrid, comparisons,
  };
}

export function useAdmin() {
  const {
    indexingTasks, setIndexingTasks, addIndexingTask, refreshIndexingTasks,
    auditLines, setAuditLines, refreshAuditLogs,
    proposedEdges, setProposedEdges, refreshProposedEdges,
    confirmEdge, rejectEdge,
    isPipelineRunning, setIsPipelineRunning,
    isStalenessChecking, setIsStalenessChecking,
  } = useAppState();
  return {
    indexingTasks, setIndexingTasks, addIndexingTask, refreshIndexingTasks,
    auditLines, setAuditLines, refreshAuditLogs,
    proposedEdges, setProposedEdges, refreshProposedEdges,
    confirmEdge, rejectEdge,
    isPipelineRunning, setIsPipelineRunning,
    isStalenessChecking, setIsStalenessChecking,
  };
}
