import { useState, useEffect, useMemo, useCallback } from "react";
import {
  AlertCircle,
  Users,
  Wrench,
  CheckCircle2,
  Clock,
  RotateCcw,
  Search,
  RefreshCw,
  Eye,
  Filter,
  CheckSquare,
  FileText,
  Tag,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Zap,
  X,
} from "lucide-react";
import Button from "../../components/widgets/Button";
import TextInput from "../../components/widgets/TextInput";
import Selectbox from "../../components/widgets/Selectbox";
import Alert from "../../components/widgets/Alert";
import Divider from "../../components/widgets/Divider";
import { useAppState } from "../../state/AppState";
import {
  fetchFeedbackIssues,
  fetchFeedbackTelemetry,
  updateIssueStatus,
  initiateIssueRepair,
} from "../../services/api";

const STATUS_OPTIONS = [
  "All",
  "Reported",
  "Under_Review",
  "In_Repair",
  "Resolved",
  "Closed",
  "Reopened",
];

export default function AdminFeedbackIssuesTab() {
  const { activeUser } = useAppState();
  const currentActorId = activeUser?.username || "admin";

  const [issues, setIssues] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Filters & Server Search
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination (Phase 5)
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [cacheTelemetry, setCacheTelemetry] = useState(null);

  // Inspect Modal
  const [inspectingIssue, setInspectingIssue] = useState(null);

  // Resolution Modal
  const [resolvingIssue, setResolvingIssue] = useState(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [actionInProgress, setActionInProgress] = useState(false);

  const loadIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchFeedbackIssues({
        status: selectedStatus !== "All" ? selectedStatus.toLowerCase() : undefined,
        q: searchQuery.trim() || undefined,
        page: currentPage,
        pageSize: pageSize,
      });
      setIssues(resp?.items || []);
      setTotalCount(resp?.total || 0);

      try {
        const telem = await fetchFeedbackTelemetry();
        if (telem?.cache) setCacheTelemetry(telem.cache);
      } catch {
        // Non-blocking telemetry
      }
    } catch (err) {
      console.error("Failed to load feedback issues:", err);
      setError(err.message || "Failed to retrieve feedback issues.");
    } finally {
      setLoading(false);
    }
  }, [selectedStatus, searchQuery, currentPage, pageSize]);

  useEffect(() => {
    loadIssues();
  }, [loadIssues]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // Derived Summary Metrics
  const metrics = useMemo(() => {
    const total = totalCount || issues.length;
    let openCount = 0;
    let inRepairCount = 0;
    let resolvedCount = 0;
    let totalContributors = 0;

    issues.forEach((iss) => {
      totalContributors += iss.contributor_count || 1;
      if (iss.status === "in_repair") {
        inRepairCount += 1;
      } else if (iss.status === "resolved" || iss.status === "closed") {
        resolvedCount += 1;
      } else {
        openCount += 1;
      }
    });

    return { total, openCount, inRepairCount, resolvedCount, totalContributors };
  }, [issues, totalCount]);


  // Actions
  const handleInitiateRepair = async (issueId) => {
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await initiateIssueRepair(issueId, { actorId: currentActorId });
      setSuccessMsg(
        `Repair task '${res.repair_task_id}' ${res.reused ? "reused" : "created"} for issue '${issueId}'.`
      );
      await loadIssues();
    } catch (err) {
      setError(err.message || "Failed to initiate repair task.");
    } finally {
      setActionInProgress(false);
    }
  };

  const handleUpdateStatus = async (issueId, newStatus, notes = null) => {
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await updateIssueStatus(issueId, {
        status: newStatus,
        resolutionNotes: notes,
        actorId: currentActorId,
      });
      setSuccessMsg(`Issue '${issueId}' transitioned to '${newStatus}'.`);
      setResolvingIssue(null);
      setResolutionNotes("");
      await loadIssues();
    } catch (err) {
      setError(err.message || `Failed to transition issue to '${newStatus}'.`);
    } finally {
      setActionInProgress(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.2rem" }}>
      {/* Title & Description */}
      <div>
        <h2 className="stHeader2" style={{ marginBottom: "0.25rem" }}>
          Feedback &amp; Triage
        </h2>
        <div className="stCaption">
          Monitor aggregated feedback issues, inspect contributor impact, initiate Repair Engine tasks, and manage the issue lifecycle.
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "0.75rem",
        }}
      >
        <div className="stMetric">
          <div className="stMetric-value">{metrics.total}</div>
          <div className="stMetric-label">Total Reported Issues</div>
        </div>
        <div className="stMetric">
          <div className="stMetric-value" style={{ color: "#d97706" }}>
            {metrics.openCount}
          </div>
          <div className="stMetric-label">Pending Review</div>
        </div>
        <div className="stMetric">
          <div className="stMetric-value" style={{ color: "#2563eb" }}>
            {metrics.inRepairCount}
          </div>
          <div className="stMetric-label">In Repair (Linked)</div>
        </div>
        <div className="stMetric">
          <div className="stMetric-value" style={{ color: "#7c3aed" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Users size={20} />
              {metrics.totalContributors}
            </span>
          </div>
          <div className="stMetric-label">Contributors Impacted</div>
        </div>
        <div className="stMetric">
          <div className="stMetric-value" style={{ color: "#16a34a" }}>
            {metrics.resolvedCount}
          </div>
          <div className="stMetric-label">Resolved / Closed</div>
        </div>
      </div>

      {/* Messages */}
      {error && <Alert type="error">{error}</Alert>}
      {successMsg && <Alert type="success">{successMsg}</Alert>}

      {/* Filters Bar */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          alignItems: "center",
          flexWrap: "wrap",
          padding: "0.75rem 1rem",
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <div style={{ flex: 1, minWidth: "240px" }}>
          <TextInput
            placeholder="Search query text, entities, issue ID..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
          />
        </div>
        <div style={{ width: "180px" }}>
          <Selectbox
            options={STATUS_OPTIONS}
            value={selectedStatus}
            onChange={(val) => {
              setSelectedStatus(val);
              setCurrentPage(1);
            }}
          />
        </div>
        <button
          type="button"
          className="stButton kind-secondary"
          style={{ width: "auto", display: "inline-flex", alignItems: "center", gap: 6, padding: "0.5rem 0.9rem" }}
          onClick={loadIssues}
          disabled={loading}
          title="Refresh issue list"
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          <span>Refresh</span>
        </button>
        {cacheTelemetry && (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              fontSize: "11px",
              padding: "4px 8px",
              borderRadius: "12px",
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              color: "#166534",
            }}
            title={`Hit Rate: ${cacheTelemetry.hit_rate_pct}% (${cacheTelemetry.hits} hits / ${cacheTelemetry.total_requests} reqs), Drift: ${cacheTelemetry.last_drift_size || 0}`}
          >
            <Zap size={11} style={{ color: "#16a34a" }} />
            <span>Cache: {cacheTelemetry.hit_rate_pct}%</span>
          </div>
        )}
      </div>


      {/* Issues Table */}
      <div
        style={{
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
          background: "var(--color-surface)",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
          <thead>
            <tr style={{ background: "var(--color-navy-100)", borderBottom: "1px solid var(--color-border)" }}>
              <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600 }}>Query &amp; Entities</th>
              <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "130px" }}>
                Contributors
              </th>
              <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "120px" }}>
                Status
              </th>
              <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, width: "160px" }}>
                Repair Linkage
              </th>
              <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "210px" }}>
                Triage Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && issues.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: "2rem", textAlign: "center", color: "var(--color-ink-500)" }}>
                  Loading feedback issues...
                </td>
              </tr>
            ) : issues.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: "2.5rem", textAlign: "center", color: "var(--color-ink-500)" }}>
                  No feedback issues found matching current criteria.
                </td>
              </tr>
            ) : (
              issues.map((issue) => {

                const statusSlug = (issue.status || "reported").toLowerCase();
                const isResolved = statusSlug === "resolved" || statusSlug === "closed";
                const isAutoRepaired =
                  Boolean(issue.repair_task_id?.startsWith("task-auto-")) ||
                  Boolean(issue.resolution_notes?.toLowerCase().includes("auto-repair")) ||
                  Boolean(issue.resolution_notes?.toLowerCase().includes("hands-free"));
                return (
                  <tr
                    key={issue.issue_id}
                    style={{
                      borderBottom: "1px solid var(--color-border)",
                      transition: "background 0.15s ease",
                    }}
                  >
                    {/* Column 1: Query & Details */}
                    <td style={{ padding: "10px 12px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                        {issue.canonical_query_text}
                      </div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap", fontSize: "11px", color: "var(--color-ink-500)" }}>
                        <code>{issue.issue_id}</code>
                        <span>·</span>
                        <span>{new Date(issue.created_at).toLocaleDateString()}</span>
                        {issue.primary_entities && issue.primary_entities.length > 0 && (
                          <>
                            <span>·</span>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: "#1d4ed8" }}>
                              <Tag size={10} />
                              {issue.primary_entities.join(", ")}
                            </span>
                          </>
                        )}
                        {issue.resolution_notes && (
                          <div style={{ width: "100%", fontStyle: "italic", color: "#15803d", marginTop: 2 }}>
                            Resolution: {issue.resolution_notes}
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Column 2: Contributor Count & Linked Feedbacks (Phase 4 Visibility) */}
                    <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          padding: "3px 8px",
                          borderRadius: "12px",
                          background: issue.contributor_count > 1 ? "#ede9fe" : "#f1f5f9",
                          color: issue.contributor_count > 1 ? "#6d28d9" : "#475569",
                          fontWeight: 700,
                          fontSize: "12px",
                        }}
                        title={`${issue.contributor_count} unique users have submitted feedback on this issue`}
                      >
                        <Users size={13} />
                        <span>{issue.contributor_count}</span>
                      </div>
                      <div style={{ fontSize: "10.5px", color: "var(--color-ink-500)", marginTop: 3 }}>
                        {issue.linked_feedback_count || 1} feedback{issue.linked_feedback_count === 1 ? "" : "s"}
                      </div>
                    </td>

                    {/* Column 3: Status Badge */}
                    <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                      <span className={`cg-issue-awareness-status-pill cg-issue-status--${statusSlug}`}>
                        {statusSlug.replace("_", " ")}
                      </span>
                    </td>

                    {/* Column 4: Repair Linkage */}
                    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                      {issue.repair_task_id ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              fontSize: "11px",
                              fontWeight: 600,
                              color: isResolved ? "#15803d" : "#1e40af",
                              background: isResolved ? "#dcfce7" : "#dbeafe",
                              padding: "2px 8px",
                              borderRadius: "4px",
                              width: "fit-content",
                            }}
                            title={`Repair Task: ${issue.repair_task_id}`}
                          >
                            {isResolved ? (
                              isAutoRepaired ? (
                                <Zap size={11} style={{ color: "#16a34a" }} />
                              ) : (
                                <CheckCircle2 size={11} />
                              )
                            ) : (
                              <Wrench size={11} />
                            )}
                            <span>
                              {isAutoRepaired
                                ? "Auto-Repaired"
                                : isResolved
                                ? "Repaired"
                                : "In Repair"}
                            </span>
                          </span>
                          <span style={{ fontSize: "10px", color: isResolved ? "#166534" : "#64748b" }}>
                            {isAutoRepaired
                              ? "Hands-free automated fix"
                              : isResolved
                              ? "Fix applied"
                              : "Task active"}
                          </span>
                        </div>
                      ) : (
                        <span style={{ fontSize: "11px", color: "var(--color-ink-500)" }}>None</span>
                      )}
                    </td>

                    {/* Column 5: Triage Actions */}
                    <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                      <div style={{ display: "flex", gap: "6px", justifyContent: "center", flexWrap: "wrap" }}>
                        {isResolved ? (
                          <>
                            <button
                              type="button"
                              className="stButton kind-secondary"
                              style={{
                                padding: "4px 8px",
                                fontSize: "11px",
                                width: "auto",
                                background: "#fef2f2",
                                color: "#b91c1c",
                                borderColor: "#fecaca",
                              }}
                              onClick={() => handleUpdateStatus(issue.issue_id, "reopened")}
                              disabled={actionInProgress}
                              title="Reopen issue and clear repair task"
                            >
                              <RotateCcw size={11} style={{ marginRight: 3, verticalAlign: "middle" }} />
                              Reopen
                            </button>

                            <button
                              type="button"
                              className="stButton kind-secondary"
                              style={{
                                padding: "4px 8px",
                                fontSize: "11px",
                                width: "auto",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                              }}
                              onClick={() => setInspectingIssue(issue)}
                              title="View issue details"
                            >
                              <Eye size={12} />
                              <span>View</span>
                            </button>
                          </>
                        ) : (
                          <>
                            {issue.status !== "in_repair" && (
                              <button
                                type="button"
                                className="stButton kind-secondary"
                                style={{
                                  padding: "4px 8px",
                                  fontSize: "11px",
                                  width: "auto",
                                  background: "#eff6ff",
                                  color: "#1d4ed8",
                                  borderColor: "#bfdbfe",
                                }}
                                onClick={() => handleInitiateRepair(issue.issue_id)}
                                disabled={actionInProgress}
                                title="Initiate or link Repair Engine task"
                              >
                                <Wrench size={11} style={{ marginRight: 3, verticalAlign: "middle" }} />
                                Repair
                              </button>
                            )}

                            {issue.status === "reported" && (
                              <button
                                type="button"
                                className="stButton kind-secondary"
                                style={{ padding: "4px 8px", fontSize: "11px", width: "auto" }}
                                onClick={() => handleUpdateStatus(issue.issue_id, "under_review")}
                                disabled={actionInProgress}
                                title="Acknowledge issue"
                              >
                                Review
                              </button>
                            )}

                            <button
                              type="button"
                              className="stButton kind-secondary"
                              style={{
                                padding: "4px 8px",
                                fontSize: "11px",
                                width: "auto",
                                background: "#f0fdf4",
                                color: "#15803d",
                                borderColor: "#bbf7d0",
                              }}
                              onClick={() => setResolvingIssue(issue)}
                              disabled={actionInProgress}
                              title="Resolve issue"
                            >
                              <CheckCircle2 size={11} style={{ marginRight: 3, verticalAlign: "middle" }} />
                              Resolve
                            </button>

                            <button
                              type="button"
                              className="stButton kind-secondary"
                              style={{
                                padding: "4px 8px",
                                fontSize: "11px",
                                width: "auto",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                              }}
                              onClick={() => setInspectingIssue(issue)}
                              title="View issue details"
                            >
                              <Eye size={12} />
                              <span>View</span>
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Pagination Controls (Phase 5 Server-Side Pagination) */}
        {totalCount > 0 && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "0.75rem 1rem",
              borderTop: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              fontSize: "12px",
              color: "var(--color-ink-600)",
            }}
          >
            <div>
              Showing {Math.min((currentPage - 1) * pageSize + 1, totalCount)} to{" "}
              {Math.min(currentPage * pageSize, totalCount)} of {totalCount} issues
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <button
                type="button"
                className="stButton kind-secondary"
                style={{ padding: "4px 8px", display: "inline-flex", alignItems: "center", gap: 4 }}
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft size={14} />
                <span>Prev</span>
              </button>
              <span>
                Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
              </span>
              <button
                type="button"
                className="stButton kind-secondary"
                style={{ padding: "4px 8px", display: "inline-flex", alignItems: "center", gap: 4 }}
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              >
                <span>Next</span>
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>


      {/* Inspect Issue Modal (User-Friendly Design) */}
      {inspectingIssue && (() => {
        const isAutoRep =
          inspectingIssue.repair_task_id?.startsWith("task-auto-") ||
          inspectingIssue.resolution_notes?.toLowerCase().includes("auto-repair") ||
          inspectingIssue.resolution_notes?.toLowerCase().includes("hands-free");
        const isRes =
          inspectingIssue.status === "resolved" || inspectingIssue.status === "closed";
        const statusSlug = (inspectingIssue.status || "reported").toLowerCase();

        return (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(15, 23, 42, 0.45)",
              backdropFilter: "blur(2px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: "1rem",
            }}
            onClick={() => setInspectingIssue(null)}
          >
            <div
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                maxWidth: "620px",
                width: "100%",
                maxHeight: "85vh",
                overflowY: "auto",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header with Issue ID clearly preserved and visible */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  marginBottom: "1.2rem",
                  borderBottom: "1px solid var(--color-border)",
                  paddingBottom: "0.8rem",
                }}
              >
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--color-navy-900)" }}>
                    Feedback Issue Details
                  </h3>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                    <span style={{ fontSize: "12px", color: "var(--color-ink-500)" }}>Issue ID:</span>
                    <code
                      style={{
                        fontSize: "12px",
                        background: "#f1f5f9",
                        padding: "2px 8px",
                        borderRadius: "4px",
                        color: "var(--color-navy-900)",
                        fontWeight: 600,
                      }}
                    >
                      {inspectingIssue.issue_id}
                    </code>
                  </div>
                </div>
                <button
                  type="button"
                  className="stButton kind-secondary"
                  style={{ width: "auto", padding: "4px 8px", fontSize: "12px", display: "inline-flex", alignItems: "center" }}
                  onClick={() => setInspectingIssue(null)}
                >
                  <X size={14} />
                </button>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "1rem", fontSize: "13px" }}>
                {/* Query Block */}
                <div>
                  <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                    Reported Query:
                  </div>
                  <div
                    style={{
                      padding: "10px 14px",
                      background: "var(--color-navy-100)",
                      borderLeft: "3px solid #3b82f6",
                      borderRadius: "6px",
                      color: "var(--color-navy-900)",
                      fontSize: "13px",
                      lineHeight: 1.5,
                    }}
                  >
                    "{inspectingIssue.canonical_query_text}"
                  </div>
                </div>

                {/* User-friendly Status & Overview Grid */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                    gap: "0.75rem",
                    background: "#f8fafc",
                    padding: "0.85rem",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "11px", color: "var(--color-ink-500)", marginBottom: 3 }}>
                      Lifecycle Status
                    </div>
                    <span className={`cg-issue-awareness-status-pill cg-issue-status--${statusSlug}`}>
                      {statusSlug.replace("_", " ")}
                    </span>
                  </div>

                  <div>
                    <div style={{ fontSize: "11px", color: "var(--color-ink-500)", marginBottom: 3 }}>
                      Repair Status
                    </div>
                    {isAutoRep ? (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#15803d",
                          background: "#dcfce7",
                          padding: "2px 7px",
                          borderRadius: "4px",
                        }}
                      >
                        <Zap size={11} /> Auto-Repaired
                      </span>
                    ) : isRes ? (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#15803d",
                          background: "#dcfce7",
                          padding: "2px 7px",
                          borderRadius: "4px",
                        }}
                      >
                        <CheckCircle2 size={11} /> Resolved
                      </span>
                    ) : inspectingIssue.repair_task_id ? (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#1e40af",
                          background: "#dbeafe",
                          padding: "2px 7px",
                          borderRadius: "4px",
                        }}
                      >
                        <Wrench size={11} /> In Repair
                      </span>
                    ) : (
                      <span style={{ fontSize: "12px", color: "var(--color-ink-500)", fontStyle: "italic" }}>
                        Pending review
                      </span>
                    )}
                  </div>

                  <div>
                    <div style={{ fontSize: "11px", color: "var(--color-ink-500)", marginBottom: 3 }}>
                      Community Impact
                    </div>
                    <div style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "#6d28d9", fontWeight: 700, fontSize: "12px" }}>
                      <Users size={13} />
                      <span>
                        {inspectingIssue.contributor_count} {inspectingIssue.contributor_count === 1 ? "user" : "users"}
                      </span>
                    </div>
                    <div style={{ fontSize: "10.5px", color: "var(--color-ink-500)", marginTop: 1 }}>
                      {inspectingIssue.linked_feedback_count || inspectingIssue.linked_feedback_ids?.length || 1} report{inspectingIssue.linked_feedback_count === 1 ? "" : "s"}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "11px", color: "var(--color-ink-500)", marginBottom: 3 }}>
                      Reported Date
                    </div>
                    <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-navy-900)" }}>
                      {inspectingIssue.created_at
                        ? new Date(inspectingIssue.created_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })
                        : "Recent"}
                    </div>
                  </div>
                </div>

                {/* Primary Entities & Topics */}
                {inspectingIssue.primary_entities && inspectingIssue.primary_entities.length > 0 && (
                  <div>
                    <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                      Primary Topics &amp; Entities:
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {inspectingIssue.primary_entities.map((ent, idx) => (
                        <span
                          key={idx}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                            padding: "3px 8px",
                            borderRadius: "4px",
                            background: "#eff6ff",
                            color: "#1d4ed8",
                            border: "1px solid #bfdbfe",
                            fontSize: "11.5px",
                            fontWeight: 500,
                          }}
                        >
                          <Tag size={11} />
                          {ent}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Taxonomy Paths (Human-Friendly Breadcrumbs) */}
                {inspectingIssue.taxonomy_paths && inspectingIssue.taxonomy_paths.length > 0 && (
                  <div>
                    <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                      Category Classification:
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {inspectingIssue.taxonomy_paths.map((p, idx) => (
                        <span
                          key={idx}
                          style={{
                            padding: "3px 8px",
                            borderRadius: "4px",
                            background: "#f1f5f9",
                            border: "1px solid #e2e8f0",
                            color: "#334155",
                            fontSize: "11.5px",
                          }}
                        >
                          {p
                            .split("/")
                            .map((s) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))
                            .join(" › ")}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Resolution & Auto-Repair Notes */}
                {inspectingIssue.resolution_notes && (
                  <div
                    style={{
                      padding: "10px 14px",
                      background: "#f0fdf4",
                      border: "1px solid #bbf7d0",
                      borderRadius: "6px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, color: "#166534", marginBottom: 3 }}>
                      {isAutoRep ? <Zap size={14} style={{ color: "#16a34a" }} /> : <CheckCircle2 size={14} />}
                      <span>{isAutoRep ? "Automated Repair Summary" : "Resolution Summary"}</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "#15803d", lineHeight: 1.5 }}>
                      {inspectingIssue.resolution_notes}
                    </div>
                  </div>
                )}

                {/* Feedback aggregation summary instead of raw UUID dump */}
                <div
                  style={{
                    padding: "10px 12px",
                    background: "#fafafa",
                    border: "1px solid #f0f0f0",
                    borderRadius: "6px",
                    fontSize: "12px",
                    color: "var(--color-ink-600)",
                  }}
                >
                  <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 2 }}>
                    Aggregation &amp; Cluster Summary
                  </div>
                  <div>
                    Aggregated from {inspectingIssue.contributor_count || 1} contributor{inspectingIssue.contributor_count === 1 ? "" : "s"} across {inspectingIssue.linked_feedback_count || inspectingIssue.linked_feedback_ids?.length || 1} chat interaction{inspectingIssue.linked_feedback_count === 1 ? "" : "s"}.
                    Semantic intent and entity matching confirmed these belong to the same canonical question.
                  </div>
                </div>
              </div>

              {/* Modal Actions */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: "0.5rem",
                  marginTop: "1.2rem",
                  paddingTop: "0.8rem",
                  borderTop: "1px solid var(--color-border)",
                }}
              >
                {isRes && (
                  <button
                    type="button"
                    className="stButton kind-secondary"
                    style={{
                      padding: "5px 12px",
                      fontSize: "12px",
                      width: "auto",
                      background: "#fef2f2",
                      color: "#b91c1c",
                      borderColor: "#fecaca",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    onClick={() => {
                      const id = inspectingIssue.issue_id;
                      setInspectingIssue(null);
                      handleUpdateStatus(id, "reopened");
                    }}
                    disabled={actionInProgress}
                  >
                    <RotateCcw size={12} />
                    <span>Reopen Issue</span>
                  </button>
                )}
                <button
                  type="button"
                  className="stButton kind-secondary"
                  style={{ padding: "5px 12px", fontSize: "12px", width: "auto" }}
                  onClick={() => setInspectingIssue(null)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Resolve Issue Modal */}
      {resolvingIssue && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "1rem",
          }}
          onClick={() => setResolvingIssue(null)}
        >
          <div
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-lg)",
              padding: "1.5rem",
              maxWidth: "500px",
              width: "100%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "15px", fontWeight: 700 }}>
              Resolve Feedback Issue
            </h4>
            <div className="stCaption" style={{ marginBottom: "1rem" }}>
              Resolving <code>{resolvingIssue.issue_id}</code> will preserve its repair task for historical audit and remove it from active pending matching.
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label style={{ fontSize: "12px", fontWeight: 600, display: "block", marginBottom: 4 }}>
                Resolution Notes / Fix Details
              </label>
              <textarea
                style={{
                  width: "100%",
                  minHeight: "80px",
                  padding: "8px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border)",
                  fontSize: "12px",
                  fontFamily: "inherit",
                }}
                placeholder="e.g., Knowledge graph factsheet updated to reflect new circular..."
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
              <button
                type="button"
                className="stButton kind-secondary"
                style={{ width: "auto" }}
                onClick={() => setResolvingIssue(null)}
                disabled={actionInProgress}
              >
                Cancel
              </button>
              <button
                type="button"
                className="stButton kind-primary"
                style={{ width: "auto", background: "#16a34a", borderColor: "#16a34a" }}
                onClick={() => handleUpdateStatus(resolvingIssue.issue_id, "resolved", resolutionNotes)}
                disabled={actionInProgress}
              >
                Confirm Resolution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
