export default function QueryInputPanel({ text, onTextChange, onRunTraditional, onRunContextGraph, tradLoading, cgLoading }) {
  return (
    <div className="query-input-box">
      <div className="qlabel">Enter your own query</div>
      <textarea
        className="query-textarea"
        rows={3}
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="e.g. What's our exposure to Adani Group across all schemes?"
      />
      <div className="query-run-buttons">
        <button
          className="run-btn run-btn-trad"
          disabled={!text.trim() || tradLoading}
          onClick={() => onRunTraditional(text.trim())}
        >
          {tradLoading ? 'Searching…' : 'Run Traditional Search'}
        </button>
        <button
          className="run-btn run-btn-cg"
          disabled={!text.trim() || cgLoading}
          onClick={() => onRunContextGraph(text.trim())}
        >
          {cgLoading ? 'Searching…' : 'Run ContextGraph Search'}
        </button>
      </div>
    </div>
  );
}