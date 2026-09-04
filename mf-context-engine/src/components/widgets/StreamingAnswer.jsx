import { useEffect, useRef } from "react";

/**
 * StreamingAnswer — renders markdown text with an animated blinking cursor.
 *
 * Props:
 *   content    {string}   The accumulated answer text so far
 *   isStreaming {boolean} Whether the stream is still active (controls cursor visibility)
 *   onStop     {Function} Optional callback for the Stop button (should abort the stream)
 */
export default function StreamingAnswer({ content = "", isStreaming = false, onStop }) {
  const bottomRef = useRef(null);

  // Auto-scroll to the latest content while streaming
  useEffect(() => {
    if (isStreaming && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [content, isStreaming]);

  return (
    <div className="streaming-answer" style={{ position: "relative" }}>
      {/* Render content as plain text — swap for <MarkdownRenderer> if available */}
      <div
        style={{
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "inherit",
          fontSize: "0.95rem",
          lineHeight: 1.6,
        }}
      >
        {content}
        {isStreaming && (
          <span
            className="cursor-blink"
            aria-hidden="true"
            style={{
              display: "inline-block",
              width: "0.6em",
              height: "1.1em",
              background: "currentColor",
              marginLeft: "2px",
              verticalAlign: "text-bottom",
              animation: "blink 1s step-end infinite",
            }}
          />
        )}
      </div>

      {/* Stop button — only shown while streaming */}
      {isStreaming && onStop && (
        <div style={{ marginTop: "0.5rem" }}>
          <button
            onClick={onStop}
            style={{
              fontSize: "0.8rem",
              padding: "0.2rem 0.7rem",
              cursor: "pointer",
              background: "transparent",
              border: "1px solid currentColor",
              borderRadius: "4px",
              opacity: 0.7,
            }}
            title="Stop generation"
          >
            Stop
          </button>
        </div>
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />

      {/* Keyframe animation injected once */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
