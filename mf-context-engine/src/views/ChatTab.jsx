import { useRef, useState } from "react";
import TextInput from "../components/widgets/TextInput";
import Button from "../components/widgets/Button";
import Expander from "../components/widgets/Expander";
import Divider from "../components/widgets/Divider";
import Alert from "../components/widgets/Alert";
import StreamingAnswer from "../components/widgets/StreamingAnswer";
import { useAppState } from "../state/AppState";
import { useToast } from "../components/widgets/Toast";
import ContextGraphPanel from "./panels/ContextGraphPanel";
import { sendChatStream, adaptHybridResponse } from "../services/api";

export default function ChatTab() {
  const {
    chatSessionId, chatQuery, setChatQuery,
    isChatLoading,
    loadChatSession, sendChatMessage,
    getChatHistory, setChatHistory,
  } = useAppState();
  const pushToast = useToast();

  const [resumeId, setResumeId] = useState("");
  const [resumeError, setResumeError] = useState("");

  // ── Streaming state ──────────────────────────────────────────────────────
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamMetadata, setStreamMetadata] = useState(null);
  const [progressiveSources, setProgressiveSources] = useState([]);
  const abortControllerRef = useRef(null);

  const history = getChatHistory(chatSessionId);

  // ── Streaming send handler ────────────────────────────────────────────────
  const handleSend = async () => {
    const q = chatQuery.trim();
    if (!q || isChatLoading || isStreaming) return;

    const sid = chatSessionId;
    const currentHistory = getChatHistory(sid);
    const turnIndex = Math.floor(currentHistory.length / 2) + 1;

    const userMsg = { role: "user", content: q, turn_index: turnIndex, timestamp: Date.now() };
    const loadingMsg = { role: "assistant", loading: true, turn_index: turnIndex };

    setChatQuery("");
    setIsStreaming(true);
    setStreamingAnswer("");
    setStreamMetadata(null);
    setProgressiveSources([]);
    setChatHistory(sid, (h) => [...h, userMsg, loadingMsg]);

    // Create abort controller for stop button
    const controller = new AbortController();
    abortControllerRef.current = controller;

    let accumulatedAnswer = "";
    let accumulatedMeta = null;
    let finalResponseId = null;

    try {
      await sendChatStream({
        query: q,
        history: currentHistory,
        session_id: sid,
        mode: "contextgraph",
        signal: controller.signal,

        onChunk: (chunk) => {
          accumulatedAnswer += chunk.text;
          setStreamingAnswer(accumulatedAnswer);
        },

        onMetadata: (meta) => {
          accumulatedMeta = { ...(accumulatedMeta || {}), ...meta };
          setStreamMetadata(accumulatedMeta);
        },

        onSources: (sourcesEvent) => {
          setProgressiveSources((prev) => {
            const existing = new Set(prev.map((s) => s.document_id));
            const newSources = (sourcesEvent.sources || []).filter(
              (s) => !existing.has(s.document_id)
            );
            return [...prev, ...newSources];
          });
        },

        onError: (error) => {
          if (error.recoverable) {
            pushToast(`Streaming issue: ${error.message}`, "⚠️");
          } else {
            // Non-recoverable: replace loading placeholder with error message
            setChatHistory(sid, (h) => {
              const next = [...h];
              const idx = next.length - 1;
              next[idx] = {
                role: "assistant",
                loading: false,
                turn_index: turnIndex,
                error_hybrid: error.message,
                content: { error: error.message },
                timestamp: Date.now(),
              };
              return next;
            });
            setIsStreaming(false);
          }
        },

        onComplete: (data) => {
          finalResponseId = data.response_id;
          const rawHybrid = data.hybrid || {
            answer: accumulatedAnswer,
            sources: progressiveSources,
            response_id: data.response_id,
            ...(accumulatedMeta || {}),
          };
          const adapted = adaptHybridResponse(rawHybrid, rawHybrid?.latency_ms);

          // Commit final streamed answer to history with full ContextGraph fidelity
          setChatHistory(sid, (h) => {
            const next = [...h];
            const idx = next.length - 1;
            next[idx] = {
              role: "assistant",
              loading: false,
              turn_index: turnIndex,
              hybrid: adapted,
              content: accumulatedAnswer || adapted?.answer || "No answer generated.",
              resolvedQuery: q,
              timestamp: Date.now(),
            };
            return next;
          });
          setIsStreaming(false);
          setStreamingAnswer("");
          setProgressiveSources([]);
        },
      });
    } catch (err) {
      if (err.name === "AbortError") {
        // User clicked Stop — commit whatever was streamed so far
        const rawHybrid = {
          answer: accumulatedAnswer + " [stopped]",
          sources: progressiveSources,
          response_id: finalResponseId || `resp_${turnIndex}_${sid}`,
          ...(accumulatedMeta || {}),
        };
        const adapted = adaptHybridResponse(rawHybrid);
        setChatHistory(sid, (h) => {
          const next = [...h];
          const idx = next.length - 1;
          next[idx] = {
            role: "assistant",
            loading: false,
            turn_index: turnIndex,
            hybrid: adapted,
            content: accumulatedAnswer + " [stopped]",
            timestamp: Date.now(),
          };
          return next;
        });
      } else {
        // Stream failed entirely — fall back to synchronous path
        pushToast(`Streaming failed, falling back to sync mode: ${err.message}`, "⚠️");
        try {
          await sendChatMessage(q);
        } catch (syncErr) {
          pushToast(`Failed to send message: ${syncErr.message}`, "❌");
        }
      }
      setIsStreaming(false);
      setStreamingAnswer("");
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
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
      <div className="stChatInputBar">
        <div className="stChatInputBar-input">
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
        <div className="stChatInputBar-button">
          <Button kind="primary" fullWidth disabled={isChatLoading || isStreaming || !chatQuery.trim()} onClick={handleSend}>
            {isChatLoading ? "Sending…" : isStreaming ? "Streaming…" : "Send"}
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

      {/* Progressive sources panel — shown while streaming */}
      {isStreaming && progressiveSources.length > 0 && (
        <div style={{ marginBottom: "0.5rem", padding: "0.5rem", background: "rgba(0,0,0,0.03)", borderRadius: "6px" }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem", opacity: 0.7 }}>
            📚 Sources found ({progressiveSources.length})
          </div>
          {progressiveSources.slice(0, 5).map((src, i) => (
            <div key={i} style={{ fontSize: "0.78rem", opacity: 0.8, marginLeft: "0.5rem" }}>
              • {src.document_title || src.document_id}
            </div>
          ))}
        </div>
      )}

      {/* Inline streaming answer — shown while answer is being streamed */}
      {isStreaming && streamingAnswer && (
        <div style={{ marginBottom: "1rem", padding: "0.75rem", border: "1px solid rgba(0,0,0,0.08)", borderRadius: "8px" }}>
          <StreamingAnswer
            content={streamingAnswer}
            isStreaming={isStreaming}
            onStop={handleStop}
          />
        </div>
      )}

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
