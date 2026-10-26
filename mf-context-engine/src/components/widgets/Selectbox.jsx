export default function Selectbox({ label, help, options, value, onChange, getLabel }) {
  return (
    <div className="stSelectbox">
      {label && (
        <div className="stSelectbox-label">
          {label}
          {help && (
            <span className="stHelpIcon">
              ?<span className="tooltip">{help}</span>
            </span>
          )}
        </div>
      )}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {getLabel ? getLabel(opt) : opt}
          </option>
        ))}
      </select>
    </div>
  );
}
