import { Component } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * ErrorBoundary — catches any React render error and shows a readable
 * message instead of a blank white page.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary] Uncaught error:", error, info);
    this.setState({ info });
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    const { error, info } = this.state;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "'Inter', system-ui, sans-serif",
          backgroundColor: "#FAFAF8",
          padding: "2rem",
          color: "#15181D",
        }}
      >
        <div
          style={{
            maxWidth: 680,
            width: "100%",
            background: "#fff",
            borderRadius: 10,
            border: "1px solid #F5C6BC",
            padding: "2rem",
            boxShadow: "0 6px 16px rgba(21,24,29,0.08)",
          }}
        >
          <h1 style={{ display: "flex", alignItems: "center", gap: 10, color: "#9C4A3A", marginBottom: "0.5rem", fontSize: "1.4rem" }}>
            <AlertTriangle size={22} strokeWidth={1.75} />
            Application Error
          </h1>
          <p style={{ color: "#3B4149", marginBottom: "1.5rem" }}>
            The app encountered an unexpected error. Open your browser's developer
            console (F12 → Console) for full details, or check the error below.
          </p>
          <details open style={{ marginBottom: "1.5rem" }}>
            <summary
              style={{
                cursor: "pointer",
                fontWeight: 600,
                color: "#1F3A5F",
                userSelect: "none",
              }}
            >
              Error details
            </summary>
            <pre
              style={{
                marginTop: "0.75rem",
                padding: "1rem",
                backgroundColor: "#F2EFE7",
                borderRadius: 6,
                fontSize: "0.8rem",
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                color: "#15181D",
              }}
            >
              {error?.toString()}
              {"\n\nComponent stack:"}
              {info?.componentStack}
            </pre>
          </details>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: "0.6rem 1.4rem",
              backgroundColor: "#1F3A5F",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: "0.95rem",
              fontWeight: 600,
            }}
          >
            Reload Page
          </button>
        </div>
      </div>
    );
  }
}
