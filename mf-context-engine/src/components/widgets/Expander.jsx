import { useState } from "react";
import { ChevronRight } from "lucide-react";

export default function Expander({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`stExpander ${open ? "open" : ""}`}>
      <div className="stExpander-header" onClick={() => setOpen((o) => !o)}>
        <span className="chevron"><ChevronRight size={14} strokeWidth={1.75} /></span>
        <span>{title}</span>
      </div>
      {open && <div className="stExpander-body">{children}</div>}
    </div>
  );
}
