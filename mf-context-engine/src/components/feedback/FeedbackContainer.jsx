import { useState, useEffect, useCallback } from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Users } from "lucide-react";
import FailureCheckboxGrid from "./FailureCheckboxGrid";
import FeedbackInputRow from "./FeedbackInputRow";
import { submitFeedback, fetchPendingFeedbackNotice, fetchFeedbackStatus } from "../../services/api";
import { useAppState } from "../../state/AppState";
import { FEATURES } from "../../config/features";
import { FAILURE_TAXONOMY } from "../../constants/failureTaxonomy";

const TAXONOMY_BY_CODE = Object.fromEntries(
  FAILURE_TAXONOMY.map((item) => [item.code.toUpperCase(), item])
);

/**
 * FeedbackContainer
 * ─────────────────────────────────────────────────────────────────────────────
 * Per-response feedback container positioned as the last child inside the
 * ContextGraph result card or within the FeedbackModal. Scoped strictly to response_id.
 */
export default function FeedbackContainer({
  responseId,
  interactionId,
  sessionId,
  turnNumber = 1,
  query = "",
  actorId,
  actorRole,
  tenantId,
  isCurrentTurn = true,
  pendingFeedbackNotice = null,
}) {
  const { activeUser } = useAppState();

  const isFeedbackStatusEnabled = import.meta.env?.VITE_ENABLE_FEEDBACK_STATUS_AWARENESS !== "false";

  const effectiveActorId = actorId || activeUser?.username || "compliance_reviewer";
  const effectiveActorRole = actorRole || activeUser?.role || "Compliance & Regulatory Officer";

  const [selectedCodes, setSelectedCodes] = useState(new Set());
  const [freeText, setFreeText] = useState("");
  const [submitState, setSubmitState] = useState("idle"); // 'idle' | 'submitting' | 'success' | 'error'
  const [feedbackId, setFeedbackId] = useState(null);
  const [submittedIssueInfo, setSubmittedIssueInfo] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [lastSubmittedAt, setLastSubmittedAt] = useState(null);
  const [notice, setNotice] = useState(pendingFeedbackNotice);
  const [issueStatus, setIssueStatus] = useState(null);
  const [isCategoryBreakdownExpanded, setIsCategoryBreakdownExpanded] = useState(false);

  // Status check when modal / container mounts or query changes (non-blocking)
  useEffect(() => {
    if (!isFeedbackStatusEnabled) {
      setIssueStatus(null);
      return;
    }
    if (!query && !responseId) {
      setIssueStatus(null);
      return;
    }

    let active = true;
    fetchFeedbackStatus({
      responseId: responseId || undefined,
      query: query || undefined,
      sessionId: sessionId || undefined,
      tenantId: tenantId || undefined,
    })
      .then((res) => {
        if (active && res?.has_existing_issue) {
          setIssueStatus(res);
        } else if (active) {
          setIssueStatus(null);
        }
      })
      .catch((err) => {
        console.warn("Issue status check failed:", err);
        if (active) setIssueStatus(null);
      });

    return () => {
      active = false;
    };
  }, [isFeedbackStatusEnabled, responseId, query, sessionId, tenantId]);

  useEffect(() => {
    if (pendingFeedbackNotice !== undefined && pendingFeedbackNotice !== null) {
      setNotice(pendingFeedbackNotice);
      return;
    }
    if (!query) {
      setNotice(null);
      return;
    }
    let active = true;
    fetchPendingFeedbackNotice({
      query,
      sessionId: sessionId || undefined,
      actorId: effectiveActorId || undefined,
    })
      .then((res) => {
        if (active) setNotice(res);
      })
      .catch(() => {
        if (active) setNotice(null);
      });
    return () => {
      active = false;
    };
  }, [pendingFeedbackNotice, query, sessionId, effectiveActorId]);

  // Reset form when switching response_id
  useEffect(() => {
    setSelectedCodes(new Set());
    setFreeText("");
    setSubmitState("idle");
    setFeedbackId(null);
    setSubmittedIssueInfo(null);
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
      if (res.issue_id) {
        setSubmittedIssueInfo({
          issueId: res.issue_id,
          issueStatus: res.issue_status,
          wasMatched: res.was_matched_to_existing_issue,
          matchType: res.match_type,
        });
      }
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

      {/* Contextual Feedback Status Awareness Banner (Phase 2) */}
      {isFeedbackStatusEnabled && issueStatus?.has_existing_issue && (
        <div className="cg-issue-awareness-banner" role="status">
          <div className="cg-issue-awareness-banner-header">
            <div className="cg-issue-awareness-banner-icon">
              <AlertCircle size={16} />
            </div>
            <div className="cg-issue-awareness-banner-content">
              <div className="cg-issue-awareness-title">
                <span>Issue Status Awareness</span>
                {issueStatus.status && (
                  <span className={`cg-issue-awareness-status-pill cg-issue-status--${issueStatus.status}`}>
                    {issueStatus.status.replace("_", " ")}
                  </span>
                )}
                {issueStatus.match_type && (
                  <span className="cg-issue-awareness-match-pill">
                    {issueStatus.match_type} match
                  </span>
                )}
              </div>
              <div className="cg-issue-awareness-message">
                {issueStatus.message || "A similar query has already been reported. The issue is pending review or repair."}
              </div>
              {Boolean(issueStatus.contributor_count && issueStatus.contributor_count > 0) && (
                <div className="cg-issue-awareness-contributors">
                  <Users size={12} />
                  <span>
                    {issueStatus.contributor_count} {issueStatus.contributor_count === 1 ? "user has" : "users have"} reported this issue so far
                  </span>
                </div>
              )}

              {/* Phase 4: Category Breakdown Pills */}
              {FEATURES.FEEDBACK_CATEGORY_BREAKDOWN_BANNER_ENABLED &&
                issueStatus.category_breakdown &&
                issueStatus.category_breakdown.length > 0 && (
                  <div className="cg-issue-category-breakdown">
                    <div className="cg-issue-category-header">Previously flagged:</div>
                    <div className="cg-issue-category-pills">
                      {(isCategoryBreakdownExpanded
                        ? issueStatus.category_breakdown
                        : issueStatus.category_breakdown.slice(0, 5)
                      ).map((cat) => {
                        const codeUpper = (cat.code || "").toUpperCase();
                        const taxInfo = TAXONOMY_BY_CODE[codeUpper];
                        const label = cat.label || taxInfo?.label || codeUpper;
                        const tooltip = taxInfo?.tooltip || `${label} (${codeUpper})`;
                        const count = cat.count || 1;

                        return (
                          <span
                            key={codeUpper}
                            className="cg-category-breakdown-pill"
                            title={tooltip}
                          >
                            <span className="cg-category-breakdown-code">{codeUpper}</span>
                            <span className="cg-category-breakdown-label">{label}</span>
                            {count > 1 && (
                              <span className="cg-category-breakdown-multiplier">
                                &times;{count}
                              </span>
                            )}
                          </span>
                        );
                      })}

                      {issueStatus.category_breakdown.length > 5 && (
                        <button
                          type="button"
                          className="cg-category-breakdown-expander"
                          onClick={() => setIsCategoryBreakdownExpanded((prev) => !prev)}
                          title={
                            isCategoryBreakdownExpanded
                              ? "Show top 5 categories"
                              : "Show all flagged categories"
                          }
                        >
                          {isCategoryBreakdownExpanded
                            ? "Show less"
                            : `+${issueStatus.category_breakdown.length - 5} more`}
                        </button>
                      )}
                    </div>
                  </div>
              )}

              <div className="cg-issue-awareness-note">
                You can still submit additional feedback below.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Fallback pending notice when issue status banner is not shown */}
      {(!isFeedbackStatusEnabled || !issueStatus?.has_existing_issue) && notice?.has_pending_feedback && (
        <div className="cg-pending-feedback-banner" role="status">
          <div className="cg-pending-feedback-banner-header">
            <div className="cg-pending-feedback-banner-icon">
              <AlertCircle size={16} />
            </div>
            <div className="cg-pending-feedback-banner-content">
              <div className="cg-pending-feedback-title">
                Similar Feedback Already Submitted
                {notice.match_count && notice.match_count > 1 ? (
                  <span className="cg-pending-feedback-badge">
                    {notice.match_count} reports
                  </span>
                ) : null}
              </div>
              <div className="cg-pending-feedback-message">
                Another user has previously submitted feedback on a similar query. Repair is currently{" "}
                <span className="cg-pending-feedback-status-pill">{notice.repair_lifecycle_status || "open"}</span>.
              </div>
              <div className="cg-pending-feedback-note">
                You can still submit additional feedback below if needed.
              </div>

              <details className="cg-pending-feedback-details">
                <summary>View Match Details</summary>
                <div className="cg-pending-feedback-details-content">
                  {notice.similarity_score != null && (
                    <div>
                      <span>Semantic match:</span>{" "}
                      <strong>{(notice.similarity_score * 100).toFixed(1)}%</strong>
                    </div>
                  )}
                  {Array.isArray(notice.feedback_categories) && notice.feedback_categories.length > 0 && (
                    <div>
                      <span>Reported categories:</span>{" "}
                      <strong>{notice.feedback_categories.join(", ")}</strong>
                    </div>
                  )}
                  {notice.feedback_submitted_at && (
                    <div>
                      <span>Submitted at:</span>{" "}
                      <span>{new Date(notice.feedback_submitted_at).toLocaleString()}</span>
                    </div>
                  )}
                  {notice.original_query_text && (
                    <div>
                      <span>Matched query:</span>{" "}
                      <code>{notice.original_query_text}</code>
                    </div>
                  )}
                </div>
              </details>
            </div>
          </div>
        </div>
      )}

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
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            <span>
              <b>Feedback recorded</b> — ID: <code>{feedbackId}</code>
              {lastSubmittedAt && ` at ${new Date(lastSubmittedAt).toLocaleTimeString()}`}
              {effectiveActorId && ` (Reviewer: ${effectiveActorId})`}
            </span>
            {submittedIssueInfo?.issueId && (
              <span style={{ fontSize: "11px", opacity: 0.9 }}>
                Attached to Issue: <code>{submittedIssueInfo.issueId}</code>
                {` (${(submittedIssueInfo.issueStatus || "reported").replace("_", " ")}`}
                {submittedIssueInfo.wasMatched ? " · linked to existing" : " · new issue"}
                {submittedIssueInfo.matchType ? ` · ${submittedIssueInfo.matchType}` : ""})
              </span>
            )}
          </div>
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
