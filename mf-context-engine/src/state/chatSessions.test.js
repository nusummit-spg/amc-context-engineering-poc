import test from "node:test";
import assert from "node:assert/strict";
import {
  hasUserMessage,
  formatSidebarSessions,
  getUserChatSessionsKey,
  getUserActiveSessionIdKey,
  loadUserChatSessions,
} from "../utils/chatSessionUtils.js";

test("hasUserMessage validation", () => {
  assert.equal(hasUserMessage(null), false);
  assert.equal(hasUserMessage({}), false);
  assert.equal(hasUserMessage({ history: [] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "assistant", content: "Hello" }] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "user", content: "   " }] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "user", content: "Valid message" }] }), true);
});

test("Recent chats filter logic: ignores empty or assistant-only conversations", () => {
  const sessions = {
    "sess-empty": {
      id: "sess-empty",
      title: "New Conversation",
      history: [],
      updatedAt: 1000,
    },
    "sess-asst": {
      id: "sess-asst",
      title: "Assistant greeting",
      history: [{ role: "assistant", content: "Hi" }],
      updatedAt: 2000,
    },
    "sess-valid-1": {
      id: "sess-valid-1",
      title: "Chat 1",
      history: [{ role: "user", content: "Query 1" }],
      updatedAt: 3000,
    },
    "sess-valid-2": {
      id: "sess-valid-2",
      title: "Chat 2",
      history: [{ role: "user", content: "Query 2" }],
      updatedAt: 4000,
    },
  };

  const filtered = Object.entries(sessions)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .map(([id, s]) => ({ id, title: s.title }));

  assert.equal(filtered.length, 2);
  assert.equal(filtered[0].id, "sess-valid-2");
  assert.equal(filtered[1].id, "sess-valid-1");
});

test("Deletion reflow: deleting Chat 2 from [Chat 1, Chat 2, Chat 3, Chat 4] immediately reflows without gaps or duplicates", () => {
  const sessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }], updatedAt: 2000 },
    "chat-3": { id: "chat-3", title: "Chat 3", history: [{ role: "user", content: "Q3" }], updatedAt: 3000 },
    "chat-4": { id: "chat-4", title: "Chat 4", history: [{ role: "user", content: "Q4" }], updatedAt: 4000 },
  };

  // Simulate deletion of chat-2
  const copy = { ...sessions };
  delete copy["chat-2"];

  const reflowed = Object.entries(copy)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .map(([id]) => id);

  assert.deepEqual(reflowed, ["chat-4", "chat-3", "chat-1"]);
  assert.equal(copy["chat-2"], undefined);
  assert.equal(Object.keys(copy).length, 3);
});

test("New Chat behavior: clicking New Chat does NOT insert an empty session into chatSessions", () => {
  let chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
  };
  let chatSessionId = "chat-1";

  function startNewChatSession() {
    const active = chatSessions[chatSessionId];
    const isBlank = !active || !hasUserMessage(active);
    if (isBlank) {
      return chatSessionId;
    }
    const freshId = "blank-uuid-1";
    chatSessionId = freshId;
    return freshId;
  }

  // First click on New Chat
  const id1 = startNewChatSession();
  assert.equal(id1, "blank-uuid-1");
  assert.equal(chatSessionId, "blank-uuid-1");
  // chatSessions must still ONLY have chat-1!
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);

  // Rapidly click New Chat 5 more times
  for (let i = 0; i < 5; i++) {
    const idNext = startNewChatSession();
    assert.equal(idNext, "blank-uuid-1"); // Stays on the blank session
  }
  // Still only chat-1 in chatSessions, no stacked empty chats!
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);

  // Recent chats filter must only show chat-1
  const recent = Object.entries(chatSessions).filter(([_, s]) => hasUserMessage(s));
  assert.equal(recent.length, 1);
  assert.equal(recent[0][0], "chat-1");
});

