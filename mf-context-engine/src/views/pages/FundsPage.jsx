import { useState, useMemo } from "react";
import Selectbox from "../../components/widgets/Selectbox";
import Divider from "../../components/widgets/Divider";
import DataFrame from "../../components/widgets/DataFrame";
import Alert from "../../components/widgets/Alert";

const FUNDS_MATRIX = [
  { "Fund ID": "SEBI_FUND_001", Name: "HDFC Top 100 Bluechip Fund", Category: "Equity", "AUM (Cr)": "₹45,250", Portfolio: "WARN", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "88%" },
  { "Fund ID": "SEBI_FUND_002", Name: "ICICI Prudential Corp Bond", Category: "Debt", "AUM (Cr)": "₹28,400", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "100%" },
  { "Fund ID": "SEBI_FUND_003", Name: "SBI Balanced Advantage Dynamic", Category: "Hybrid", "AUM (Cr)": "₹31,200", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "96%" },
  { "Fund ID": "SEBI_FUND_004", Name: "Nippon India Small Cap Equity", Category: "Equity", "AUM (Cr)": "₹52,100", Portfolio: "PASS", Gov: "PASS", KYC: "WARN", Risk: "WARN", NAV: "PASS", Score: "82%" },
  { "Fund ID": "SEBI_FUND_005", Name: "Axis Liquid Treasury Cash", Category: "Debt", "AUM (Cr)": "₹39,000", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "100%" },
  { "Fund ID": "SEBI_FUND_006", Name: "Kotak Emerging Equity Mid Cap", Category: "Equity", "AUM (Cr)": "₹41,500", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "95%" },
  { "Fund ID": "SEBI_FUND_007", Name: "Aditya Birla Frontline Equity", Category: "Equity", "AUM (Cr)": "₹26,300", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "98%" },
  { "Fund ID": "SEBI_FUND_008", Name: "Mirae Asset Tax Saver ELSS", Category: "Equity", "AUM (Cr)": "₹21,800", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "100%" },
  { "Fund ID": "SEBI_FUND_009", Name: "UTI Nifty 50 Index Passive", Category: "Index", "AUM (Cr)": "₹18,500", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "100%" },
  { "Fund ID": "SEBI_FUND_010", Name: "DSP Overnight Treasury Cash", Category: "Debt", "AUM (Cr)": "₹12,400", Portfolio: "PASS", Gov: "PASS", KYC: "PASS", Risk: "PASS", NAV: "PASS", Score: "100%" },
];

const SCHEME_VIOLATIONS = {
  SEBI_FUND_001: [
    { violation_id: "V_20260819_001", rule: "Single Holding Concentration", breach: "Reliance Ind. at 18.2% (cap: 15%)", severity: "critical" },
    { violation_id: "V_20260819_002", rule: "Sector Exposure Limit", breach: "IT Sector at 34.0% (cap: 30%)", severity: "high" },
  ],
  SEBI_FUND_004: [
    { violation_id: "V_20260819_003", rule: "KYC Freshness Recency", breach: "42 investor accounts exceed 365 days", severity: "high" },
    { violation_id: "V_20260819_004", rule: "Daily 99% VaR Limit", breach: "1-day simulated VaR is 4.6% (cap: 4.0%)", severity: "high" },
  ],
};

export default function FundsPage() {
  const [catFilter, setCatFilter] = useState("All Categories");
  const [selectedFundId, setSelectedFundId] = useState(FUNDS_MATRIX[0]["Fund ID"]);

  const filteredFunds = useMemo(() => {
    if (catFilter === "All Categories") return FUNDS_MATRIX;
    return FUNDS_MATRIX.filter((f) => f.Category === catFilter);
  }, [catFilter]);

  const selectedRow = useMemo(() => {
    return FUNDS_MATRIX.find((f) => f["Fund ID"] === selectedFundId) || FUNDS_MATRIX[0];
  }, [selectedFundId]);

  const activeBreaches = SCHEME_VIOLATIONS[selectedFundId] || [];

  return (
    <div>
      <h1 className="stTitle">🏢 Fund Scheme Compliance Heatmap</h1>
      <div className="stCaption">Scheme Health Matrix Across All 5 Statutory Domains</div>

      <div style={{ marginTop: "1rem", maxWidth: "320px" }}>
        <Selectbox
          label="Filter Scheme Category"
          options={["All Categories", "Equity", "Debt", "Hybrid", "Index"]}
          value={catFilter}
          onChange={setCatFilter}
        />
      </div>

      <div style={{ marginTop: "1.2rem" }}>
        <h3 className="stSubheader">📊 5-Domain Compliance Matrix</h3>
        <DataFrame
          columns={["Fund ID", "Name", "Category", "AUM (Cr)", "Portfolio", "Gov", "KYC", "Risk", "NAV", "Score"]}
          rows={filteredFunds}
        />
      </div>

      <Divider />

      <h3 className="stSubheader">🔍 Fund Scheme Detailed Audit Inspection</h3>
      <div style={{ maxWidth: "400px", marginBottom: "1rem" }}>
        <Selectbox
          label="Select Scheme to Inspect"
          options={FUNDS_MATRIX.map((f) => f["Fund ID"])}
          value={selectedFundId}
          onChange={setSelectedFundId}
        />
      </div>

      <div className="stRow" style={{ gap: "1rem", marginBottom: "1.2rem" }}>
        <div className="stCol" style={{ flex: 1 }}>
          <Alert type="info">
            <b>Scheme Name</b>: {selectedRow.Name}
          </Alert>
        </div>
        <div className="stCol" style={{ flex: 1 }}>
          <Alert type="info">
            <b>Asset Class</b>: {selectedRow.Category}
          </Alert>
        </div>
        <div className="stCol" style={{ flex: 1 }}>
          <Alert type="info">
            <b>Total AUM</b>: {selectedRow["AUM (Cr)"]}
          </Alert>
        </div>
        <div className="stCol" style={{ flex: 1 }}>
          <Alert type="success">
            <b>Health Score</b>: {selectedRow.Score}
          </Alert>
        </div>
      </div>

      <h4 style={{ margin: "0.8rem 0 0.4rem 0", color: "#31333F" }}>Registered Breaches for Scheme</h4>
      {activeBreaches.length > 0 ? (
        <DataFrame
          columns={["violation_id", "rule", "breach", "severity"]}
          rows={activeBreaches}
        />
      ) : (
        <Alert type="success">Zero active violations recorded for this scheme.</Alert>
      )}
    </div>
  );
}
