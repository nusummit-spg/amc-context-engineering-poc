import "./Header.css";

const STATUS_META = {
  live: { label: "Backend: Healthy", detail: "All systems operational" },
  demo: { label: "Backend: Demo mode", detail: "Using local demo data" },
  checking: { label: "Backend: Checking…", detail: "Contacting server" },
};

export default function Header({ status }) {
  const meta = STATUS_META[status] || STATUS_META.checking;
  return (
    <header className="app-header">
      <div>
        <h2>Compare</h2>
      </div>

      <div className={`status-pill status-pill--${status}`}>
        <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
        <div className="status-pill__text">
          <span className="status-pill__label">{meta.label}</span>
          <span className="status-pill__detail">{meta.detail}</span>
        </div>
      </div>
    </header>
  );
}
