import { useEffect, useRef } from "react";

/**
 * StreamingAnswer — renders the accumulating answer text with a blinking caret
 * while the stream is open. The Stop control lives in the chat's send button,
 * so this component only draws the text.
 *
 * Props:
 *   content     {string}  The accumulated answer text so far
 *   isStreaming {boolean} Whether the stream is still active (controls the caret)
 */
export default function StreamingAnswer({ content = "", isStreaming = false }) {
  const bottomRef = useRef(null);

  // Keep the newest text in view while it is still arriving
  useEffect(() => {
    if (isStreaming && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [content, isStreaming]);

  return (
    <div className="cg-stream">
      <div className="cg-stream-text">
        {content}
        {isStreaming && <span className="cg-stream-cursor" aria-hidden="true" />}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
