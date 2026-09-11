import { useState, useEffect, useCallback } from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import FailureCheckboxGrid from "./FailureCheckboxGrid";
import FeedbackInputRow from "./FeedbackInputRow";
import { submitFeedback } from "../../services/api";
import { useAppState } from "../../state/AppState";

/**
 * FeedbackContainer
 * ─────────────────────────────────────────────────────────────────────────────
 * Per-response feedback container positioned as the last child inside the
 * ContextGraph result card. Scoped strictly to response_id.
 */
export default function FeedbackContainer({
  responseId,
  interactionId,
  sessionId,
  turnNumber = 1,
  query = "",
  actorId,
  actorRole,
  isCurrentTurn = true,
}) {
  const { activeUser } = useAppState();

  const effectiveActorId = actorId || activeUser?.username || "compliance_reviewer";
  const effectiveActorRole = actorRole || activeUser?.role || "Compliance & Regulatory Officer";

  const [selectedCodes, setSelectedCodes] = useState(new Set());
  const [freeText, setFreeText] = useState("");
  const [submitState, setSubmitState] = useState("idle"); // 'idle' | 'submitting' | 'success' | 'error'
  const [feedbackId, setFeedbackId] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [lastSubmittedAt, setLastSubmittedAt] = useState(null);

  // Reset form when switching response_id
  useEffect(() => {
    setSelectedCodes(new Set());
    setFreeText("");
    setSubmitState("idle");
    setFeedbackId(null);
    setErrorMessage(null);
    setLastSubmittedAt(null);
  }, [responseId]);

  const isInteractive = isCurrentTurn && submitState !== "submitting";

  const handleCheckboxChange = useCallback((code, checked) => {
    if (!isCurrentTurn) return;
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(code);
      } else {
        next.delete(code);
      }
      return next;
    });
    setSubmitState((prev) => (prev === "error" ? "idle" : prev));
  }, [isCurrentTurn]);

  const canSubmit = isCurrentTurn && (selectedCodes.size > 0 || freeText.trim().length > 0);

  const handleSubmit = async () => {
    if (!isCurrentTurn || !canSubmit || submitState === "submitting") return;

    setSubmitState("submitting");
    setErrorMessage(null);

    const payload = {
      response_id: responseId || `resp_${Date.now()}`,
      interaction_id: interactionId || `int_${sessionId || "session"}`,
      session_id: sessionId || "default_session",
      turn_number: Number(turnNumber) || 1,
      query_text: query || "",
      actor_id: effectiveActorId,
      actor_role: effectiveActorRole,
      selected_categories: Array.from(selectedCodes),
      feedback_text: freeText.trim() || null,
      client_timestamp: new Date().toISOString(),
    };

    try {
      const res = await submitFeedback(payload);
      setFeedbackId(res.feedback_id);
      setLastSubmittedAt(res.stored_at || new Date().toISOString());
      setSubmitState("success");
    } catch (err) {
      console.error("Feedback submission error:", err);
      setErrorMessage(err.message || "Failed to persist feedback. Please try again.");
      setSubmitState("error");
    }
  };

  return (
    <div className={`cg-feedback-container ${!isCurrentTurn ? "cg-feedback-container--disabled" : ""}`}>
      <div className="cg-feedback-header">
        <div className="cg-feedback-eyebrow">
          <span>FEEDBACK &amp; REVIEW AUDIT</span>
          {isCurrentTurn ? (
            <span className="cg-feedback-badge-active">ACTIVE TURN</span>
          ) : (
            <span className="cg-feedback-badge-closed">LOCKED · PREVIOUS TURN</span>
          )}
        </div>
        <div className="cg-feedback-subtitle">
          {isCurrentTurn
            ? "Tag any issues applicable to this response. Hover any option for explanations."
            : "Feedback review is only active on the latest response. This previous turn is locked."}
        </div>
      </div>

      {isCurrentTurn && selectedCodes.size > 0 && (
        <div className="cg-feedback-selection">
          <span>
            <b>{selectedCodes.size}</b> issue{selectedCodes.size === 1 ? "" : "s"} selected
          </span>
          <button type="button" className="cg-feedback-clear-btn" onClick={() => setSelectedCodes(new Set())}>
            Clear all
          </button>
        </div>
      )}

      <FailureCheckboxGrid
        selectedCodes={selectedCodes}
        onChange={handleCheckboxChange}
        disabled={!isInteractive}
      />

      <FeedbackInputRow
        freeText={freeText}
        setFreeText={(val) => {
          if (!isCurrentTurn) return;
          setFreeText(val);
          if (submitState === "error") setSubmitState("idle");
        }}
        canSubmit={canSubmit}
        submitState={submitState}
        disabled={!isCurrentTurn}
        onSubmit={handleSubmit}
      />

      {submitState === "success" && (
        <div className="cg-feedback-status cg-feedback-status--success">
          <span className="cg-feedback-status-icon"><CheckCircle2 size={14} strokeWidth={2} /></span>
          <span>
            <b>Feedback recorded</b> — ID: <code>{feedbackId}</code>
            {lastSubmittedAt && ` at ${new Date(lastSubmittedAt).toLocaleTimeString()}`}
            {effectiveActorId && ` (Reviewer: ${effectiveActorId})`}
          </span>
        </div>
      )}

      {submitState === "error" && isCurrentTurn && (
        <div className="cg-feedback-status cg-feedback-status--error">
          <span className="cg-feedback-status-icon"><AlertTriangle size={14} strokeWidth={2} /></span>
          <span style={{ flex: 1 }}>{errorMessage}</span>
          <button
            type="button"
            className="cg-feedback-retry-btn"
            onClick={handleSubmit}
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
