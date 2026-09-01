export default function TextInput({ value, onChange, placeholder, label, labelVisible = true, disabled }) {
  return (
    <div className="stTextInput">
      {labelVisible && label && <div className="stSelectbox-label">{label}</div>}
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange && onChange(e.target.value)}
      />
    </div>
  );
}
