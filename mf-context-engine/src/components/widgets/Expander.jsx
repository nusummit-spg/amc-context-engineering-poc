import { useId, useState } from "react";
import { ChevronRight } from "lucide-react";

export default function Expander({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  return (
    <div className={`stExpander ${open ? "open" : ""}`}>
      <button
        type="button"
        className="stExpander-header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={bodyId}
      >
        <span className="chevron"><ChevronRight size={14} strokeWidth={1.75} /></span>
        <span>{title}</span>
      </button>
      {open && <div className="stExpander-body" id={bodyId}>{children}</div>}
    </div>
  );
}
