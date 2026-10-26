import { useRef, useState } from "react";
import { UploadCloud, FileText, X } from "lucide-react";

export default function FileUploader({ label, types, onChange }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const pick = (f) => {
    setFile(f);
    onChange && onChange(f);
  };

  return (
    <div>
      {label && <div className="stSelectbox-label">{label}</div>}
      <div
        className={`stFileUploader ${dragOver ? "stFileUploader--dragover" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) pick(f);
        }}
      >
        <div className="stFileUploader-drop">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <UploadCloud size={22} strokeWidth={1.5} style={{ color: "var(--color-ink-400)", flexShrink: 0 }} />
            <div>
              <div>Drag and drop file here</div>
              <div className="stFileUploader-hint">
                Limit 200MB per file{types ? ` • ${types.join(", ").toUpperCase()}` : ""}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="stFileUploader-browse"
            onClick={() => inputRef.current?.click()}
          >
            Browse files
          </button>
          <input
            ref={inputRef}
            type="file"
            style={{ display: "none" }}
            accept={types ? types.map((t) => "." + t).join(",") : undefined}
            onChange={(e) => pick(e.target.files?.[0] || null)}
          />
        </div>
        {file && (
          <div className="stFileUploader-fileitem">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <FileText size={14} strokeWidth={1.75} />
              {file.name}
            </span>
            <button
              type="button"
              className="stFileUploader-browse"
              onClick={() => pick(null)}
              aria-label="Remove file"
            >
              <X size={13} strokeWidth={1.75} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
