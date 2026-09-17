import { useState, useEffect, useMemo } from "react";
import {
  ClipboardCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Search,
  RefreshCw,
  Eye,
  CheckCheck,
  ShieldCheck,
  Layers,
  ArrowRight,
  Info,
} from "lucide-react";
import Button from "../../components/widgets/Button";
import TextInput from "../../components/widgets/TextInput";
import Selectbox from "../../components/widgets/Selectbox";
import Alert from "../../components/widgets/Alert";
import {
  fetchPendingCorrections,
  approveCorrection,
  rejectCorrection,
  batchApproveCorrections,
} from "../../services/api";

export default function GovernancePage() {
  const [corrections, setCorrections] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState("All");
  const [selectedIds, setSelectedIds] = useState(new Set());

  const [activeEvidenceModal, setActiveEvidenceModal] = useState(null);
  const [rejectModalPatch, setRejectModalPatch] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  const [actionInProgress, setActionInProgress] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPendingCorrections();
      setCorrections(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed loading pending corrections:", err);
      setError(err.message || "Failed to load governance review queue.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = useMemo(() => {
    return corrections.filter((c) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesQuery =
        !q ||
        c.entity_name?.toLowerCase().includes(q) ||
        c.entity_id?.toLowerCase().includes(q) ||
        c.attribute?.toLowerCase().includes(q) ||
        c.proposed_value?.toLowerCase().includes(q);

      const matchesRisk =
        riskFilter === "All" ||
        (c.risk_level && c.risk_level.toUpperCase() === riskFilter.toUpperCase());

      return matchesQuery && matchesRisk;
    });
  }, [corrections, searchQuery, riskFilter]);

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedIds(new Set(filtered.map((c) => c.patch_id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const toggleSelectOne = (patchId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(patchId)) next.delete(patchId);
      else next.add(patchId);
      return next;
    });
  };

  const handleApprove = async (patchId) => {
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await approveCorrection(patchId, "Approved via Governance Review UI");
      setSuccessMsg(`Patch ${patchId} successfully approved and promoted to canonical graph.`);
      setCorrections((prev) => prev.filter((c) => c.patch_id !== patchId));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(patchId);
        return next;
      });
    } catch (err) {
      setError(`Approval failed: ${err.message}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleConfirmReject = async () => {
    if (!rejectModalPatch) return;
    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    const pid = rejectModalPatch.patch_id;
    try {
      await rejectCorrection(pid, rejectReason || "Rejected by compliance officer");
      setSuccessMsg(`Patch ${pid} rejected and removed from shadow graph.`);
      setCorrections((prev) => prev.filter((c) => c.patch_id !== pid));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(pid);
        return next;
      });
      setRejectModalPatch(null);
      setRejectReason("");
    } catch (err) {
      setError(`Rejection failed: ${err.message}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleBatchAction = async (action) => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    setActionInProgress(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const result = await batchApproveCorrections(ids, action, `Batch ${action} via UI`);
      const count = result.succeeded_count ?? ids.length;
      setSuccessMsg(`Successfully ${action}d ${count} correction patches.`);
      setCorrections((prev) => prev.filter((c) => !ids.includes(c.patch_id)));
      setSelectedIds(new Set());
    } catch (err) {
      setError(`Batch ${action} failed: ${err.message}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const highRiskCount = corrections.filter((c) => c.risk_level === "HIGH").length;

  return (
    <div style={{ padding: "8px 0" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <h2 className="stHeader2" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ClipboardCheck className="text-primary" size={26} />
            Governance Review Queue
          </h2>
          <div className="stCaption">
            Weekly batch approval interface for compliance officers. Review pending feedback corrections before
            promoting them to the permanent canonical Neo4j knowledge graph.
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadData}
          disabled={loading || actionInProgress}
          icon={RefreshCw}
        >
          {loading ? "Refreshing..." : "Refresh Queue"}
        </Button>
      </div>

      {/* Summary KPI Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div className="card" style={{ padding: 14, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ padding: 10, borderRadius: 8, background: "rgba(59, 130, 246, 0.1)", color: "#2563eb" }}>
            <Layers size={22} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#64748b" }}>Pending Corrections</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{corrections.length}</div>
          </div>
        </div>

        <div className="card" style={{ padding: 14, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ padding: 10, borderRadius: 8, background: "rgba(239, 68, 68, 0.1)", color: "#dc2626" }}>
            <AlertTriangle size={22} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#64748b" }}>High Regulatory Risk</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: highRiskCount > 0 ? "#dc2626" : "inherit" }}>
              {highRiskCount}
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: 14, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ padding: 10, borderRadius: 8, background: "rgba(16, 185, 129, 0.1)", color: "#059669" }}>
            <ShieldCheck size={22} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#64748b" }}>Default Retention</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>7 Days TTL</div>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 14 }}>
          <Alert type="error" title="Governance Notice" message={error} />
        </div>
      )}
      {successMsg && (
        <div style={{ marginBottom: 14 }}>
          <Alert type="success" title="Success" message={successMsg} />
        </div>
      )}

      {/* Filter Toolbar */}
      <div
        className="card"
        style={{
          padding: 14,
          marginBottom: 16,
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: 10, flex: 1, minWidth: 260 }}>
          <div style={{ flex: 1 }}>
            <TextInput
              placeholder="Search by fund, ISIN, attribute or value..."
              value={searchQuery}
              onChange={setSearchQuery}
              icon={Search}
            />
          </div>
          <div style={{ width: 140 }}>
            <Selectbox
              options={["All", "LOW", "MEDIUM", "HIGH"]}
              value={riskFilter}
              onChange={setRiskFilter}
            />
          </div>
        </div>

        {/* Batch Actions */}
        {selectedIds.size > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, color: "#64748b" }}>
              {selectedIds.size} selected
            </span>
            <Button
              variant="primary"
              size="sm"
              icon={CheckCheck}
              disabled={actionInProgress}
              onClick={() => handleBatchAction("approve")}
            >
              Approve Selected
            </Button>
            <Button
              variant="outline"
              size="sm"
              icon={XCircle}
              disabled={actionInProgress}
              onClick={() => handleBatchAction("reject")}
            >
              Reject Selected
            </Button>
          </div>
        )}
      </div>

      {/* Corrections List Table */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "rgba(0,0,0,0.02)", borderBottom: "1px solid rgba(0,0,0,0.08)" }}>
                <th style={{ padding: "12px 14px", width: 40 }}>
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selectedIds.size === filtered.length}
                    onChange={handleSelectAll}
                    disabled={filtered.length === 0}
                  />
                </th>
                <th style={{ padding: "12px 14px" }}>Entity / ISIN</th>
                <th style={{ padding: "12px 14px" }}>Attribute</th>
                <th style={{ padding: "12px 14px" }}>Current Canonical</th>
                <th style={{ padding: "12px 14px" }}>Proposed Value</th>
                <th style={{ padding: "12px 14px" }}>Confidence</th>
                <th style={{ padding: "12px 14px" }}>Risk</th>
                <th style={{ padding: "12px 14px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: 40, textAlign: "center", color: "#64748b" }}>
                    {loading ? "Loading pending corrections..." : "No pending corrections in the governance queue."}
                  </td>
                </tr>
              ) : (
                filtered.map((c) => {
                  const isChecked = selectedIds.has(c.patch_id);
                  const confPct = Math.round((c.confidence || 0) * 100);
                  const isHighRisk = c.risk_level === "HIGH";

                  return (
                    <tr
                      key={c.patch_id}
                      style={{
                        borderBottom: "1px solid rgba(0,0,0,0.05)",
                        background: isChecked ? "rgba(59, 130, 246, 0.04)" : "transparent",
                      }}
                    >
                      <td style={{ padding: "12px 14px" }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelectOne(c.patch_id)}
                        />
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ fontWeight: 600, color: "#1e293b" }}>{c.entity_name}</div>
                        <div style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace" }}>{c.entity_id}</div>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 4,
                            background: "rgba(0,0,0,0.06)",
                            fontWeight: 600,
                            fontSize: 12,
                          }}
                        >
                          {c.attribute}
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", color: "#64748b" }}>
                        {c.current_value || "—"}
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: "#2563eb" }}>
                          <ArrowRight size={14} color="#64748b" />
                          {c.proposed_value}
                        </div>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 12,
                            fontSize: 11,
                            fontWeight: 600,
                            background: confPct >= 85 ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.12)",
                            color: confPct >= 85 ? "#059669" : "#d97706",
                          }}
                        >
                          {confPct}%
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: isHighRisk
                              ? "rgba(239, 68, 68, 0.15)"
                              : c.risk_level === "MEDIUM"
                              ? "rgba(245, 158, 11, 0.15)"
                              : "rgba(16, 185, 129, 0.15)",
                            color: isHighRisk ? "#dc2626" : c.risk_level === "MEDIUM" ? "#b45309" : "#059669",
                          }}
                        >
                          {c.risk_level}
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                          <button
                            type="button"
                            onClick={() => handleApprove(c.patch_id)}
                            disabled={actionInProgress}
                            title="Approve and promote to permanent knowledge graph"
                            style={{
                              border: "none",
                              background: "#10b981",
                              color: "white",
                              borderRadius: 4,
                              padding: "5px 9px",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              fontSize: 12,
                              fontWeight: 600,
                            }}
                          >
                            <CheckCircle2 size={13} />
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setRejectModalPatch(c);
                              setRejectReason("");
                            }}
                            disabled={actionInProgress}
                            title="Reject correction"
                            style={{
                              border: "1px solid rgba(239, 68, 68, 0.3)",
                              background: "rgba(239, 68, 68, 0.08)",
                              color: "#dc2626",
                              borderRadius: 4,
                              padding: "4px 8px",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              fontSize: 12,
                            }}
                          >
                            <XCircle size={13} />
                            Reject
                          </button>
                          <button
                            type="button"
                            onClick={() => setActiveEvidenceModal(c)}
                            title="Inspect supporting evidence and provenance"
                            style={{
                              border: "1px solid rgba(0,0,0,0.1)",
                              background: "transparent",
                              color: "#475569",
                              borderRadius: 4,
                              padding: "4px 8px",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              fontSize: 12,
                            }}
                          >
                            <Eye size={13} />
                            Details
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Inspection Modal */}
      {activeEvidenceModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div
            className="card"
            style={{
              width: 580,
              maxHeight: "85vh",
              overflowY: "auto",
              padding: 24,
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8, fontSize: 18 }}>
                <Info size={20} color="#2563eb" />
                Correction Evidence &amp; Provenance
              </h3>
              <button
                type="button"
                onClick={() => setActiveEvidenceModal(null)}
                style={{ border: "none", background: "none", cursor: "pointer", fontSize: 18, color: "#64748b" }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Fund / Entity</div>
                <div style={{ fontWeight: 600 }}>{activeEvidenceModal.entity_name}</div>
                <div style={{ fontSize: 11, fontFamily: "monospace", color: "#64748b" }}>
                  {activeEvidenceModal.entity_id}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Attribute</div>
                <div style={{ fontWeight: 600 }}>{activeEvidenceModal.attribute}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Current Value in Graph</div>
                <div style={{ fontWeight: 600, color: "#64748b" }}>{activeEvidenceModal.current_value}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Proposed Value</div>
                <div style={{ fontWeight: 700, color: "#2563eb" }}>{activeEvidenceModal.proposed_value}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Confidence Score</div>
                <div style={{ fontWeight: 600 }}>
                  {Math.round((activeEvidenceModal.confidence || 0) * 100)}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>Risk Evaluation</div>
                <div style={{ fontWeight: 700, color: activeEvidenceModal.risk_level === "HIGH" ? "#dc2626" : "#059669" }}>
                  {activeEvidenceModal.risk_level}
                </div>
              </div>
            </div>

            <div style={{ borderTop: "1px solid rgba(0,0,0,0.08)", paddingTop: 14, marginBottom: 16 }}>
              <h4 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "0 0 8px 0" }}>
                Supporting Feedback Evidence
              </h4>
              {activeEvidenceModal.supporting_evidence && activeEvidenceModal.supporting_evidence.length > 0 ? (
                activeEvidenceModal.supporting_evidence.map((ev, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: "rgba(0,0,0,0.03)",
                      padding: 10,
                      borderRadius: 6,
                      fontSize: 12,
                      marginBottom: 6,
                    }}
                  >
                    <div><strong>Source:</strong> {ev.source || "User Feedback"}</div>
                    <div><strong>Feedback ID:</strong> {ev.feedback_id || "N/A"}</div>
                    <div><strong>Reviewer Role:</strong> {ev.actor_id || "N/A"}</div>
                    <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>Recorded: {ev.recorded_at}</div>
                  </div>
                ))
              ) : (
                <div style={{ fontSize: 12, color: "#64748b" }}>Direct system telemetry or manual patch.</div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <Button variant="outline" size="sm" onClick={() => setActiveEvidenceModal(null)}>
                Close
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={CheckCircle2}
                disabled={actionInProgress}
                onClick={() => {
                  handleApprove(activeEvidenceModal.patch_id);
                  setActiveEvidenceModal(null);
                }}
              >
                Approve Patch
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Reason Modal */}
      {rejectModalPatch && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div className="card" style={{ width: 460, padding: 22 }}>
            <h3 style={{ margin: "0 0 10px 0", fontSize: 16, color: "#dc2626", display: "flex", alignItems: "center", gap: 8 }}>
              <XCircle size={18} />
              Reject Correction Patch
            </h3>
            <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 12px 0" }}>
              Are you sure you want to reject the proposed change for <strong>{rejectModalPatch.entity_name}</strong> (
              {rejectModalPatch.attribute})? The patch will be permanently purged from the shadow graph.
            </p>
            <div style={{ marginBottom: 16 }}>
              <TextInput
                label="Rejection Reason"
                placeholder="e.g. Canonical factsheet verified; user claim is inaccurate"
                value={rejectReason}
                onChange={setRejectReason}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <Button variant="outline" size="sm" onClick={() => setRejectModalPatch(null)}>
                Cancel
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={actionInProgress}
                onClick={handleConfirmReject}
                style={{ borderColor: "#dc2626", color: "#dc2626" }}
              >
                Confirm Rejection
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
