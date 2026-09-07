import { useRef, useState, useEffect } from "react";
import { BookOpen, ArrowUp, Square, ChevronDown } from "lucide-react";
import Alert from "../components/widgets/Alert";
import AutoGrowTextarea from "../components/widgets/AutoGrowTextarea";
import StreamingAnswer from "../components/widgets/StreamingAnswer";
import { useAppState } from "../state/AppState";
import { useToast } from "../components/widgets/Toast";
import AssistantMessage from "./chat/AssistantMessage";
import EvidenceModal from "./chat/EvidenceModal";
import OntologyModal from "./chat/OntologyModal";
import FeedbackModal from "./chat/FeedbackModal";
import { sendChatStream, adaptHybridResponse } from "../services/api";

const STARTER_PROMPTS = [
  "Which schemes breached SEBI exposure limits this quarter?",
  "Summarise our ESG disclosure obligations",
  "What remediation items are past their SLA?",
];

export default function ChatTab() {
  const {
    chatSessions,
    chatSessionId, chatQuery, setChatQuery,
    isChatLoading,
    sendChatMessage,
    getChatHistory, setChatHistory,
    generateConversationTitle,
  } = useAppState();
  const pushToast = useToast();

  // ── Streaming state ──────────────────────────────────────────────────────
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamMetadata, setStreamMetadata] = useState(null);
  const [progressiveSources, setProgressiveSources] = useState([]);
  const abortControllerRef = useRef(null);

  // ── Evidence / Ontology / Feedback modal state (scoped per response) ────
  const [evidenceData, setEvidenceData] = useState(null);
  const [ontologyData, setOntologyData] = useState(null);
  const [feedbackData, setFeedbackData] = useState(null);

  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // The conversation scrolls inside .stMain, so the jump-to-latest affordance
  // has to watch that element rather than the window.
  useEffect(() => {
    const scroller = document.querySelector(".stMain");
    if (!scroller) return undefined;
    const onScroll = () => {
      const gap = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
      setIsAtBottom(gap < 160);
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, []);

  const history = getChatHistory(chatSessionId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, streamingAnswer, isStreaming]);

  // ── Streaming send handler ────────────────────────────────────────────────
  const handleSend = async () => {
    const q = chatQuery.trim();
    if (!q || isChatLoading || isStreaming) return;

    const sid = chatSessionId;
    const currentHistory = getChatHistory(sid);
    const turnIndex = Math.floor(currentHistory.length / 2) + 1;

    // Automatically generate concise title on initial query in parallel
    if (turnIndex === 1 && !chatSessions[sid]?.isTitleGenerated) {
      generateConversationTitle(sid, q);
    }

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
            pushToast(`Streaming issue: ${error.message}`);
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
        pushToast(`Streaming failed, falling back to sync mode: ${err.message}`);
        try {
          await sendChatMessage(q);
        } catch (syncErr) {
          pushToast(`Failed to send message: ${syncErr.message}`);
        }
      }
      setIsStreaming(false);
      setStreamingAnswer("");
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const turns = [];
  for (let i = 0; i < history.length; i += 2) {
    turns.push([history[i], history[i + 1]]);
  }
  const lastTurnIdx = turns.length - 1;

  return (
    <div className="cg-chat-tab">
      <div className="cg-chat-scroll">
        {turns.length === 0 && !isStreaming && (
          <div className="cg-chat-empty">
            <div className="cg-chat-empty-title">What would you like to know?</div>
            <div className="cg-chat-empty-sub">
              Ask about compliance, funds, or governance. Every answer cites the documents it came from,
              and follow-up questions keep the context of this conversation.
            </div>
            <div className="cg-chat-starters">
              {STARTER_PROMPTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="cg-chat-starter"
                  onClick={() => {
                    setChatQuery(p);
                    inputRef.current?.focus();
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map(([userMsg, asstMsg], i) => (
          <div key={i} className="cg-msg-group">
            <div className="cg-msg-user">{userMsg.content}</div>

            {!asstMsg ? null : asstMsg.loading ? (
              i === lastTurnIdx && isStreaming && streamingAnswer ? (
                <div className="cg-msg-assistant cg-msg-assistant--streaming">
                  <StreamingAnswer content={streamingAnswer} isStreaming={isStreaming} />
                  {progressiveSources.length > 0 && (
                    <div className="cg-progressive-sources">
                      <div className="cg-progressive-sources-head">
                        <BookOpen size={14} strokeWidth={1.75} />
                        Sources found ({progressiveSources.length})
                      </div>
                      {progressiveSources.slice(0, 5).map((src, si) => (
                        <div key={si} className="cg-progressive-source-item">
                          &bull; {src.document_title || src.document_id}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="cg-msg-assistant">
                  <div className="cg-thinking" role="status" aria-live="polite">
                    <span className="cg-thinking-dots" aria-hidden="true">
                      <span /><span /><span />
                    </span>
                    <span className="cg-thinking-text">
                      {progressiveSources.length > 0
                        ? `Reading ${progressiveSources.length} source${progressiveSources.length === 1 ? "" : "s"}…`
                        : "Searching documents and graph…"}
                    </span>
                  </div>
                </div>
              )
            ) : (
              <>
                {asstMsg.error_hybrid && (
                  <div className="cg-msg-assistant">
                    <Alert type="error">ContextGraph failed: {asstMsg.error_hybrid}</Alert>
                  </div>
                )}
                {asstMsg.hybrid && (
                  <AssistantMessage
                    r={asstMsg.hybrid}
                    entitySummary={asstMsg.hybrid.entity_summary}
                    responseId={asstMsg.hybrid.response_id || `resp_${asstMsg.turn_index || (userMsg?.turn_index ?? 1)}_${chatSessionId}`}
                    interactionId={asstMsg.hybrid.interaction_id || `int_${chatSessionId}`}
                    sessionId={chatSessionId}
                    turnNumber={asstMsg.turn_index || (userMsg?.turn_index ?? 1)}
                    query={userMsg?.content || ""}
                    timestamp={asstMsg.timestamp}
                    showFeedback={true}
                    isCurrentTurn={i === lastTurnIdx}
                    onOpenEvidence={setEvidenceData}
                    onOpenOntology={setOntologyData}
                    onOpenFeedback={setFeedbackData}
                  />
                )}
              </>
            )}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      <div className="cg-chat-bottom-bar">
        {!isAtBottom && turns.length > 0 && (
          <button
            type="button"
            className="cg-scroll-bottom-btn"
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })}
            title="Jump to the latest message"
            aria-label="Jump to the latest message"
          >
            <ChevronDown size={16} strokeWidth={2} />
          </button>
        )}
        <div className="cg-chatgpt-query-box">
          <AutoGrowTextarea
            ref={inputRef}
            className="cg-chatgpt-query-input"
            value={chatQuery}
            onChange={setChatQuery}
            onSubmit={handleSend}
            maxRows={10}
            placeholder={
              turns.length === 0
                ? "Ask about compliance, funds, or governance…"
                : "Ask a follow-up — conversation context carries forward…"
            }
            disabled={isChatLoading || isStreaming}
          />
          <button
            type="button"
            className={`cg-chatgpt-send-btn ${isStreaming ? "cg-chatgpt-send-btn--streaming" : ""}`}
            disabled={isChatLoading || (!isStreaming && !chatQuery.trim())}
            onClick={isStreaming ? handleStop : handleSend}
            title={isStreaming ? "Stop generating" : "Send message"}
            aria-label={isStreaming ? "Stop generating" : "Send message"}
          >
            {isStreaming ? (
              <Square size={13} fill="currentColor" strokeWidth={0} />
            ) : (
              <ArrowUp size={18} strokeWidth={2.5} />
            )}
          </button>
        </div>
        <div className="cg-chat-input-hint">
          <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line · answers cite their sources
        </div>
      </div>

      <EvidenceModal open={!!evidenceData} data={evidenceData} onClose={() => setEvidenceData(null)} />
      <OntologyModal open={!!ontologyData} data={ontologyData} onClose={() => setOntologyData(null)} />
      <FeedbackModal open={!!feedbackData} data={feedbackData} onClose={() => setFeedbackData(null)} />
    </div>
  );
}
