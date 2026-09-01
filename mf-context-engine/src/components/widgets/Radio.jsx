export default function Radio({ options, value, onChange, name }) {
  return (
    <div className="stRadioRow">
      {options.map((opt) => (
        <label className="stRadioOpt" key={opt}>
          <input
            type="radio"
            name={name}
            checked={value === opt}
            onChange={() => onChange(opt)}
          />
          {opt}
        </label>
      ))}
    </div>
  );
}
