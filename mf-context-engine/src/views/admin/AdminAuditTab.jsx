import { useState } from "react";
import CodeBlock from "../../components/widgets/CodeBlock";
import Alert from "../../components/widgets/Alert";
import Button from "../../components/widgets/Button";
import { useAppState } from "../../state/AppState";
import { fetchAuditLogs } from "../../services/api";

export default function AdminAuditTab() {
  const { auditLines, setAuditLines } = useAppState();
  const [loading, setLoading] = useState(false);

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const resp = await fetchAuditLogs(30);
      if (resp && resp.lines && resp.lines.length > 0) {
        setAuditLines(resp.lines);
      }
    } catch (err) {
      console.warn("Could not refresh audit logs:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="stRow" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <h3 className="stSubheader" style={{ margin: 0 }}>System Governance &amp; Compliance Audit Stream</h3>
        <div style={{ width: 180 }}>
          <Button kind="secondary" fullWidth onClick={handleRefresh} disabled={loading}>
            {loading ? "Refreshing…" : "🔄 Refresh Logs"}
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
