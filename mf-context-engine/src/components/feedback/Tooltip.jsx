import { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { createPortal } from "react-dom";

const GAP = 8;
const EDGE = 8;

/**
 * Reusable hover and keyboard-focus tooltip popover.
 *
 * Rendered in a portal with fixed positioning so it is never clipped by a
 * scrolling ancestor (the feedback modal body, for one), and flips below the
 * trigger when there is not enough room above it.
 */
export default function Tooltip({ text, id, children, maxWidth = 320 }) {
  const [isVisible, setIsVisible] = useState(false);
  const [pos, setPos] = useState(null);
  const wrapperRef = useRef(null);
  const popoverRef = useRef(null);
  const timerRef = useRef(null);

  const showTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setIsVisible(true), 120);
  };

  const hideTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setIsVisible(false);
      setPos(null);
    }, 100);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const position = useCallback(() => {
    const trigger = wrapperRef.current?.getBoundingClientRect();
    const pop = popoverRef.current?.getBoundingClientRect();
    if (!trigger || !pop) return;

    // Prefer below: above would float over whatever card or header sits on top
    // of the trigger, which reads as a rendering glitch rather than a tooltip.
    const fitsBelow = trigger.bottom + pop.height + GAP <= window.innerHeight - EDGE;
    const fitsAbove = !fitsBelow && trigger.top - pop.height - GAP >= EDGE;
    const top = fitsAbove ? trigger.top - pop.height - GAP : trigger.bottom + GAP;
    const left = Math.max(
      EDGE,
      Math.min(trigger.left + trigger.width / 2 - pop.width / 2, window.innerWidth - pop.width - EDGE)
    );
    setPos({ top, left, placement: fitsAbove ? "top" : "bottom", anchorX: trigger.left + trigger.width / 2 });
  }, []);

  useLayoutEffect(() => {
    if (!isVisible) return undefined;
    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return () => {
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }, [isVisible, text, position]);

  return (
    <div
      ref={wrapperRef}
      className="cg-tooltip-wrapper"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {isVisible &&
        text &&
        createPortal(
          <div
            ref={popoverRef}
            id={id}
            role="tooltip"
            className={`cg-tooltip-popover cg-tooltip-popover--${pos?.placement || "top"}`}
            style={{
              maxWidth,
              top: pos ? pos.top : 0,
              left: pos ? pos.left : 0,
              visibility: pos ? "visible" : "hidden",
            }}
          >
            <div
              className="cg-tooltip-arrow"
              style={pos ? { left: Math.max(10, Math.min(pos.anchorX - pos.left, maxWidth - 10)) } : undefined}
            />
            <div className="cg-tooltip-body">{text}</div>
          </div>,
          document.body
        )}
    </div>
  );
}
