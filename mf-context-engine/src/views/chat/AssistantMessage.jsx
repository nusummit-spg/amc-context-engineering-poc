import { useState } from "react";
import { Share2, FileSearch, MessageSquareText, Copy, Check } from "lucide-react";
import MarkdownAnswer from "../../components/provenance/MarkdownAnswer";

export default function AssistantMessage({
  r,
  entitySummary,
  responseId,
  interactionId,
  sessionId,
  turnNumber,
  query,
  timestamp,
  actorId,
  actorRole,
  isCurrentTurn = true,
  showFeedback = true,
  onOpenEvidence,
  onOpenOntology,
  onOpenFeedback,
}) {
  const [copied, setCopied] = useState(false);

  if (!r) return null;

  const answerText = typeof r.answer === "string" ? r.answer : (r.answer?.answer || "");
  const sourceCount = (
    r.citations && r.citations.length > 0
      ? r.citations
      : (r.provenance && r.provenance.length > 0 ? r.provenance : r.docs || [])
  ).length;
  const isLowConfidence = /moderate|low/i.test(r.confidence_label || "");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(answerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — the button simply does nothing */
    }
  };

  return (
    <div className="cg-msg-assistant">
      <div className="cg-msg-assistant-head">
        <span className="cg-msg-assistant-mark" aria-hidden="true">CG</span>
        <span className="cg-msg-assistant-name">ContextGraph</span>
        {r.confidence_label && (
          <span className={`cg-msg-confidence ${isLowConfidence ? "cg-msg-confidence--low" : ""}`}>
            {r.confidence_label}
          </span>
        )}
        {timestamp && (
          <time className="cg-msg-time" dateTime={new Date(timestamp).toISOString()}>
            {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </time>
        )}
      </div>

      <div className="cg-answer">
        <MarkdownAnswer
          text={answerText}
          citations={r.citations || r.docs || []}
          metrics={r.metrics || []}
        />
      </div>

      <div className="cg-msg-actions">
        <button
          type="button"
          className="cg-msg-action-btn"
          onClick={() => onOpenOntology?.({ r, entitySummary, query })}
          title="View the graph/ontology context for this response"
        >
          <Share2 size={13} strokeWidth={1.75} />
          Ontology View
        </button>
        <button
          type="button"
          className="cg-msg-action-btn"
          onClick={() => onOpenEvidence?.({ r, entitySummary, query, responseId, turnNumber })}
          title="View evidence, sources and retrieval details for this response"
        >
          <FileSearch size={13} strokeWidth={1.75} />
          Evidence{sourceCount > 0 ? ` (${sourceCount})` : ""}
        </button>
        {showFeedback && (
          <button
            type="button"
            className="cg-msg-action-btn"
            disabled={!isCurrentTurn}
            onClick={() =>
              onOpenFeedback?.({
                responseId: responseId || r.response_id || `resp_${turnNumber || 1}`,
                interactionId: interactionId || r.interaction_id || `int_${sessionId || "cg"}`,
                sessionId: sessionId || r.session_id || "session_default",
                turnNumber: turnNumber || r.turn_number || r.turn_index || 1,
                query: query || r.query || "",
                actorId,
                actorRole,
                isCurrentTurn,
              })
            }
            title={isCurrentTurn ? "Rate or flag issues with this response" : "Feedback is only available on the latest response"}
          >
            <MessageSquareText size={13} strokeWidth={1.75} />
            Feedback
          </button>
        )}
        <button
          type="button"
          className="cg-msg-action-btn cg-msg-action-btn--icon"
          onClick={handleCopy}
          title="Copy this answer"
          aria-label="Copy this answer"
        >
          {copied ? <Check size={13} strokeWidth={2} /> : <Copy size={13} strokeWidth={1.75} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
