import { useState } from "react";
import TextInput from "../components/widgets/TextInput";
import Button from "../components/widgets/Button";
import Expander from "../components/widgets/Expander";
import Divider from "../components/widgets/Divider";
import Alert from "../components/widgets/Alert";
import { useAppState } from "../state/AppState";
import { useToast } from "../components/widgets/Toast";
import ContextGraphPanel from "./panels/ContextGraphPanel";

export default function ChatTab() {
  const {
    chatSessionId, chatQuery, setChatQuery,
    isChatLoading, getChatHistory,
    startNewChatSession, loadChatSession, sendChatMessage,
    clearCache, isCacheClearing,
  } = useAppState();
  const pushToast = useToast();

  const [resumeId, setResumeId] = useState("");
  const [resumeError, setResumeError] = useState("");

  const history = getChatHistory(chatSessionId);

  const handleClearCache = async () => {
    const ok = await clearCache();
    if (ok) {
      pushToast("Intent Cache cleared cleanly! Next query will execute full LLM synthesis.", "⚡");
    } else {
      pushToast("Intent Cache flushed locally.", "⚡");
    }
  };

  const handleSend = async () => {
    if (!chatQuery.trim() || isChatLoading) return;
    await sendChatMessage();
  };

  const handleResumeLoad = () => {
    if (!resumeId.trim()) return;
    const ok = loadChatSession(resumeId.trim());
    if (!ok) {
      setResumeError("No saved session found with that ID.");
    } else {
      setResumeError("");
      pushToast("Loaded saved conversation session!", "📂");
    }
  };

  const turns = [];
  for (let i = 0; i < history.length; i += 2) {
    turns.push([history[i], history[i + 1]]);
  }

  return (
    <div>
      <div className="stRow">
        <div className="stCol" style={{ flex: 4.0 }}>
          <TextInput
            value={chatQuery}
            onChange={setChatQuery}
            labelVisible={false}
            placeholder="Ask a follow-up — conversation context carries forward…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
        </div>
        <div className="stCol" style={{ flex: 0.8 }}>
          <Button kind="primary" fullWidth disabled={isChatLoading || !chatQuery.trim()} onClick={handleSend}>
            {isChatLoading ? "Sending…" : "Send"}
          </Button>
        </div>
        <div className="stCol" style={{ flex: 1.1 }}>
          <Button
            kind="secondary"
            fullWidth
            onClick={() => {
              startNewChatSession();
              pushToast("Started new chat session", "✨");
            }}
          >
            🔄 New Session
          </Button>
        </div>
        <div className="stCol" style={{ flex: 1.1 }}>
          <Button
            kind="secondary"
            fullWidth
            disabled={isCacheClearing}
            title="Flush in-memory and disk intent cache so next query performs fresh LLM synthesis"
            onClick={handleClearCache}
          >
            {isCacheClearing ? "Flushing…" : "🗑️ Clear Cache"}
          </Button>
        </div>
      </div>

      <Expander title={<>Session: <code>{chatSessionId}</code>  ·  resume a previous session</>}>
        <TextInput
          value={resumeId}
          onChange={setResumeId}
          labelVisible={false}
          placeholder="Paste a session ID and press Enter…"
        />
        {resumeId && (
          <div style={{ marginTop: 8 }}>
            <Button kind="secondary" onClick={handleResumeLoad}>Load session</Button>
          </div>
        )}
        {resumeError && <div style={{ marginTop: 8 }}><Alert type="error">{resumeError}</Alert></div>}
      </Expander>

      {[...turns].reverse().map(([userMsg, asstMsg], i) => (
        <div key={i}>
          <div style={{ fontSize: "1rem", margin: "0.5rem 0" }}>
            <b>Turn {userMsg.turn_index ?? 1}:</b> {userMsg.content}
          </div>
          {!asstMsg ? (
            <Divider />
          ) : asstMsg.loading ? (
            <>
              <div className="stRow">
                <div className="stCol" style={{ flex: 1 }}>
                  <Alert type="info">ContextGraph is generating…</Alert>
                </div>
              </div>
              <Divider />
            </>
          ) : (
            <>
              {asstMsg.error_hybrid && <Alert type="error">ContextGraph failed: {asstMsg.error_hybrid}</Alert>}
              {asstMsg.hybrid && (
                <div className="stRow">
                  <div className="stCol" style={{ flex: 1 }}>
                    <ContextGraphPanel
                      r={asstMsg.hybrid}
                      entitySummary={asstMsg.hybrid.entity_summary}
                      responseId={asstMsg.hybrid.response_id || `resp_${asstMsg.turn_index || (userMsg?.turn_index ?? 1)}_${chatSessionId}`}
                      interactionId={asstMsg.hybrid.interaction_id || `int_${chatSessionId}`}
                      sessionId={chatSessionId}
                      turnNumber={asstMsg.turn_index || (userMsg?.turn_index ?? 1)}
                      query={userMsg?.content || ""}
                      showFeedback={true}
                      isCurrentTurn={i === 0}
                    />
                  </div>
                </div>
              )}
              <Divider />
            </>
          )}
        </div>
      ))}
    </div>
  );
}
