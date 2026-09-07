import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * Shared centered-overlay card used by the Ontology View, Evidence, and
 * Feedback response actions. `size` picks a width/height preset in CSS.
 */
export default function ModalCard({ open, onClose, title, icon, query, size = "md", children }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="cg-modal-overlay" onClick={onClose}>
      <div
        className={`cg-modal-card cg-modal-card--${size}`}
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cg-modal-head">
          <div className="cg-modal-head-title">
            {icon}
            {title}
          </div>
          <button type="button" className="cg-modal-close-btn" onClick={onClose} aria-label={`Close ${title}`}>
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        {query && (
          <div className="cg-modal-query" title={query}>
            &ldquo;{query}&rdquo;
          </div>
        )}

        <div className="cg-modal-body">{children}</div>
      </div>
    </div>
  );
}
