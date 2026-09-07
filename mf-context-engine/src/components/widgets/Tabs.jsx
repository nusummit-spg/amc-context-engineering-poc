export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="stTabs-list">
      {tabs.map((t, i) => {
        const isObj = typeof t === "object" && t !== null;
        const label = isObj ? t.label : t;
        const Icon = isObj ? t.icon : null;
        return (
          <button
            key={label}
            className="stTabs-tab"
            aria-selected={active === i}
            onClick={() => onChange(i)}
          >
            {Icon && <Icon size={16} strokeWidth={1.75} className="stTabs-tab-icon" />}
            {label}
          </button>
        );
      })}
    </div>
  );
}