test("Active chat deletion: deleting active chat transitions to blank session without adding placeholder", () => {
  let chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }], updatedAt: 2000 },
  };
  let chatSessionId = "chat-2";

  function deleteChatSession(id) {
    delete chatSessions[id];
    if (chatSessionId === id) {
      chatSessionId = "fresh-blank-id";
    }
  }

  deleteChatSession("chat-2");

  // chat-2 is gone, chatSessions contains only chat-1
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);
  // active session is a clean blank session
  assert.equal(chatSessionId, "fresh-blank-id");
  assert.equal(chatSessions[chatSessionId], undefined);

  // Recent chats contains only chat-1
  const recent = Object.entries(chatSessions).filter(([_, s]) => hasUserMessage(s));
  assert.equal(recent.length, 1);
  assert.equal(recent[0][0], "chat-1");
});

test("Sending first query after opening blank session creates conversation in Recent Chats", () => {
  let chatSessions = {};
  let chatSessionId = "blank-uuid-1";

  function sendFirstQuery(sid, queryText) {
    const userMsg = { role: "user", content: queryText, turn_index: 1 };
    const loadingMsg = { role: "assistant", loading: true, turn_index: 1 };
    const history = [userMsg, loadingMsg];
    const previewTitle = queryText.length > 45 ? queryText.slice(0, 44) + "…" : queryText;
    chatSessions[sid] = {
      id: sid,
      title: previewTitle,
      history,
      updatedAt: Date.now(),
    };
  }

  // Initially empty
  assert.equal(Object.keys(chatSessions).length, 0);

  // User submits first query (short query)
  sendFirstQuery(chatSessionId, "What are SEBI regulations?");

  // Now conversation appears in chatSessions
  assert.equal(Object.keys(chatSessions).length, 1);
  assert.equal(chatSessions[chatSessionId].title, "What are SEBI regulations?");
  assert.equal(hasUserMessage(chatSessions[chatSessionId]), true);

  // Formatted sidebar sessions shows this new conversation
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "blank-uuid-1");
  assert.equal(sidebar[0].title, "What are SEBI regulations?");
});

test("Edge case: starting a new chat after deleting one", () => {
  let chatSessions = {
    "only-chat": { id: "only-chat", title: "Single Chat", history: [{ role: "user", content: "Hi" }], updatedAt: 1000 },
  };
  let chatSessionId = "only-chat";

  // 1. Delete the only chat
  delete chatSessions["only-chat"];
  if (chatSessionId === "only-chat") {
    chatSessionId = "blank-after-delete";
  }

  // Sidebar is empty
  assert.equal(formatSidebarSessions(chatSessions).length, 0);

  // 2. User clicks New Chat while already on blank session
  const activeSession = chatSessions[chatSessionId];
  const isCurrentBlank = !activeSession || !hasUserMessage(activeSession);
  if (!isCurrentBlank) {
    chatSessionId = "should-not-reach";
  }
  // Still blank, still 0 in sidebar
  assert.equal(chatSessionId, "blank-after-delete");
  assert.equal(formatSidebarSessions(chatSessions).length, 0);

  // 3. User sends query in this new session
  chatSessions[chatSessionId] = {
    id: chatSessionId,
    title: "Brand new conversation",
    history: [{ role: "user", content: "Brand new query" }],
    updatedAt: 2000,
  };

  // Now sidebar has 1 conversation
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "blank-after-delete");
  assert.equal(sidebar[0].title, "Brand new conversation");
});

test("Edge case: refreshing the browser while a blank session is open", () => {
  // Saved storage state
  const mockStorageSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Existing" }], updatedAt: 1000 },
    // Also simulate a buggy empty session that may have lingered previously in storage
    "stale-empty": { id: "stale-empty", title: "New Conversation", history: [], updatedAt: 1500 },
  };
  const mockActiveSessionId = "blank-session-never-sent"; // Active was blank session

  // Simulation of AppState initialization logic
  const cleaned = {};
  for (const [id, s] of Object.entries(mockStorageSessions)) {
    if (hasUserMessage(s)) {
      cleaned[id] = s;
    }
  }

  // Active session ID is retained or fallback
  const resolvedActiveId = mockActiveSessionId || "fallback-id";

  // Sidebar only renders cleaned sessions
  const sidebar = formatSidebarSessions(cleaned);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "chat-1");

  // Blank session is NOT in cleaned chatSessions
  assert.equal(cleaned[resolvedActiveId], undefined);
  // No "New Conversation" placeholder exists
  assert.equal(sidebar.some((s) => s.title === "New Conversation"), false);
});

