export default function Progress({ value, text }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="stProgressWrap">
      <div className="stProgressTrack">
        <div className="stProgressFill" style={{ width: `${pct}%` }} />
      </div>
      {text && <div className="stProgressText">{text}</div>}
    </div>
  );
}
