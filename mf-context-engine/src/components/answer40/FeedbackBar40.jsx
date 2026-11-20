import { useId, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { submitFeedback40 } from "../../services/api";
import { FEEDBACK_REASONS } from "../../utils/answer40";

/**
 * Pilot feedback (TDS-40 E7/E11.2): one rating per answer, bound server-side to the caller's own evidence row by
 * request id. Shown only when the build enables it AND the answer has a request id. A 404 (flag off on the
 * server) hides the bar instead of showing an error.
 */
export default function FeedbackBar40({ requestId }) {
  const [state, setState] = useState("idle");      // idle | down | sending | done | error | hidden
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const reasonId = useId();
  const commentId = useId();

  if (!requestId || state === "hidden") return null;

  const send = async (rating, why) => {
    setState("sending");
    setError("");
    try {
      await submitFeedback40({ request_id: requestId, rating, reason: why, comment: comment.trim() || null });
      setState("done");
    } catch (err) {
      if (err.status === 404) {
        setState("hidden");
      } else if (err.status === 409) {
        setState("done");
      } else {
        setError("Feedback could not be saved. Please try again.");
        setState(rating === "DOWN" ? "down" : "idle");
      }
    }
  };

  if (state === "done") {
    return <p className="a40-feedback a40-feedback--done" role="status" data-testid="feedback-done">Thanks — your feedback was recorded.</p>;
  }

  return (
    <div className="a40-feedback" data-testid="feedback-bar">
      {state !== "down" && (
        <>
          <span className="a40-feedback-label" id={`${reasonId}-q`}>Was this answer right?</span>
          <button type="button" className="cg-msg-action-btn" aria-describedby={`${reasonId}-q`}
                  disabled={state === "sending"} onClick={() => send("UP", "HELPFUL")}>
            <ThumbsUp size={13} aria-hidden="true" /> Yes
          </button>
          <button type="button" className="cg-msg-action-btn" aria-describedby={`${reasonId}-q`}
                  disabled={state === "sending"} onClick={() => setState("down")}>
            <ThumbsDown size={13} aria-hidden="true" /> No
          </button>
        </>
      )}
      {state === "down" && (
        <form className="a40-feedback-form" onSubmit={(e) => { e.preventDefault(); if (reason) send("DOWN", reason); }}>
          <label htmlFor={reasonId}>What was wrong?</label>
          <select id={reasonId} value={reason} onChange={(e) => setReason(e.target.value)} required>
            <option value="">Choose a reason</option>
            {FEEDBACK_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          <label htmlFor={commentId} className="a40-sr-only">Comment (optional)</label>
          <input id={commentId} type="text" maxLength={1000} placeholder="Optional comment (no personal details)"
                 value={comment} onChange={(e) => setComment(e.target.value)} />
          <button type="submit" className="cg-msg-action-btn" disabled={!reason}>Send</button>
          <button type="button" className="cg-msg-action-btn" onClick={() => setState("idle")}>Cancel</button>
        </form>
      )}
      {error && <p className="a40-feedback-error" role="alert">{error}</p>}
    </div>
  );
}