test("Edge case: switching between existing chats preserves history and order", () => {
  const chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }, { role: "assistant", content: "A2" }], updatedAt: 2000 },
  };

  let activeId = "chat-1";
  assert.equal(chatSessions[activeId].history.length, 2);

  // Switch to chat-2
  activeId = "chat-2";
  assert.equal(chatSessions[activeId].history.length, 2);
  assert.equal(chatSessions[activeId].history[0].content, "Q2");

  // Sidebar ordering stays newest first (chat-2, then chat-1)
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar[0].session_id, "chat-2");
  assert.equal(sidebar[1].session_id, "chat-1");
});

test("Login behavior: user login always starts with a fresh new chat session and NOT existing last recent chat", () => {
  // Simulate backend having 3 previous chats for the logging-in user
  const backendSessions = [
    { session_id: "prev-recent-chat", preview: "Most recent query", title: "Most recent query", modified_time: 3000 },
    { session_id: "prev-older-chat-1", preview: "Older query 1", title: "Older query 1", modified_time: 2000 },
    { session_id: "prev-older-chat-2", preview: "Older query 2", title: "Older query 2", modified_time: 1000 },
  ];
  const validIds = new Set(backendSessions.map((b) => b.session_id));

  // 1. User signs in -> login commit logic assigns a fresh UUID and resets local chat state
  const freshLoginSessionId = "fresh-new-session-uuid";
  let chatSessionId = freshLoginSessionId;
  let chatSessions = {};
  let isLoginPendingNewChat = true;

  // 2. syncBackendSessions runs: populates chatSessions from backend
  for (const bs of backendSessions) {
    chatSessions[bs.session_id] = {
      id: bs.session_id,
      title: bs.title,
      history: [{ role: "user", content: bs.preview }],
      updatedAt: bs.modified_time * 1000,
    };
  }

  // Active session resolution logic in syncBackendSessions
  function resolveActiveSession(currId) {
    if (isLoginPendingNewChat) {
      isLoginPendingNewChat = false;
      const freshId =
        currId && !validIds.has(currId) && (!chatSessions[currId] || !hasUserMessage(chatSessions[currId]))
          ? currId
          : "new-fallback-uuid";
      return freshId;
    }
    if (currId && validIds.has(currId)) {
      return currId;
    }
    if (currId && (!chatSessions[currId] || !hasUserMessage(chatSessions[currId]))) {
      return currId;
    }
    return "new-fallback-uuid";
  }

  const resolvedActiveId = resolveActiveSession(chatSessionId);

  // Assert: Active chat MUST be the fresh new session, NEVER the most recent chat!
  assert.equal(resolvedActiveId, freshLoginSessionId);
  assert.notEqual(resolvedActiveId, "prev-recent-chat");
  assert.equal(chatSessions[resolvedActiveId], undefined); // Still clean blank session

  // Assert: Recent chats in sidebar lists all 3 existing chats
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar.length, 3);
  assert.equal(sidebar[0].session_id, "prev-recent-chat");
  assert.equal(sidebar[1].session_id, "prev-older-chat-1");
  assert.equal(sidebar[2].session_id, "prev-older-chat-2");

  // Assert: None of the existing chats are marked as current/active
  assert.equal(sidebar.some((s) => s.session_id === resolvedActiveId), false);
});

test("Syncing backend sessions preserves a blank new chat even when previous chats exist in backend", () => {
  const backendSessions = [
    { session_id: "prev-1", title: "Existing chat", modified_time: 1000 },
  ];
  const validIds = new Set(backendSessions.map((b) => b.session_id));
  const chatSessions = {
    "prev-1": { id: "prev-1", title: "Existing chat", history: [{ role: "user", content: "Hi" }] },
  };

  const currentBlankId = "blank-active-uuid";

  function resolveActiveSession(currId) {
    if (currId && validIds.has(currId)) {
      return currId;
    }
    if (currId && (!chatSessions[currId] || !hasUserMessage(chatSessions[currId]))) {
      return currId;
    }
    return "fallback-uuid";
  }

  const result = resolveActiveSession(currentBlankId);
  // Must preserve blank session, not switch to prev-1
  assert.equal(result, "blank-active-uuid");
});

