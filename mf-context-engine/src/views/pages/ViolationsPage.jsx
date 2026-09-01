import { useState, useEffect, useMemo } from "react";
import Selectbox from "../../components/widgets/Selectbox";
import TextInput from "../../components/widgets/TextInput";
import Button from "../../components/widgets/Button";
import Expander from "../../components/widgets/Expander";
import Divider from "../../components/widgets/Divider";
import DataFrame from "../../components/widgets/DataFrame";
import BarChart from "../../components/widgets/BarChart";
import Alert from "../../components/widgets/Alert";
import { API_BASE } from "../../services/api";

const SAMPLE_VIOLATIONS = [
  {
    violation_id: "V_20260819_001",
    rule_id: "RULE_PORT_CONC_001",
    fund_id: "SEBI_FUND_001",
    severity: "critical",
    confidence: 0.98,
    actual_value: "18.2%",
    threshold_value: "15.0%",
    description: "Single Holding Concentration breached: Reliance Industries allocation is 18.2%",
    detected_at: "2026-08-19 09:30:00",
    status: "detected",
    region: "SEBI",
  },
  {
    violation_id: "V_20260819_002",
    rule_id: "RULE_PORT_SECTOR_001",
    fund_id: "SEBI_FUND_001",
    severity: "high",
    confidence: 0.92,
    actual_value: "34.0%",
    threshold_value: "30.0%",
    description: "Sector Limit breached: Information Technology sector exposure is 34.0%",
    detected_at: "2026-08-19 09:30:00",
    status: "detected",
    region: "SEBI",
  },
  {
    violation_id: "V_20260819_003",
    rule_id: "RULE_KYC_RECENCY_001",
    fund_id: "SEBI_FUND_004",
    severity: "high",
    confidence: 0.90,
    actual_value: "410 days",
    threshold_value: "365 days",
    description: "KYC Freshness breached: 42 investor records exceed 365-day review cycle",
    detected_at: "2026-08-19 10:15:00",
    status: "detected",
    region: "SEBI",
  },
  {
    violation_id: "V_20260819_004",
    rule_id: "RULE_RISK_VAR_001",
    fund_id: "SEBI_FUND_004",
    severity: "high",
    confidence: 0.95,
    actual_value: "4.6%",
    threshold_value: "4.0%",
    description: "Daily 99% VaR exceeded: Current 1-day simulated VaR is 4.6%",
    detected_at: "2026-08-19 11:00:00",
    status: "detected",
    region: "SEBI",
  },
];

export default function ViolationsPage() {
  const [region, setRegion] = useState("SEBI");
  const [severityFilter, setSeverityFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("detected");
  const [searchKw, setSearchKw] = useState("");
  const [violations, setViolations] = useState(SAMPLE_VIOLATIONS);

  useEffect(() => {
    async function fetchViolations() {
      try {
        const url = `${API_BASE}/compliance/violations?region=${region}${statusFilter !== "all" ? `&status=${statusFilter}` : ""}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            setViolations(data);
            return;
          }
        }
      } catch {}
      // fallback
      setViolations(SAMPLE_VIOLATIONS.map((v) => ({ ...v, region })));
    }
    fetchViolations();
  }, [region, statusFilter]);

  const filteredViolations = useMemo(() => {
    return violations.filter((v) => {
      if (severityFilter !== "All" && v.severity !== severityFilter.toLowerCase()) return false;
      if (statusFilter !== "all" && v.status !== statusFilter) return false;
      if (searchKw.trim()) {
        const kw = searchKw.toLowerCase();
        const desc = (v.description || "").toLowerCase();
        const rId = (v.rule_id || "").toLowerCase();
        const fId = (v.fund_id || "").toLowerCase();
        if (!desc.includes(kw) && !rId.includes(kw) && !fId.includes(kw)) return false;
      }
      return true;
    });
  }, [violations, severityFilter, statusFilter, searchKw]);

  // Severity counts
  const sevCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    filteredViolations.forEach((v) => {
      if (counts[v.severity] !== undefined) counts[v.severity]++;
    });
    return counts;
  }, [filteredViolations]);

  // Leaderboard of breached rules
  const ruleLeaderboard = useMemo(() => {
    const map = {};
    filteredViolations.forEach((v) => {
      map[v.rule_id] = (map[v.rule_id] || 0) + 1;
    });
    return Object.entries(map).map(([rule_id, count]) => ({ "Rule ID": rule_id, "Breach Count": count }));
  }, [filteredViolations]);

  const handleExportCsv = () => {
    if (filteredViolations.length === 0) return;
    const headers = ["violation_id", "rule_id", "fund_id", "severity", "actual_value", "threshold_value", "description", "status"];
    const rows = filteredViolations.map((v) => headers.map((h) => `"${v[h] ?? ""}"`).join(","));
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `compliance_violations_${region}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div>
      <h1 className="stTitle">⚠️ Compliance Violations Explorer</h1>
      <div className="stCaption">Active Regulatory Breaches, Rule Metrics &amp; Resolution Tracking</div>

      <div style={{ marginTop: "1rem" }}>
        <Expander title="🔍 Filter Criteria" defaultOpen={true}>
          <div className="stRow">
            <div className="stCol" style={{ flex: 1 }}>
              <Selectbox label="Region" options={["SEBI", "SEC", "ESMA"]} value={region} onChange={setRegion} />
            </div>
            <div className="stCol" style={{ flex: 1 }}>
              <Selectbox label="Severity" options={["All", "Critical", "High", "Medium", "Low"]} value={severityFilter} onChange={setSeverityFilter} />
            </div>
            <div className="stCol" style={{ flex: 1 }}>
              <Selectbox label="Status" options={["all", "detected", "reviewed", "remediated"]} value={statusFilter} onChange={setStatusFilter} />
            </div>
            <div className="stCol" style={{ flex: 1.5 }}>
              <TextInput label="Keyword Search" value={searchKw} onChange={setSearchKw} placeholder="Search rule, fund, or keywords..." />
            </div>
          </div>
        </Expander>
      </div>

      <div className="stRow" style={{ marginTop: "1rem", gap: "1.5rem" }}>
        <div className="stCol" style={{ flex: 1 }}>
          <h3 className="stSubheader">Severity Breakdown</h3>
          <BarChart
            categories={["Critical", "High", "Medium", "Low"]}
            series={[
              {
                name: "Violations",
                values: [sevCounts.critical, sevCounts.high, sevCounts.medium, sevCounts.low],
              },
            ]}
          />
        </div>
        <div className="stCol" style={{ flex: 1 }}>
          <h3 className="stSubheader">🏆 Top Violated Rules Leaderboard</h3>
          <DataFrame columns={["Rule ID", "Breach Count"]} rows={ruleLeaderboard} />
        </div>
      </div>

      <Divider />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
        <h3 className="stSubheader" style={{ margin: 0 }}>
          📋 Violations Register ({filteredViolations.length} records)
        </h3>
        {filteredViolations.length > 0 && (
          <Button kind="secondary" onClick={handleExportCsv}>
            📥 Export Violations to CSV
          </Button>
        )}
      </div>

      {filteredViolations.length > 0 ? (
        <DataFrame
          columns={["violation_id", "rule_id", "fund_id", "severity", "actual_value", "threshold_value", "description", "status"]}
          rows={filteredViolations}
        />
      ) : (
        <Alert type="success">No violations match the selected filter criteria.</Alert>
      )}
    </div>
  );
}
