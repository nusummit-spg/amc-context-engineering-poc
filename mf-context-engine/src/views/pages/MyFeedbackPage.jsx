import { useState, useEffect, useMemo, useCallback } from "react";
import {
  MessageSquare,
  Users,
  Wrench,
  CheckCircle2,
  Clock,
  RotateCcw,
  Search,
  RefreshCw,
  Eye,
  Filter,
  Tag,
  AlertCircle,
  HelpCircle,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  X,
  FileText,
  Zap,
} from "lucide-react";
import Button from "../../components/widgets/Button";
import TextInput from "../../components/widgets/TextInput";
import Selectbox from "../../components/widgets/Selectbox";
import Alert from "../../components/widgets/Alert";
import Divider from "../../components/widgets/Divider";
import { useAppState } from "../../state/AppState";
import { fetchMyFeedback } from "../../services/api";
import { FAILURE_TAXONOMY } from "../../constants/failureTaxonomy";

const STATUS_OPTIONS = [
  "All",
  "Reported",
  "Under_Review",
  "In_Repair",
  "Resolved",
  "Closed",
  "Reopened",
];

const TAXONOMY_MAP = Object.fromEntries(
  FAILURE_TAXONOMY.map((item) => [item.code.toUpperCase(), item])
);

export default function MyFeedbackPage() {
  const { setActiveTab, setActivePage } = useAppState();

  const [issues, setIssues] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspect Modal state
  const [inspectingIssue, setInspectingIssue] = useState(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const loadMyIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchMyFeedback({
        page: currentPage,
        pageSize: pageSize,
        q: searchQuery.trim() || undefined,
        status: selectedStatus !== "All" ? selectedStatus.toLowerCase() : undefined,
      });
      setIssues(resp?.items || []);
      setTotalCount(resp?.total || 0);
    } catch (err) {
      console.error("Failed to load personal feedback issues:", err);
      setError(err.message || "Failed to retrieve your reported feedback issues.");
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, searchQuery, selectedStatus]);

  useEffect(() => {
    loadMyIssues();
  }, [loadMyIssues]);

  // Reset to page 1 when filter or page size changes
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedStatus, searchQuery, pageSize]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // Derived Summary Metrics
  const metrics = useMemo(() => {
    const total = totalCount || issues.length;
    let openCount = 0;
    let inRepairCount = 0;
    let resolvedCount = 0;

    issues.forEach((iss) => {
      const st = (iss.status || "").toLowerCase();
      if (st === "in_repair") {
        inRepairCount += 1;
      } else if (st === "resolved" || st === "closed") {
        resolvedCount += 1;
      } else {
        openCount += 1;
      }
    });

    return { total, openCount, inRepairCount, resolvedCount };
  }, [issues, totalCount]);


  const handleGoToChat = () => {
    setActiveTab(0);
    setActivePage("app");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1280px", margin: "0 auto" }}>
      {/* Page Header */}
      <div>
        <h2 className="stHeader2" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <MessageSquare size={24} className="text-primary" />
          <span>My Reported Feedback</span>
        </h2>
        <div className="stCaption">
          Track the review, repair, and resolution progress of queries and answers you have flagged across your sessions.
        </div>
      </div>

      {/* KPI Stat Cards (Personal Scope) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "1rem",
        }}
      >
        <div className="stMetric">
          <div className="stMetric-value">{metrics.total}</div>
          <div className="stMetric-label">Total Reported by You</div>
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
          <div className="stMetric-label">In Repair</div>
        </div>
        <div className="stMetric">
          <div className="stMetric-value" style={{ color: "#16a34a" }}>
            {metrics.resolvedCount}
          </div>
          <div className="stMetric-label">Resolved / Closed</div>
        </div>
      </div>

      {/* Alert Messages */}
      {error && <Alert type="error">{error}</Alert>}

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
            placeholder="Search your reported queries, categories, or entities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div style={{ width: "180px" }}>
          <Selectbox
            options={STATUS_OPTIONS}
            value={selectedStatus}
            onChange={(val) => setSelectedStatus(val)}
          />
        </div>
        <button
          type="button"
          className="stButton kind-secondary"
          style={{ width: "auto", display: "inline-flex", alignItems: "center", gap: 6, padding: "0.5rem 0.9rem" }}
          onClick={loadMyIssues}
          disabled={loading}
          title="Refresh issue list"
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Table Container */}
      <div
        style={{
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
          background: "var(--color-surface)",
        }}
      >
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
            <thead>
              <tr style={{ background: "var(--color-navy-100)", borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600 }}>Query &amp; Entities</th>
                <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, width: "240px" }}>
                  Your Reported Categories
                </th>
                <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "160px" }}>
                  Community Impact
                </th>
                <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "120px" }}>
                  Status
                </th>
                <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, width: "150px" }}>
                  Repair Linkage
                </th>
                <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, width: "80px" }}>
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && issues.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: "2.5rem", textAlign: "center", color: "var(--color-ink-500)" }}>
                    Loading your feedback issues...
                  </td>
                </tr>
              ) : issues.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: "3rem 1.5rem", textAlign: "center" }}>
                    <div style={{ maxWidth: "420px", margin: "0 auto", display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}>
                      <div
                        style={{
                          width: 48,
                          height: 48,
                          borderRadius: "50%",
                          background: "#f1f5f9",
                          color: "#64748b",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <MessageSquare size={24} />
                      </div>
                      <div style={{ fontWeight: 600, fontSize: "14px", color: "var(--color-navy-900)" }}>
                        {issues.length === 0
                          ? "You have not reported any feedback issues yet"
                          : "No reported feedback matches your filters"}
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--color-ink-500)", lineHeight: 1.5 }}>
                        {issues.length === 0
                          ? "When you flag an inaccurate or incomplete answer in Chat using the feedback action, your issues and their repair progress will appear here."
                          : "Try adjusting your search keywords or resetting the status filter to see all your reported issues."}
                      </div>
                      {issues.length === 0 && (
                        <div style={{ marginTop: "0.5rem" }}>
                          <Button kind="primary" onClick={handleGoToChat}>
                            Go to Chat
                          </Button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                issues.map((issue) => {
                  const statusSlug = (issue.status || "reported").toLowerCase();

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
                        <div
                          style={{
                            display: "flex",
                            gap: "8px",
                            alignItems: "center",
                            flexWrap: "wrap",
                            fontSize: "11px",
                            color: "var(--color-ink-500)",
                          }}
                        >
                          <code>{issue.issue_id}</code>
                          <span>·</span>
                          <span>{issue.created_at ? new Date(issue.created_at).toLocaleDateString() : "Recent"}</span>
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

                      {/* Column 2: Your Reported Categories (§4, §7.2) */}
                      <td style={{ padding: "10px 12px", verticalAlign: "top" }}>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                          {issue.user_reported_categories && issue.user_reported_categories.length > 0 ? (
                            issue.user_reported_categories.map((code) => {
                              const upper = code.toUpperCase();
                              const info = TAXONOMY_MAP[upper];
                              const label = info ? info.label : upper;
                              const tooltip = info ? info.tooltip : "";
                              return (
                                <span
                                  key={code}
                                  title={tooltip}
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 3,
                                    padding: "2px 6px",
                                    borderRadius: "4px",
                                    background: "#eff6ff",
                                    color: "#1d4ed8",
                                    border: "1px solid #bfdbfe",
                                    fontSize: "11px",
                                    fontWeight: 500,
                                  }}
                                >
                                  <strong>{upper}</strong>
                                  <span>{label}</span>
                                </span>
                              );
                            })
                          ) : (
                            <span style={{ color: "var(--color-ink-400)", fontSize: "11px", fontStyle: "italic" }}>
                              General query feedback
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Column 3: Community Impact (Anonymized §4) */}
                      <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                        {issue.also_reported_by_count > 0 ? (
                          <div
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "3px 8px",
                              borderRadius: "12px",
                              background: "#ede9fe",
                              color: "#6d28d9",
                              fontWeight: 600,
                              fontSize: "11.5px",
                            }}
                            title={`Also reported by ${issue.also_reported_by_count} other user${issue.also_reported_by_count === 1 ? "" : "s"}`}
                          >
                            <Users size={12} />
                            <span>Also reported by {issue.also_reported_by_count} other{issue.also_reported_by_count === 1 ? "" : "s"}</span>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "2px 7px",
                              borderRadius: "10px",
                              background: "#f1f5f9",
                              color: "#475569",
                              fontSize: "11px",
                            }}
                            title="You are currently the sole reporter of this issue"
                          >
                            <span>Sole reporter</span>
                          </div>
                        )}
                      </td>

                      {/* Column 4: Status Badge */}
                      <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                        <span className={`cg-issue-awareness-status-pill cg-issue-status--${statusSlug}`}>
                          {statusSlug.replace("_", " ")}
                        </span>
                      </td>

                      {/* Column 5: Repair Linkage (Read-Only §4) */}
                      <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                        {issue.repair_task_id ? (
                          (() => {
                            const isResolved = issue.status === "resolved" || issue.status === "closed";
                            const isAuto =
                              issue.repair_task_id?.startsWith("task-auto-") ||
                              issue.resolution_notes?.toLowerCase().includes("auto-repair") ||
                              issue.resolution_notes?.toLowerCase().includes("hands-free");

                            return (
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
                                    isAuto ? <Zap size={10} style={{ color: "#16a34a" }} /> : <CheckCircle2 size={10} />
                                  ) : (
                                    <Wrench size={10} />
                                  )}
                                  <span>
                                    {isAuto
                                      ? "Auto-Repaired"
                                      : isResolved
                                      ? "Repaired"
                                      : "In Repair"}
                                  </span>
                                </span>
                                <span style={{ fontSize: "10px", color: isResolved ? "#166534" : "#1e40af", fontWeight: 500 }}>
                                  {isAuto
                                    ? "Fix applied automatically"
                                    : isResolved
                                    ? "Fix applied"
                                    : "Repair in progress"}
                                </span>
                              </div>
                            );
                          })()
                        ) : (
                          <span style={{ color: "var(--color-ink-400)", fontSize: "11px", fontStyle: "italic" }}>
                            Under triage analysis
                          </span>
                        )}
                      </td>

                      {/* Column 6: Inspect Details Button */}
                      <td style={{ padding: "10px 12px", textAlign: "center", verticalAlign: "middle" }}>
                        <button
                          type="button"
                          className="stButton kind-secondary"
                          style={{
                            padding: "4px 8px",
                            fontSize: "11px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                          }}
                          onClick={() => setInspectingIssue(issue)}
                          title="View your reported feedback details"
                        >
                          <Eye size={12} />
                          <span>View</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
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

      {/* Inspect Modal (Read-Only) */}
      {inspectingIssue && (
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
              width: "100%",
              maxWidth: "600px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
              maxHeight: "85vh",
              overflowY: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <div>
                <h3 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "var(--color-navy-900)" }}>
                  Feedback Issue Details
                </h3>
                <div style={{ fontSize: "11px", color: "var(--color-ink-500)", marginTop: 2 }}>
                  Issue ID: <code>{inspectingIssue.issue_id}</code>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInspectingIssue(null)}
                style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--color-ink-500)" }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", fontSize: "13px" }}>
              <div>
                <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                  Reported Query:
                </div>
                <div
                  style={{
                    background: "var(--color-navy-100)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    fontStyle: "italic",
                  }}
                >
                  "{inspectingIssue.canonical_query_text}"
                </div>
              </div>

              <div>
                <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                  Your Reported Categories:
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {inspectingIssue.user_reported_categories && inspectingIssue.user_reported_categories.length > 0 ? (
                    inspectingIssue.user_reported_categories.map((code) => {
                      const upper = code.toUpperCase();
                      const info = TAXONOMY_MAP[upper];
                      return (
                        <div
                          key={code}
                          style={{
                            padding: "4px 8px",
                            borderRadius: "4px",
                            background: "#eff6ff",
                            border: "1px solid #bfdbfe",
                            color: "#1d4ed8",
                            fontSize: "12px",
                          }}
                        >
                          <strong>{upper}</strong>: {info ? info.label : upper}
                          {info?.tooltip && (
                            <div style={{ fontSize: "10.5px", color: "#475569", marginTop: 2 }}>
                              {info.tooltip}
                            </div>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div style={{ color: "var(--color-ink-400)", fontStyle: "italic" }}>
                      No specific categories flagged.
                    </div>
                  )}
                </div>
              </div>

              {inspectingIssue.user_feedback_texts && inspectingIssue.user_feedback_texts.length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 4 }}>
                    Your Submitted Comments:
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {inspectingIssue.user_feedback_texts.map((comment, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "4px",
                          padding: "6px 10px",
                          fontSize: "12px",
                          color: "#334155",
                        }}
                      >
                        {comment}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 2 }}>
                    Lifecycle Status:
                  </div>
                  <span className={`cg-issue-awareness-status-pill cg-issue-status--${(inspectingIssue.status || "reported").toLowerCase()}`}>
                    {(inspectingIssue.status || "reported").replace("_", " ")}
                  </span>
                </div>
                <div>
                  <div style={{ fontWeight: 600, color: "var(--color-navy-900)", marginBottom: 2 }}>
                    Repair Status:
                  </div>
                  <div style={{ fontSize: "12px" }}>
                    {inspectingIssue.repair_task_id ? (
                      (() => {
                        const isResolved =
                          inspectingIssue.status === "resolved" || inspectingIssue.status === "closed";
                        const isAuto =
                          inspectingIssue.repair_task_id?.startsWith("task-auto-") ||
                          inspectingIssue.resolution_notes?.toLowerCase().includes("auto-repair") ||
                          inspectingIssue.resolution_notes?.toLowerCase().includes("hands-free");

                        if (isResolved) {
                          return (
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                color: "#15803d",
                                fontWeight: 600,
                                background: "#dcfce7",
                                padding: "2px 7px",
                                borderRadius: "4px",
                              }}
                            >
                              {isAuto ? <Zap size={11} /> : <CheckCircle2 size={11} />}
                              <span>{isAuto ? "Auto-Repaired (Fix Applied)" : "Repaired (Fix Applied)"}</span>
                            </span>
                          );
                        }
                        return (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              color: "#1e40af",
                              fontWeight: 600,
                              background: "#dbeafe",
                              padding: "2px 7px",
                              borderRadius: "4px",
                            }}
                          >
                            <Wrench size={11} />
                            <span>Repair in Progress</span>
                          </span>
                        );
                      })()
                    ) : (
                      <span style={{ color: "var(--color-ink-500)", fontStyle: "italic" }}>Under triage review</span>
                    )}
                  </div>
                </div>
              </div>

              {inspectingIssue.resolution_notes && (
                <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "6px", padding: "8px 12px" }}>
                  <div style={{ fontWeight: 600, color: "#166534", marginBottom: 2 }}>
                    Resolution Notes:
                  </div>
                  <div style={{ fontSize: "12px", color: "#15803d" }}>
                    {inspectingIssue.resolution_notes}
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.5rem" }}>
              <Button kind="secondary" onClick={() => setInspectingIssue(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