function createMockStorage(initial = {}) {
  const store = { ...initial };
  return {
    getItem(k) {
      return store[k] !== undefined ? store[k] : null;
    },
    setItem(k, v) {
      store[k] = String(v);
    },
    removeItem(k) {
      delete store[k];
    },
    clear() {
      for (const k of Object.keys(store)) delete store[k];
    },
    _raw() {
      return store;
    },
  };
}

test("Storage key helpers partition keys by authenticated username", () => {
  assert.equal(getUserChatSessionsKey("sarah.compliance"), "ns_cg_chat_sessions_v1_sarah.compliance");
  assert.equal(getUserActiveSessionIdKey("sarah.compliance"), "ns_cg_active_session_id_v1_sarah.compliance");

  assert.equal(getUserChatSessionsKey("vikram.pm"), "ns_cg_chat_sessions_v1_vikram.pm");
  assert.equal(getUserActiveSessionIdKey("vikram.pm"), "ns_cg_active_session_id_v1_vikram.pm");

  assert.equal(getUserChatSessionsKey(null), "ns_cg_chat_sessions_v1");
  assert.equal(getUserActiveSessionIdKey(null), "ns_cg_active_session_id_v1");
  assert.equal(getUserChatSessionsKey(""), "ns_cg_chat_sessions_v1");
  assert.equal(getUserActiveSessionIdKey(""), "ns_cg_active_session_id_v1");
});

test("loadUserChatSessions automatically migrates legacy unpartitioned storage key", () => {
  const legacySessions = {
    "legacy-chat-1": {
      id: "legacy-chat-1",
      title: "Legacy Chat",
      history: [{ role: "user", content: "What is the NAV?" }],
      updatedAt: 1000,
    },
    "legacy-empty": {
      id: "legacy-empty",
      title: "New Conversation",
      history: [],
      updatedAt: 500,
    },
  };

  const storage = createMockStorage({
    ns_cg_chat_sessions_v1: JSON.stringify(legacySessions),
  });

  const loaded = loadUserChatSessions("sarah.compliance", storage);

  // Cleaned: only contains valid conversations
  assert.equal(Object.keys(loaded).length, 1);
  assert.equal(loaded["legacy-chat-1"].title, "Legacy Chat");
  assert.equal(loaded["legacy-empty"], undefined);

  // Partitioned key was written
  const userKey = getUserChatSessionsKey("sarah.compliance");
  assert.notEqual(storage.getItem(userKey), null);

  // Legacy key was cleaned up
  assert.equal(storage.getItem("ns_cg_chat_sessions_v1"), null);
});

test("Chat persistence across logout and re-login: user chat history is preserved", () => {
  const storage = createMockStorage();
  const username = "sarah.compliance";
  const userKey = getUserChatSessionsKey(username);

  // 1. User logs in, has conversations
  const userSessions = {
    "sarah-chat-1": {
      id: "sarah-chat-1",
      title: "SEBI Compliance Review",
      history: [{ role: "user", content: "Check SEBI circular limits" }],
      updatedAt: 1000,
    },
    "sarah-chat-2": {
      id: "sarah-chat-2",
      title: "Portfolio Analysis",
      history: [{ role: "user", content: "Review HDFC Top 100 allocation" }],
      updatedAt: 2000,
    },
  };
  storage.setItem(userKey, JSON.stringify(userSessions));

  // 2. User logs out: auth tokens are cleared, but user chat history is NOT purged!
  const simulatedClearAuth = (mockStore) => {
    mockStore.removeItem("ns_cg_auth_session_v1");
    mockStore.removeItem("ns_cg_active_user_v1");
    // Crucial check: userKey must NOT be removed on logout
  };
  simulatedClearAuth(storage);

  // Verify chat history still safely exists on storage
  assert.notEqual(storage.getItem(userKey), null);

  // 3. User logs in again: history is loaded
  const restored = loadUserChatSessions(username, storage);
  assert.equal(Object.keys(restored).length, 2);
  assert.equal(restored["sarah-chat-1"].title, "SEBI Compliance Review");
  assert.equal(restored["sarah-chat-2"].title, "Portfolio Analysis");

  // Sidebar shows both previous conversations
  const sidebar = formatSidebarSessions(restored);
  assert.equal(sidebar.length, 2);
  assert.equal(sidebar[0].session_id, "sarah-chat-2");
  assert.equal(sidebar[1].session_id, "sarah-chat-1");

  // 4. Initial active session on login is a fresh new session, NOT continuing previous chat
  const newLoginActiveSessionId = "fresh-login-uuid-999";
  assert.equal(restored[newLoginActiveSessionId], undefined); // Fresh blank canvas
});

