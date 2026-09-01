export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="stTabs-list">
      {tabs.map((t, i) => (
        <button
          key={t}
          className="stTabs-tab"
          aria-selected={active === i}
          onClick={() => onChange(i)}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
