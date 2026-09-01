import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import "./Tooltip.css";

/**
 * Robust floating portal tooltip component.
 * - Renders directly into document.body to bypass all overflow / width constraints
 * - Fixed viewport positioning with boundary safety and intelligent flip (top/bottom)
 * - Horizontal centering clamped within viewport margins
 * - Hover & focus persistence (allows moving cursor over tooltip to click links/scroll)
 */
export default function Tooltip({
  content,
  children,
  placement = "top",
  maxWidth = 440,
  minWidth = 320,
  delay = 100,
}) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, effectivePlacement: placement });
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);
  const timerRef = useRef(null);
  const hideTimerRef = useRef(null);

  const calculatePosition = useCallback(() => {
    if (!triggerRef.current) return;

    const rect = triggerRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;

    // Check vertical space
    const spaceAbove = rect.top;
    const spaceBelow = viewportHeight - rect.bottom;
    
    // Choose effective placement based on available vertical space
    let effective = placement;
    if (placement === "top" && spaceAbove < 200 && spaceBelow > spaceAbove) {
      effective = "bottom";
    } else if (placement === "bottom" && spaceBelow < 200 && spaceAbove > spaceBelow) {
      effective = "top";
    }

    // Determine target width
    const targetWidth = Math.min(maxWidth, Math.max(minWidth, viewportWidth - 32));
    const halfWidth = targetWidth / 2;

    // Center horizontally over the trigger element
    const triggerCenterX = rect.left + rect.width / 2;
    // Clamp so the popover remains strictly within viewport with 16px margin
    const clampedLeft = Math.max(halfWidth + 16, Math.min(triggerCenterX, viewportWidth - halfWidth - 16));

    // Determine vertical coordinate (position: fixed relative to viewport)
    let top = 0;
    if (effective === "top") {
      top = rect.top - 8;
    } else {
      top = rect.bottom + 8;
    }

    setCoords({
      top,
      left: clampedLeft,
      effectivePlacement: effective,
    });
  }, [placement, maxWidth, minWidth]);

  const show = useCallback(() => {
    clearTimeout(hideTimerRef.current);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      calculatePosition();
      setVisible(true);
    }, delay);
  }, [calculatePosition, delay]);

  const hide = useCallback(() => {
    clearTimeout(timerRef.current);
    clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      setVisible(false);
    }, 120);
  }, []);

  const handleKeyDown = useCallback((e) => {
    if (e.key === "Escape") {
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      calculatePosition();
      const onScrollOrResize = () => {
        calculatePosition();
      };
      window.addEventListener("scroll", onScrollOrResize, true);
      window.addEventListener("resize", onScrollOrResize);
      return () => {
        window.removeEventListener("scroll", onScrollOrResize, true);
        window.removeEventListener("resize", onScrollOrResize);
      };
    }
  }, [visible, calculatePosition]);

  useEffect(() => {
    return () => {
      clearTimeout(timerRef.current);
      clearTimeout(hideTimerRef.current);
    };
  }, []);

  const tooltipElement = visible && content ? (
    <div
      ref={tooltipRef}
      role="tooltip"
      className={`mf-tooltip-portal mf-tooltip-${coords.effectivePlacement}`}
      style={{
        position: "fixed",
        top: `${coords.top}px`,
        left: `${coords.left}px`,
        transform: coords.effectivePlacement === "top" ? "translate(-50%, -100%)" : "translate(-50%, 0)",
        minWidth: `${minWidth}px`,
        maxWidth: `${maxWidth}px`,
      }}
      onMouseEnter={() => {
        clearTimeout(hideTimerRef.current);
      }}
      onMouseLeave={hide}
    >
      <div className="mf-tooltip-inner">
        {content}
      </div>
      <div className={`mf-tooltip-arrow mf-tooltip-arrow--${coords.effectivePlacement}`} />
    </div>
  ) : null;

  return (
    <>
      <span
        ref={triggerRef}
        className="mf-tooltip-trigger"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        role="button"
        aria-expanded={visible}
      >
        {children}
      </span>
      {typeof document !== "undefined" && createPortal(tooltipElement, document.body)}
    </>
  );
}
