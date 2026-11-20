import { useId, useState } from "react";
import { AlertTriangle, CalendarClock, ChevronDown, Database, HelpCircle, Info, ShieldOff } from "lucide-react";
import MarkdownAnswer from "../provenance/MarkdownAnswer";
import {
  INCOMPLETE_TEXT, answerKindOf, asOfBadge, cellText, columnHeader, computationFacts, exclusionNotes,
  filterChips, isNumericColumn, summaryLine,
} from "../../utils/answer40";
import "./answer40.css";

/**
 * Wave 4.0 typed answer (TDS-40 E11.1). Returns null for DOCUMENT answers, which keep the existing
 * markdown + citation rendering. Every figure shown comes from the verified `structured_result`.
 */
export default function AnswerCard40({ r, query, onPickPrompt }) {
  const kind = answerKindOf(r);
  if (kind === "STRUCTURED") return <StructuredCard r={r} />;
  if (kind === "ABSTAIN") return <AbstainCard r={r} onPickPrompt={onPickPrompt} />;
  if (kind === "CLARIFY") return <ClarifyCard r={r} query={query} onPickPrompt={onPickPrompt} />;
  return null;
}

export function IncompleteBanner({ state }) {
  if (!state || !INCOMPLETE_TEXT[state]) return null;
  return (
    <div className={`a40-banner a40-banner--${state}`} role="status" data-testid={`answer-${state}`}>
      <AlertTriangle size={14} aria-hidden="true" />
      <span><strong>{state === "stopped" ? "Incomplete answer." : "Answer withdrawn."}</strong>{" "}
        {INCOMPLETE_TEXT[state]}</span>
    </div>
  );
}

function StructuredCard({ r }) {
  const sr = r.structured_result || {};
  const columns = sr.columns || [];
  const rows = sr.rows || [];
  const badge = asOfBadge(sr);
  const chips = filterChips(sr);
  const notes = exclusionNotes(sr);
  const [open, setOpen] = useState(false);
  const drawerId = useId();
  const summary = summaryLine(r.answer);

  return (
    <section className="a40-card a40-card--structured" aria-label="Verified fund data answer" data-testid="answer-structured">
      <div className="a40-card-head">
        <span className="a40-kind"><Database size={13} aria-hidden="true" /> Verified fund data</span>
        {badge && (
          <span className="a40-badge" title={badge.title} aria-label={`As of: ${badge.title}`}>
            <CalendarClock size={12} aria-hidden="true" /> {badge.text}
          </span>
        )}
      </div>
      {summary && <div className="a40-summary"><MarkdownAnswer text={summary} citations={[]} metrics={[]} /></div>}
      {chips.length > 0 && (
        <ul className="a40-chips" aria-label="Filters applied">
          {chips.map((c) => <li key={c} className="a40-chip">{c}</li>)}
        </ul>
      )}
      <div className="a40-table-wrap" tabIndex={0} role="region" aria-label="Result table, scrollable">
        <table className="a40-table">
          <caption className="a40-sr-only">
            {summary.replace(/\*\*/g, "") || "Verified result"}
          </caption>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.id} scope="col" className={isNumericColumn(c) ? "a40-num" : undefined}>{columnHeader(c)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => {
                  const c = columns[j] || {};
                  const Cell = j === 0 && c.id !== "rank" ? "th" : "td";
                  return (
                    <Cell key={j} scope={Cell === "th" ? "row" : undefined}
                          className={isNumericColumn(c) ? "a40-num" : undefined}>
                      {cellText(v, c)}
                    </Cell>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {notes.map((n) => <p key={n} className="a40-note"><Info size={12} aria-hidden="true" /> {n}</p>)}
      {r.confidence_reason && <p className="a40-disclosure">{r.confidence_reason}</p>}
      <button type="button" className="a40-drawer-toggle" aria-expanded={open} aria-controls={drawerId}
              onClick={() => setOpen((v) => !v)}>
        <ChevronDown size={13} aria-hidden="true" className={open ? "a40-rot" : undefined} />
        How was this computed?
      </button>
      {open && (
        <dl id={drawerId} className="a40-facts">
          {computationFacts(sr).map(([k, v]) => (
            <div key={k} className="a40-fact"><dt>{k}</dt><dd><code>{v}</code></dd></div>
          ))}
        </dl>
      )}
    </section>
  );
}

function PromptChips({ items, label, onPick, testid }) {
  if (!items?.length) return null;
  return (
    <ul className="a40-chips a40-chips--actions" aria-label={label} data-testid={testid}>
      {items.map((o) => (
        <li key={o}>
          <button type="button" className="a40-chip a40-chip--button" onClick={() => onPick?.(o)}
                  title="Put this in the question box">{o}</button>
        </li>
      ))}
    </ul>
  );
}

function AbstainCard({ r, onPickPrompt }) {
  const a = r.abstention || {};
  const advice = a.code === "OUT_OF_SCOPE_ADVICE";
  return (
    <section className="a40-card a40-card--abstain" aria-label="No answer given" data-testid="answer-abstain"
             data-code={a.code || ""}>
      <div className="a40-card-head">
        <span className="a40-kind">
          <ShieldOff size={13} aria-hidden="true" /> {advice ? "Outside this assistant's scope" : "No verified answer"}
        </span>
      </div>
      <p className="a40-message">{a.message || r.answer}</p>
      {!advice && <p className="a40-note">No estimate has been substituted.</p>}
      <PromptChips items={a.suggestions} label="You can ask instead" onPick={onPickPrompt} testid="abstain-suggestions" />
    </section>
  );
}

function ClarifyCard({ r, query, onPickPrompt }) {
  const c = r.clarification || {};
  return (
    <section className="a40-card a40-card--clarify" aria-label="Clarification needed" data-testid="answer-clarify">
      <div className="a40-card-head">
        <span className="a40-kind"><HelpCircle size={13} aria-hidden="true" /> One detail needed</span>
      </div>
      <p className="a40-message">{c.question || r.answer}</p>
      <PromptChips items={c.options} label="Choose one" testid="clarify-options"
                   onPick={(o) => onPickPrompt?.(o, { clarifies: query })} />
    </section>
  );
}
