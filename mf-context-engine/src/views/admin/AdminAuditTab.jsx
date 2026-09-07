import { useState, useEffect, useCallback } from "react";
import {
  Database,
  RefreshCw,
  Trash2,
  Landmark,
  Leaf,
  TrendingUp,
  Briefcase,
  FolderOpen,
  ScrollText,
} from "lucide-react";
import CodeBlock from "../../components/widgets/CodeBlock";
import Alert from "../../components/widgets/Alert";
import Button from "../../components/widgets/Button";
import Divider from "../../components/widgets/Divider";
import Metric from "../../components/widgets/Metric";
import { useAppState } from "../../state/AppState";
import {
  fetchAuditLogs,
  fetchIntentCacheStats,
  invalidateIntentCacheDomain,
  clearIntentCache,
} from "../../services/api";

const DOMAIN_METADATA = {
  sebi_regulation: {
    title: "SEBI Regulatory Directives & Circulars",
    icon: ScrollText,
    badgeColor: "#1B365D",
    badgeBg: "rgba(27, 54, 93, 0.08)",
  },
  corporate_governance: {
    title: "Corporate Governance & Board Oversight",
    icon: Landmark,
    badgeColor: "#5C3A21",
    badgeBg: "rgba(92, 58, 33, 0.08)",
  },
  esg_sustainability: {
    title: "ESG & BRSR Sustainability Disclosures",
    icon: Leaf,
    badgeColor: "#2E7D32",
    badgeBg: "rgba(46, 125, 50, 0.08)",
  },
  financial_performance: {
    title: "Financial Performance, Revenue & Earnings",
    icon: TrendingUp,
    badgeColor: "#D97706",
    badgeBg: "rgba(217, 119, 6, 0.08)",
  },
  fund_performance: {
    title: "Fund NAV, Portfolio Holdings & Returns",
    icon: Briefcase,
    badgeColor: "#4338CA",
    badgeBg: "rgba(67, 56, 202, 0.08)",
  },
};

