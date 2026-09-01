import { useRef, useState } from "react";

export default function FileUploader({ label, types, onChange }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);

  const pick = (f) => {
    setFile(f);
    onChange && onChange(f);
  };

  return (
    <div>
      {label && <div className="stSelectbox-label">{label}</div>}
      <div className="stFileUploader">
        <div className="stFileUploader-drop">
          <div>
            <div>Drag and drop file here</div>
            <div className="stFileUploader-hint">
              Limit 200MB per file{types ? ` • ${types.join(", ").toUpperCase()}` : ""}
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
            <span>📄 {file.name}</span>
            <button
              type="button"
              className="stFileUploader-browse"
              onClick={() => pick(null)}
            >
              ✕
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
