const SERIES_COLORS = ["var(--color-navy-700)", "var(--color-gold-500)", "var(--color-ink-500)", "var(--color-success-text)"];
const AXIS_LABEL_SPACE = 40;

export default function BarChart({ categories, labels, series = [], height = 260 }) {
  const cats = categories || labels || [];
  const normalizedSeries = (series || []).map((s) => ({
    name: s.name || "",
    values: s.values || s.data || [],
  }));
  const allValues = normalizedSeries.flatMap((s) => s.values || [0]);
  const max = Math.max(1, ...allValues);
  const plotHeight = height - AXIS_LABEL_SPACE;

  return (
    <div>
      <div className="stBarChart" style={{ height }} role="img" aria-label={`Bar chart with ${cats.length} categories`}>
        {cats.map((cat, ci) => (
          <div key={ci} className="stBarChart-col">
            <div className="stBarChart-bars" style={{ height: plotHeight }}>
              {normalizedSeries.map((s, si) => {
                const v = s.values[ci] ?? 0;
                return (
                  <div
                    key={si}
                    className="stBarChart-bar"
                    title={`${s.name}: ${v}`}
                    style={{
                      height: `${Math.max(2, (v / max) * plotHeight)}px`,
                      background: SERIES_COLORS[si % SERIES_COLORS.length],
                      animationDelay: `${ci * 40}ms`,
                    }}
                  />
                );
              })}
            </div>
            <div className="stBarChart-cat" title={cat}>
              {cat}
            </div>
          </div>
        ))}
      </div>
      <div className="stBarChart-legend">
        {normalizedSeries.map((s, si) => (
          <div key={si} className="stBarChart-legend-item">
            <span className="stBarChart-swatch" style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }} />
            {s.name}
          </div>
        ))}
      </div>
    </div>
  );
}
