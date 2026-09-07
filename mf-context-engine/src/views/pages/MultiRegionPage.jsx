import { useState } from "react";
import { Globe2, BarChart3, Scale, Rocket } from "lucide-react";
import Metric from "../../components/widgets/Metric";
import Divider from "../../components/widgets/Divider";
import DataFrame from "../../components/widgets/DataFrame";
import Selectbox from "../../components/widgets/Selectbox";
import Button from "../../components/widgets/Button";
import Alert from "../../components/widgets/Alert";
import CodeBlock from "../../components/widgets/CodeBlock";
import { useToast } from "../../components/widgets/Toast";

const BENCHMARK_TABLE = [
  {
    "Regulatory Area": "Single Holding Concentration Limit",
    "SEBI (India)": "15.0% Maximum",
    "US SEC (USA)": "5.0% Maximum (12d-1)",
    "ESMA (Europe)": "10.0% Maximum (5/10/40 rule)",
    "Strictest Jurisdiction": "US SEC (5.0%)",
  },
  {
    "Regulatory Area": "Sector Concentration Limit",
    "SEBI (India)": "30.0% Maximum",
    "US SEC (USA)": "25.0% Maximum",
    "ESMA (Europe)": "30.0% Maximum",
    "Strictest Jurisdiction": "US SEC (25.0%)",
  },
  {
    "Regulatory Area": "Daily NAV Disclosure Cutoff",
    "SEBI (India)": "21:00 IST (Daily)",
    "US SEC (USA)": "16:00 ET (4:00 PM)",
    "ESMA (Europe)": "Daily Publication",
    "Strictest Jurisdiction": "US SEC / SEBI",
  },
  {
    "Regulatory Area": "Board Independence Mandate",
    "SEBI (India)": "50% Independent Trustees",
    "US SEC (USA)": "40% Independent Directors",
    "ESMA (Europe)": "45% Independent Members",
    "Strictest Jurisdiction": "SEBI (50.0%)",
  },
  {
    "Regulatory Area": "Liquidity Buffer Requirement",
    "SEBI (India)": "5.0% Liquid Cash Buffer",
    "US SEC (USA)": "15.0% Highly Liquid Assets",
    "ESMA (Europe)": "80% Tradable in 5 Days",
    "Strictest Jurisdiction": "ESMA (80% 5-Day)",
  },
  {
    "Regulatory Area": "ESG / Sustainability Disclosures",
    "SEBI (India)": "BRSR Framework (Top 1000)",
    "US SEC (USA)": "Climate Risk Proposed Rules",
    "ESMA (Europe)": "SFDR Article 8/9 Mandatory",
    "Strictest Jurisdiction": "ESMA (SFDR Mandatory)",
  },
];

export default function MultiRegionPage() {
  const [globalFund, setGlobalFund] = useState("GLOBAL_EQUITY_001 (Cross-Border Global Opportunity Fund)");
  const [isAuditing, setIsAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState(null);
  const pushToast = useToast();

  const handleRunGlobalAudit = () => {
    setIsAuditing(true);
    setTimeout(() => {
      setIsAuditing(false);
      setAuditResult({
        fund_id: "GLOBAL_EQUITY_001",
        jurisdictions_evaluated: ["SEBI", "SEC", "ESMA"],
        total_rules_evaluated: 140,
        overall_harmonized_score: "88.2%",
        regional_findings: {
          SEBI: { status: "COMPLIANT", breaches: 0 },
          SEC: { status: "NON_COMPLIANT", breaches: 1, detail: "Single holding 8.5% exceeds 5.0% SEC limit" },
          ESMA: { status: "COMPLIANT", breaches: 0, detail: "Complies with 10% UCITS cap" },
        },
      });
      pushToast("Global 3-Jurisdiction Audit Completed!");
    }, 600);
  };

  return (
    <div>
      <h1 className="stTitle">
        <Globe2 size={26} strokeWidth={1.75} style={{ marginRight: 10, verticalAlign: "-5px" }} />
        Multi-Jurisdiction Regulatory Comparison
      </h1>
      <div className="stCaption">Cross-Border Harmonization: SEBI (India) • US SEC (USA) • ESMA (Europe)</div>

      <h3 className="stSubheader" style={{ marginTop: "1.2rem" }}>
        <BarChart3 size={17} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
        Regional Scorecards Comparison
      </h3>
      <div className="stCardGrid">
        <div className="cg-panel" style={{ padding: "1rem" }}>
          <h4 style={{ margin: "0 0 0.5rem 0", color: "var(--color-ink-900)" }}>SEBI (India)</h4>
          <Metric label="Compliance Score" value="91.2%" delta="+1.5%" />
          <div className="stCaption" style={{ marginTop: "0.5rem" }}>
            Regulations: 52 Circulars | Rules: 32 Rules
          </div>
        </div>

        <div className="cg-panel" style={{ padding: "1rem" }}>
          <h4 style={{ margin: "0 0 0.5rem 0", color: "var(--color-ink-900)" }}>US SEC (USA)</h4>
          <Metric label="Compliance Score" value="86.5%" delta="-0.8%" />
          <div className="stCaption" style={{ marginTop: "0.5rem" }}>
            Regulations: 105 Items | Rules: 54 Rules
          </div>
        </div>

        <div className="cg-panel" style={{ padding: "1rem" }}>
          <h4 style={{ margin: "0 0 0.5rem 0", color: "var(--color-ink-900)" }}>ESMA (European Union)</h4>
          <Metric label="Compliance Score" value="89.0%" delta="+2.1%" />
          <div className="stCaption" style={{ marginTop: "0.5rem" }}>
            Regulations: 105 Articles | Rules: 54 Rules
          </div>
        </div>
      </div>

      <Divider />

      <h3 className="stSubheader">
        <Scale size={17} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
        Regulatory Threshold Benchmark Matrix
      </h3>
      <DataFrame
        columns={["Regulatory Area", "SEBI (India)", "US SEC (USA)", "ESMA (Europe)", "Strictest Jurisdiction"]}
        rows={BENCHMARK_TABLE}
      />

      <Divider />

      <h3 className="stSubheader">
        <Rocket size={17} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
        Run Global Multi-Jurisdiction Audit
      </h3>
      <p style={{ color: "#5C574C", margin: "0 0 1rem 0" }}>
        Simulate audit of a fund scheme evaluated simultaneously against all 3 regulatory regimes.
      </p>

      <div className="stRow stRow--responsive" style={{ alignItems: "flex-end", maxWidth: "700px" }}>
        <div className="stCol" style={{ flex: 3 }}>
          <Selectbox
            label="Select Global Scheme"
            options={["GLOBAL_EQUITY_001 (Cross-Border Global Opportunity Fund)"]}
            value={globalFund}
            onChange={setGlobalFund}
          />
        </div>
        <div className="stCol" style={{ flex: 2 }}>
          <Button kind="primary" fullWidth onClick={handleRunGlobalAudit} disabled={isAuditing}>
            <Rocket size={16} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
            {isAuditing ? "Evaluating..." : "Audit All 3 Jurisdictions"}
          </Button>
        </div>
      </div>

      {auditResult && (
        <div style={{ marginTop: "1.2rem" }}>
          <Alert type="success">
            Global Audit Completed! Evaluated 140 rules across 3 jurisdictions in 48ms.
          </Alert>
          <div style={{ marginTop: "0.8rem" }}>
            <CodeBlock code={JSON.stringify(auditResult, null, 2)} />
          </div>
        </div>
      )}
    </div>
  );
}
