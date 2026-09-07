const SERIES_COLORS = ["#1F3A5F", "#C9BBA0", "#6B7280", "#3F6B42"];

export default function BarChart({ categories, labels, series = [], height = 260 }) {
  const cats = categories || labels || [];
  const normalizedSeries = (series || []).map((s) => ({
    name: s.name || "",
    values: s.values || s.data || [],
  }));
  const allValues = normalizedSeries.flatMap((s) => s.values || [0]);
  const max = Math.max(1, ...allValues);
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: "1.2rem",
          height,
          borderLeft: "1px solid rgba(49,51,63,0.15)",
          borderBottom: "1px solid rgba(49,51,63,0.15)",
          padding: "0.5rem 0.75rem 0 0.75rem",
          overflowX: "auto",
          WebkitOverflowScrolling: "touch",
        }}
      >
        {cats.map((cat, ci) => (
          <div key={ci} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 42 }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: height - 40 }}>
              {normalizedSeries.map((s, si) => (
                <div
                  key={si}
                  title={`${s.name}: ${s.values[ci] ?? 0}`}
                  style={{
                    width: 14,
                    height: `${Math.max(2, (((s.values[ci] ?? 0) / max) * (height - 40)))}px`,
                    background: SERIES_COLORS[si % SERIES_COLORS.length],
                    borderRadius: "2px 2px 0 0",
                  }}
                />
              ))}
            </div>
            <div
              style={{
                fontSize: 10,
                color: "rgba(49,51,63,0.55)",
                marginTop: 4,
                width: 46,
                textAlign: "center",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={cat}
            >
              {cat}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 1rem", marginTop: 8 }}>
        {normalizedSeries.map((s, si) => (
          <div key={si} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#5C574C" }}>
            <span style={{ width: 10, height: 10, background: SERIES_COLORS[si % SERIES_COLORS.length], display: "inline-block", borderRadius: 2 }} />
            {s.name}
          </div>
        ))}
      </div>
    </div>
  );
}