export default function AdminAuditTab() {
  const { auditLines, setAuditLines } = useAppState();
  const [loadingLogs, setLoadingLogs] = useState(false);

  // Intent Cache State
  const [cacheData, setCacheData] = useState(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [actionLoading, setActionLoading] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const loadCacheStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const resp = await fetchIntentCacheStats();
      if (resp) {
        setCacheData(resp);
      }
    } catch (err) {
      console.warn("Could not fetch intent cache stats:", err);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  useEffect(() => {
    loadCacheStats();
  }, [loadCacheStats]);

  const handleRefreshLogs = async () => {
    setLoadingLogs(true);
    try {
      const resp = await fetchAuditLogs(30);
      if (resp && resp.lines && resp.lines.length > 0) {
        setAuditLines(resp.lines);
      }
    } catch (err) {
      console.warn("Could not refresh audit logs:", err);
    } finally {
      setLoadingLogs(false);
    }
  };

  const handleInvalidateDomain = async (domain) => {
    setActionLoading(domain);
    setFeedback(null);
    try {
      const resp = await invalidateIntentCacheDomain(domain);
      setFeedback({
        type: "success",
        message: resp.message || `Partition '${domain}' invalidated cleanly.`,
      });
      await loadCacheStats();
    } catch (err) {
      setFeedback({
        type: "error",
        message: `Failed to invalidate domain '${domain}': ${err.message}`,
      });
    } finally {
      setActionLoading("");
    }
  };

  const handleClearAll = async () => {
    setActionLoading("clear_all");
    setFeedback(null);
    try {
      await clearIntentCache();
      setFeedback({
        type: "success",
        message: "All Intent Cache partitions and semantic cache layers have been flushed cleanly.",
      });
      setConfirmClear(false);
      await loadCacheStats();
    } catch (err) {
      setFeedback({
        type: "error",
        message: `Failed to clear cache: ${err.message}`,
      });
    } finally {
      setActionLoading("");
    }
  };

  const cache = cacheData?.cache || { hits: 0, misses: 0, hit_rate: 0, buckets: {} };
  const savings = cacheData?.savings || {
    total_hits: 0,
    total_misses: 0,
    hit_rate_pct: 0,
    tokens_saved_cumulative: 0,
    cost_saved_cumulative_usd: 0,
    co2_saved_grams: 0,
  };
  const domains = cacheData?.domains || Object.keys(DOMAIN_METADATA);
  const thresholds = cacheData?.thresholds || {};
  const ttls = cacheData?.ttls_seconds || {};

  const totalQueries = (savings.total_hits || 0) + (savings.total_misses || 0);

  const formatTtl = (seconds) => {
    if (!seconds) return "—";
    const days = Math.round(seconds / 86400);
    return `${days} days (${seconds.toLocaleString()}s)`;
  };

  return (
    <div>
      {/* ── INTENT CACHE & SAVINGS LEDGER ── */}
      <div className="stRow stRow--responsive" style={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.8rem" }}>
        <div style={{ flex: "1 1 300px" }}>
          <h3 className="stSubheader" style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <Database size={19} strokeWidth={1.75} />
            Cognitive Intent Cache &amp; Green AI Savings Ledger
          </h3>
          <div className="stCaption" style={{ marginTop: 4 }}>
            Multi-tiered cognitive caching: Stage 1 $O(1)$ Fingerprint Probe (&lt;1ms) + Stage 2 Domain-Partitioned Cosine Similarity (0.92–0.95) with Date-Entity Guards.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ minWidth: 150 }}>
            <Button kind="secondary" fullWidth onClick={loadCacheStats} disabled={loadingStats}>
              <RefreshCw size={15} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-2px" }} />
              {loadingStats ? "Refreshing…" : "Refresh Stats"}
            </Button>
          </div>
          <div style={{ minWidth: 130 }}>
            {!confirmClear ? (
              <Button kind="secondary" fullWidth onClick={() => setConfirmClear(true)} disabled={actionLoading === "clear_all"}>
                <Trash2 size={15} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-2px" }} />
                Clear All
              </Button>
            ) : (
              <Button kind="danger" fullWidth onClick={handleClearAll} disabled={actionLoading === "clear_all"}>
                Confirm Flush?
              </Button>
            )}
          </div>
        </div>
      </div>

      {feedback && (
        <div style={{ marginTop: 12, marginBottom: 12 }}>
          <Alert type={feedback.type}>{feedback.message}</Alert>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "12px",
          marginTop: "16px",
          marginBottom: "20px",
        }}
      >
        <Metric
          label="Intent Cache Hit Rate"
          value={`${savings.hit_rate_pct ?? 0}%`}
          delta={`${savings.total_hits ?? 0} hits / ${savings.total_misses ?? 0} misses`}
        />
        <Metric
          label="Tokens Saved"
          value={(savings.tokens_saved_cumulative ?? 0).toLocaleString()}
          delta="Cumulative vs Cold LLM"
        />
        <Metric
          label="Cold Compute Cost Averted"
          value={`$${(savings.cost_saved_cumulative_usd ?? 0).toFixed(4)}`}
          delta="Estimated USD Savings"
        />
        <Metric
          label="Green AI: CO₂ Averted"
          value={`${(savings.co2_saved_grams ?? 0).toFixed(2)} g`}
          delta="Carbon Emissions Offset"
        />
        <Metric
          label="Queries Processed"
          value={totalQueries.toLocaleString()}
          delta={`${cacheData?.domains?.length || 5} Domain Partitions`}
        />
      </div>

      {/* Domain Partition Table */}
      <div style={{ marginTop: "12px", marginBottom: "24px" }}>
        <h4 style={{ margin: "0 0 8px 0", fontSize: "0.95rem", color: "#31333F", fontWeight: 600 }}>
          Domain Partition Governance &amp; Invalidation Controls
        </h4>
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch", border: "1px solid #E7E1D4", borderRadius: "8px" }}>
          <table style={{ width: "100%", minWidth: "600px", borderCollapse: "collapse", textAlign: "left", fontSize: "0.88rem" }}>
            <thead>
              <tr style={{ backgroundColor: "#F8F6F0", borderBottom: "1px solid #E7E1D4" }}>
                <th style={{ padding: "10px 14px", fontWeight: 600, color: "#5C574C" }}>Domain Bucket</th>
                <th style={{ padding: "10px 14px", fontWeight: 600, color: "#5C574C" }}>Cognitive Gate Threshold</th>
                <th style={{ padding: "10px 14px", fontWeight: 600, color: "#5C574C" }}>Partition TTL</th>
                <th style={{ padding: "10px 14px", fontWeight: 600, color: "#5C574C" }}>Cached Entries</th>
                <th style={{ padding: "10px 14px", fontWeight: 600, color: "#5C574C", textAlign: "right" }}>Partition Action</th>
              </tr>
            </thead>
            <tbody>
              {domains.map((dom) => {
                const meta = DOMAIN_METADATA[dom] || {
                  title: dom,
                  icon: FolderOpen,
                  badgeColor: "#31333F",
                  badgeBg: "rgba(49, 51, 63, 0.08)",
                };
                const DomainIcon = meta.icon;
                const thresh = thresholds[dom] !== undefined ? thresholds[dom] : "—";
                const ttlSec = ttls[dom];
                const count = cache.buckets?.[dom] ?? 0;
                const isInvalidating = actionLoading === dom;

                return (
                  <tr key={dom} style={{ borderBottom: "1px solid #F0EAE1" }}>
                    <td style={{ padding: "10px 14px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <DomainIcon size={17} strokeWidth={1.75} style={{ color: meta.badgeColor, flexShrink: 0 }} />
                        <div>
                          <span
                            style={{
                              display: "inline-block",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              backgroundColor: meta.badgeBg,
                              color: meta.badgeColor,
                              textTransform: "uppercase",
                              marginBottom: "2px",
                            }}
                          >
                            {dom}
                          </span>
                          <div style={{ fontSize: "0.82rem", color: "#555" }}>{meta.title}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontFamily: "monospace", fontWeight: 600, color: "#2B5329" }}>
                        ≥ {thresh}
                      </span>{" "}
                      <span style={{ color: "#777", fontSize: "0.8rem" }}>cosine</span>
                    </td>
                    <td style={{ padding: "10px 14px", color: "#555" }}>{formatTtl(ttlSec)}</td>
                    <td style={{ padding: "10px 14px" }}>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "12px",
                          fontSize: "0.8rem",
                          fontWeight: 600,
                          backgroundColor: count > 0 ? "rgba(46, 125, 50, 0.12)" : "rgba(0, 0, 0, 0.05)",
                          color: count > 0 ? "#2E7D32" : "#888",
                        }}
                      >
                        {count} {count === 1 ? "entry" : "entries"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 14px", textAlign: "right" }}>
                      <button
                        onClick={() => handleInvalidateDomain(dom)}
                        disabled={isInvalidating || count === 0}
                        style={{
                          padding: "4px 10px",
                          fontSize: "0.8rem",
                          fontWeight: 600,
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--color-border)",
                          backgroundColor: isInvalidating ? "var(--color-surface-tan)" : count === 0 ? "var(--color-surface-tan)" : "var(--color-surface)",
                          color: count === 0 ? "var(--color-ink-400)" : "var(--color-navy-700)",
                          cursor: count === 0 ? "not-allowed" : "pointer",
                          transition: "all var(--duration-fast) var(--ease-standard)",
                        }}
                        title={`Invalidate cache entries for ${dom}`}
                      >
                        {isInvalidating ? "Flushing…" : "Invalidate Partition"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <Divider />

      {/* ── SECURITY & AUDIT LOGS ── */}
      <div className="stRow" style={{ alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
        <h3 className="stSubheader" style={{ margin: 0 }}>System Governance &amp; Compliance Audit Stream</h3>
        <div style={{ width: 180 }}>
          <Button kind="secondary" fullWidth onClick={handleRefreshLogs} disabled={loadingLogs}>
            <RefreshCw size={15} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-2px" }} />
            {loadingLogs ? "Refreshing…" : "Refresh Logs"}
          </Button>
        </div>
      </div>
      {auditLines.length === 0 ? (
        <Alert type="info">No query audit events recorded yet.</Alert>
      ) : (
        <>
          <div className="stCaption" style={{ marginTop: 8 }}>
            Displaying recent {Math.min(auditLines.length, 30)} audit events from <code>query_execution_audit.jsonl</code>:
          </div>
          <CodeBlock>{auditLines.slice(-30).join("\n")}</CodeBlock>
        </>
      )}
    </div>
  );
}
