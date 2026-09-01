import { useState, useRef, useEffect } from "react";

/**
 * Reusable hover and keyboard-focus tooltip popover.
 * Supports debouncing (~150ms) to avoid flicker when moving across adjacent rows.
 */
export default function Tooltip({ text, id, children, maxWidth = 320 }) {
  const [isVisible, setIsVisible] = useState(false);
  const timerRef = useRef(null);

  const showTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setIsVisible(true);
    }, 120);
  };

  const hideTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setIsVisible(false);
    }, 100);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div
      className="cg-tooltip-wrapper"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {isVisible && text && (
        <div
          id={id}
          role="tooltip"
          className="cg-tooltip-popover"
          style={{ maxWidth }}
        >
          <div className="cg-tooltip-arrow" />
          <div className="cg-tooltip-body">{text}</div>
        </div>
      )}
    </div>
  );
}
