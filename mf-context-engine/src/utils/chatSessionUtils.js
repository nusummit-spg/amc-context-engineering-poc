/**
 * Utilities for chat sessions management.
 */

/**
 * User-specific storage key helpers ensuring session isolation and persistence across logins.
 */
export function getUserChatSessionsKey(username) {
  return username ? `ns_cg_chat_sessions_v1_${username}` : "ns_cg_chat_sessions_v1";
}

export function getUserActiveSessionIdKey(username) {
  return username ? `ns_cg_active_session_id_v1_${username}` : "ns_cg_active_session_id_v1";
}

/**
 * Check if a session has at least one actual, meaningful user message.
 * Also treats sessions pending full backend history fetch or with turn_count > 0 as valid.
 * @param {object} session
 * @returns {boolean}
 */
export function hasUserMessage(session) {
  if (!session) return false;
  if (session._needsFetch) return true;
  if (typeof session.turn_count === "number" && session.turn_count > 0) return true;
  if (!Array.isArray(session.history)) return false;
  return session.history.some(
    (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim().length > 0
  );
}

/**
 * Filter and sort chat sessions for sidebar display.
 * Only returns sessions that have at least one user message,
 * sorted newest-first by updatedAt or createdAt.
 * @param {Record<string, object>} chatSessions
 * @param {number} [limit=50]
 * @returns {Array<{session_id: string, title: string, words: string[], turn_count: number}>}
 */
export function formatSidebarSessions(chatSessions, limit = 50) {
  if (!chatSessions || typeof chatSessions !== "object") return [];

  return Object.entries(chatSessions)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => {
      const timeA = b[1]?.updatedAt || b[1]?.createdAt || 0;
      const timeB = a[1]?.updatedAt || a[1]?.createdAt || 0;
      return timeA - timeB;
    })
    .slice(0, limit)
    .map(([id, s]) => {
      const firstUserMsg = (s.history || []).find(
        (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim().length > 0
      );
      const userContent = firstUserMsg?.content?.trim() || "";
      const fallbackTitle = userContent
        ? (userContent.length > 45 ? userContent.slice(0, 44) + "…" : userContent)
        : "Conversation";
      const title = (s.title && s.title !== "New Conversation") ? s.title : fallbackTitle;
      const words = title.split(/\s+/).filter(Boolean);
      return {
        session_id: id,
        title,
        words,
        turn_count: s.turn_count || (s.history || []).filter((m) => m.role === "user").length || 1,
      };
    });
}

/**
 * Load and validate user chat sessions from persistent storage with automatic migration.
 * @param {string} username
 * @param {Storage|object} [storage]
 * @returns {Record<string, object>}
 */
export function loadUserChatSessions(username, storage = typeof localStorage !== "undefined" ? localStorage : null) {
  if (!username || !storage) return {};
  const userKey = getUserChatSessionsKey(username);
  let userSessions = null;
  try {
    const raw = storage.getItem(userKey);
    if (raw) userSessions = JSON.parse(raw);
  } catch {}

  if (userSessions === null) {
    try {
      const legacyRaw = storage.getItem("ns_cg_chat_sessions_v1");
      if (legacyRaw) {
        const legacy = JSON.parse(legacyRaw);
        if (legacy && typeof legacy === "object" && Object.keys(legacy).length > 0) {
          storage.setItem(userKey, JSON.stringify(legacy));
          storage.removeItem("ns_cg_chat_sessions_v1");
          userSessions = legacy;
        }
      }
    } catch {}
    if (!userSessions) userSessions = {};
  }

  const cleaned = {};
  for (const [id, s] of Object.entries(userSessions || {})) {
    if (hasUserMessage(s)) {
      cleaned[id] = s;
    }
  }
  return cleaned;
}

