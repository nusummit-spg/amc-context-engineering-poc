export default function Spinner({ text }) {
  return (
    <div className="stSpinnerRow">
      <span className="stSpinnerDot" />
      <span>{text}</span>
    </div>
  );
}
