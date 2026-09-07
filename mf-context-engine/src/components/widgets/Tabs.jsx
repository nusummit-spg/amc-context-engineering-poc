export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="stTabs-list" role="tablist">
      {tabs.map((t, i) => {
        const isObj = typeof t === "object" && t !== null;
        const label = isObj ? t.label : t;
        const Icon = isObj ? t.icon : null;
        const selected = active === i;
        return (
          <button
            key={label}
            type="button"
            role="tab"
            className="stTabs-tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") onChange((i + 1) % tabs.length);
              if (e.key === "ArrowLeft") onChange((i - 1 + tabs.length) % tabs.length);
            }}
          >
            {Icon && <Icon size={16} strokeWidth={1.75} className="stTabs-tab-icon" />}
            {label}
          </button>
        );
      })}
    </div>
  );
}
