import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { getPromptText, copyTextToClipboard } from "../../utils/promptUtils";

export default function UserMessage({ content, timestamp }) {
  const [copied, setCopied] = useState(false);

  const queryText = getPromptText(content);

  const handleCopy = async () => {
    if (!queryText) return;
    const ok = await copyTextToClipboard(queryText);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    }
  };

  const formattedTime =
    timestamp && !isNaN(new Date(timestamp).getTime())
      ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : null;

  return (
    <div className="cg-msg-user-container">
      <div className="cg-msg-user">{queryText}</div>
      <div className="cg-msg-user-actions">
        {formattedTime && (
          <time className="cg-msg-user-time" dateTime={new Date(timestamp).toISOString()}>
            {formattedTime}
          </time>
        )}
        <button
          type="button"
          className={`cg-msg-user-action-btn ${copied ? "cg-msg-user-action-btn--copied" : ""}`}
          onClick={handleCopy}
          title={copied ? "Copied to clipboard" : "Copy prompt"}
          aria-label={copied ? "Copied to clipboard" : "Copy prompt"}
        >
          {copied ? <Check size={12} strokeWidth={2} /> : <Copy size={12} strokeWidth={1.75} />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
    </div>
  );
}
