import { useState } from "react";
import { Share2, FileSearch, MessageSquareText, Copy, Check } from "lucide-react";
import MarkdownAnswer from "../../components/provenance/MarkdownAnswer";
import AnswerCard40, { IncompleteBanner } from "../../components/answer40/AnswerCard40";
import FeedbackBar40 from "../../components/answer40/FeedbackBar40";
import { answerKindOf, confidenceLabelFor, isPilotFeedbackEnabled } from "../../utils/answer40";
import { isPilotMode } from "../../utils/pilotSources";

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
  onPickPrompt,
}) {
  const [copied, setCopied] = useState(false);
  // Read-only pilot: feedback capture posts to a denied route and the pilot has no graph context to
  // show, so neither action is offered (a button that cannot work is worse than no button).
  const pilot = isPilotMode();

  if (!r) return null;

  const answerText = typeof r.answer === "string" ? r.answer : (r.answer?.answer || "");
  const sourceCount = (
    r.citations && r.citations.length > 0
      ? r.citations
      : (r.provenance && r.provenance.length > 0 ? r.provenance : r.docs || [])
  ).length;
  const confidenceLabel = confidenceLabelFor(r);
  const isLowConfidence = /moderate|low/i.test(confidenceLabel || "");
  const showBody = !r.incomplete || answerText.trim() !== "";

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
        {confidenceLabel && (
          <span className={`cg-msg-confidence ${isLowConfidence ? "cg-msg-confidence--low" : ""}`}>
            {confidenceLabel}
          </span>
        )}
        {timestamp && (
          <time className="cg-msg-time" dateTime={new Date(timestamp).toISOString()}>
            {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </time>
        )}
      </div>

      <IncompleteBanner state={r.incomplete} />
      <div className="cg-answer" data-answer-kind={answerKindOf(r)}>
        {!showBody ? null : answerKindOf(r) === "DOCUMENT" ? (
          <MarkdownAnswer
            text={answerText}
            citations={r.citations || r.docs || []}
            metrics={r.metrics || []}
          />
        ) : (
          <AnswerCard40 r={r} query={query} onPickPrompt={onPickPrompt} />
        )}
        {r.has_gaps && r.gap_description && (
          <p className="a40-note" role="note" data-testid="answer-gaps">{r.gap_description}</p>
        )}
      </div>
      {pilot && isPilotFeedbackEnabled() && !r.incomplete && answerKindOf(r) !== "CLARIFY" && (
        <FeedbackBar40 key={r.request_id} requestId={r.request_id} />
      )}

      <div className="cg-msg-actions">
        {!pilot && (
        <button
          type="button"
          className="cg-msg-action-btn"
          onClick={() => onOpenOntology?.({ r, entitySummary, query })}
          title="View the graph/ontology context for this response"
        >
          <Share2 size={13} strokeWidth={1.75} />
          Ontology View
        </button>
        )}
        <button
          type="button"
          className="cg-msg-action-btn"
          onClick={() => onOpenEvidence?.({ r, entitySummary, query, responseId, turnNumber })}
          title="View evidence, sources and retrieval details for this response"
        >
          <FileSearch size={13} strokeWidth={1.75} />
          Evidence{sourceCount > 0 ? ` (${sourceCount})` : ""}
        </button>
        {showFeedback && !pilot && (
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
                pendingFeedbackNotice: r.pending_feedback_notice,
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
