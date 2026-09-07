import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import TextInput from "../components/widgets/TextInput";
import Button from "../components/widgets/Button";
import Expander from "../components/widgets/Expander";
import Divider from "../components/widgets/Divider";
import Alert from "../components/widgets/Alert";
import { useAppState } from "../state/AppState";
import { useToast } from "../components/widgets/Toast";
import TraditionalPanel from "./panels/TraditionalPanel";
import ContextGraphPanel from "./panels/ContextGraphPanel";

export default function CompareTab({ role }) {
  const {
    compareSessionId, compareQuery, setCompareQuery,
    isCompareLoading, getCompareHistory,
    startNewCompareSession, loadCompareSession, sendCompareMessage,
    clearCache, isCacheClearing,
    lastHybrid, lastTraditional,
  } = useAppState();
  const pushToast = useToast();

  const [resumeId, setResumeId] = useState("");
  const [resumeError, setResumeError] = useState("");

  const history = getCompareHistory(compareSessionId);

  const handleClearCache = async () => {
    const ok = await clearCache();
    if (ok) {
      pushToast("Intent Cache cleared cleanly! Next query will execute full LLM synthesis.");
    } else {
      pushToast("Intent Cache flushed locally.");
    }
  };

  const handleRun = async () => {
    if (!compareQuery.trim() || isCompareLoading) return;
    await sendCompareMessage();
  };

  const handleResumeLoad = () => {
    if (!resumeId.trim()) return;
    const ok = loadCompareSession(resumeId.trim());
    if (!ok) {
      setResumeError("No saved session found with that ID.");
    } else {
      setResumeError("");
      pushToast("Loaded saved comparison session!");
    }
  };

  const turns = [];
  for (let i = 0; i < history.length; i += 2) {
    turns.push([history[i], history[i + 1]]);
  }

  return (
    <div>
      <div className="stCompareBar">
        <div className="stCompareBar-input">
          <TextInput
            value={compareQuery}
            onChange={setCompareQuery}
            labelVisible={false}
            placeholder="Type your query and run it against both search modes (Traditional vs ContextGraph)…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleRun();
              }
            }}
          />
        </div>
        <div className="stCompareBar-actions">
          <Button kind="primary" disabled={isCompareLoading || !compareQuery.trim()} onClick={handleRun}>
            {isCompareLoading ? "Running…" : "Run query"}
          </Button>
          <Button
            kind="secondary"
            onClick={() => {
              startNewCompareSession();
              pushToast("Started new comparison session");
            }}
          >
            <Plus size={15} strokeWidth={2} style={{ marginRight: 6, verticalAlign: "-2px" }} />
            New Session
          </Button>
          <Button
            kind="secondary"
            disabled={isCacheClearing}
            title="Flush in-memory and disk intent cache so next query performs fresh LLM synthesis"
            onClick={handleClearCache}
          >
            <Trash2 size={15} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-2px" }} />
            {isCacheClearing ? "Flushing…" : "Clear Cache"}
          </Button>
        </div>
      </div>

      <Expander title={<>Comparison Session: <code>{compareSessionId}</code>  ·  resume a previous session</>}>
        <TextInput
          value={resumeId}
          onChange={setResumeId}
          labelVisible={false}
          placeholder="Paste a comparison session ID and press Enter…"
        />
        {resumeId && (
          <div style={{ marginTop: 8 }}>
            <Button kind="secondary" onClick={handleResumeLoad}>Load session</Button>
          </div>
        )}
        {resumeError && <div style={{ marginTop: 8 }}><Alert type="error">{resumeError}</Alert></div>}
      </Expander>

      {turns.length === 0 && (lastTraditional || lastHybrid) && (
        <div className="stRow stRow--compare">
          <div className="stCol" style={{ flex: 1 }}>
            {lastTraditional && <TraditionalPanel r={lastTraditional} />}
          </div>
          <div className="stCol" style={{ flex: 1 }}>
            {lastHybrid && (
              <ContextGraphPanel
                r={lastHybrid}
                entitySummary={lastHybrid.entity_summary}
                showFeedback={false}
              />
            )}
          </div>
        </div>
      )}

      {[...turns].reverse().map(([userMsg, asstMsg], i) => (
        <div key={i}>
          <div style={{ fontSize: "1rem", margin: "0.5rem 0" }}>
            <b>Comparison Turn {userMsg.turn_index ?? 1}:</b> {userMsg.content}
          </div>
          {!asstMsg ? (
            <Divider />
          ) : asstMsg.loading ? (
            <>
              <div className="stRow stRow--compare">
                <div className="stCol" style={{ flex: 1 }}>
                  <Alert type="info">Traditional RAG is generating…</Alert>
                </div>
                <div className="stCol" style={{ flex: 1 }}>
                  <Alert type="info">ContextGraph is generating…</Alert>
                </div>
              </div>
              <Divider />
            </>
          ) : (
            <>
              {asstMsg.error_trad && <Alert type="error">Traditional RAG failed: {asstMsg.error_trad}</Alert>}
              {asstMsg.error_hybrid && <Alert type="error">ContextGraph failed: {asstMsg.error_hybrid}</Alert>}
              <div className="stRow stRow--compare">
                <div className="stCol" style={{ flex: 1 }}>
                  {asstMsg.traditional ? (
                    <TraditionalPanel r={asstMsg.traditional} />
                  ) : (
                    <Alert type="warning">No traditional search result.</Alert>
                  )}
                </div>
                <div className="stCol" style={{ flex: 1 }}>
                  {asstMsg.hybrid ? (
                    <ContextGraphPanel
                      r={asstMsg.hybrid}
                      entitySummary={asstMsg.hybrid?.entity_summary}
                      showFeedback={false}
                    />
                  ) : (
                    <Alert type="warning">No ContextGraph result.</Alert>
                  )}
                </div>
              </div>
              <Divider />
            </>
          )}
        </div>
      ))}
    </div>
  );
}