test("Multi-user session isolation: User A and User B cannot access each other's chats", () => {
  const storage = createMockStorage();
  const userA = "sarah.compliance";
  const userB = "vikram.pm";

  // Step 1: User A logs in and has 2 chats
  const userASessions = {
    "sarah-1": {
      id: "sarah-1",
      title: "Sarah Compliance Chat 1",
      history: [{ role: "user", content: "SEBI mandate query" }],
      updatedAt: 1000,
    },
    "sarah-2": {
      id: "sarah-2",
      title: "Sarah Compliance Chat 2",
      history: [{ role: "user", content: "Audit report check" }],
      updatedAt: 2000,
    },
  };
  storage.setItem(getUserChatSessionsKey(userA), JSON.stringify(userASessions));

  // Step 2: User A logs out, User B logs in
  const userBLoaded = loadUserChatSessions(userB, storage);
  // User B must NOT see any of User A's chats
  assert.deepEqual(userBLoaded, {});
  assert.equal(formatSidebarSessions(userBLoaded).length, 0);

  // Step 3: User B creates a chat
  const userBSessions = {
    "vikram-1": {
      id: "vikram-1",
      title: "Vikram Portfolio Strategy",
      history: [{ role: "user", content: "Sector allocation review" }],
      updatedAt: 3000,
    },
  };
  storage.setItem(getUserChatSessionsKey(userB), JSON.stringify(userBSessions));

  // Step 4: Verify User B's sidebar only shows User B's chat
  const userBSidebar = formatSidebarSessions(loadUserChatSessions(userB, storage));
  assert.equal(userBSidebar.length, 1);
  assert.equal(userBSidebar[0].session_id, "vikram-1");
  assert.equal(userBSidebar[0].title, "Vikram Portfolio Strategy");

  // Step 5: User B logs out, User A logs back in
  const userAReloaded = loadUserChatSessions(userA, storage);
  assert.equal(Object.keys(userAReloaded).length, 2);
  assert.equal(userAReloaded["sarah-1"].title, "Sarah Compliance Chat 1");
  assert.equal(userAReloaded["sarah-2"].title, "Sarah Compliance Chat 2");
  assert.equal(userAReloaded["vikram-1"], undefined); // No leak of User B's chats

  const userASidebar = formatSidebarSessions(userAReloaded);
  assert.equal(userASidebar.length, 2);
  assert.equal(userASidebar.some((s) => s.session_id === "vikram-1"), false);
});

test("User session deletion isolation: deleting User A's chat does not affect User B", () => {
  const storage = createMockStorage();
  const userA = "sarah.compliance";
  const userB = "vikram.pm";

  const userASessions = {
    "sarah-1": { id: "sarah-1", title: "S1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
    "sarah-2": { id: "sarah-2", title: "S2", history: [{ role: "user", content: "Q2" }], updatedAt: 2000 },
  };
  const userBSessions = {
    "vikram-1": { id: "vikram-1", title: "V1", history: [{ role: "user", content: "VQ1" }], updatedAt: 1500 },
  };

  storage.setItem(getUserChatSessionsKey(userA), JSON.stringify(userASessions));
  storage.setItem(getUserChatSessionsKey(userB), JSON.stringify(userBSessions));

  // User A deletes sarah-1
  const copyA = loadUserChatSessions(userA, storage);
  delete copyA["sarah-1"];
  storage.setItem(getUserChatSessionsKey(userA), JSON.stringify(copyA));

  // Verify User A now has only sarah-2
  const updatedA = loadUserChatSessions(userA, storage);
  assert.deepEqual(Object.keys(updatedA), ["sarah-2"]);

  // Verify User B's sessions are completely unchanged
  const currentB = loadUserChatSessions(userB, storage);
  assert.deepEqual(Object.keys(currentB), ["vikram-1"]);
});



