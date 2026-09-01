import { useState } from "react";

export default function Expander({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`stExpander ${open ? "open" : ""}`}>
      <div className="stExpander-header" onClick={() => setOpen((o) => !o)}>
        <span className="chevron">▶</span>
        <span>{title}</span>
      </div>
      {open && <div className="stExpander-body">{children}</div>}
    </div>
  );
}
