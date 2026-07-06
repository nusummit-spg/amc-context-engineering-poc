import "./Banners.css";

export function ErrorBanner({ error, onRetry, title = "Couldn't load this" }) {
  const message = error?.message || "Something went wrong.";
  const code = error?.code;
  return (
    <div className="banner banner--error" role="alert">
      <div className="banner__icon" aria-hidden="true">!</div>
      <div className="banner__body">
        <strong>{title}</strong>
        <p>{message}{code ? <span className="banner__code"> · {code}</span> : null}</p>
      </div>
      {onRetry && (
        <button className="btn btn--ghost banner__action" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function DemoModeNotice({ compact = false }) {
  return (
    <div className={`banner banner--demo ${compact ? "banner--compact" : ""}`}>
      <div className="banner__icon" aria-hidden="true">◆</div>
      <div className="banner__body">
        <strong>Showing demo data</strong>
        {!compact && <p>The API at this address didn't respond, so this panel is showing fixture data shaped like the real response. Start the backend to see live results.</p>}
      </div>
    </div>
  );
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="empty-state">
      <h4>{title}</h4>
      {hint && <p>{hint}</p>}
      {action}
    </div>
  );
}
