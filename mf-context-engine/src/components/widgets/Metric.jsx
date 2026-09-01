export default function Metric({ label, value, delta, deltaColor = "normal" }) {
  let deltaClass = "";
  let arrow = "";
  if (delta) {
    const isDown = delta.trim().startsWith("-");
    const isUp = delta.trim().startsWith("+");
    arrow = isDown ? "▼" : isUp ? "▲" : "";
    if (deltaColor === "inverse") {
      deltaClass = isDown ? "inverse-down" : "inverse-up";
    } else {
      deltaClass = isDown ? "down" : "up";
    }
  }
  return (
    <div className="stMetric">
      <div className="stMetric-label">{label}</div>
      <div className="stMetric-value">{value}</div>
      {delta && (
        <div className={`stMetric-delta ${deltaClass}`}>
          {arrow} {delta.replace(/^[+-]/, "")}
        </div>
      )}
    </div>
  );
}
