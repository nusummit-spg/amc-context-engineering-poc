import { forwardRef, useImperativeHandle, useLayoutEffect, useRef } from "react";

/**
 * Single-line-looking textarea that grows with its content.
 * Enter submits, Shift+Enter inserts a newline; past `maxRows` it scrolls.
 */
const AutoGrowTextarea = forwardRef(function AutoGrowTextarea(
  { value, onChange, onSubmit, maxRows = 8, className = "", ...props },
  forwardedRef
) {
  const ref = useRef(null);
  useImperativeHandle(forwardedRef, () => ref.current, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const styles = getComputedStyle(el);
    const lineHeight = parseFloat(styles.lineHeight) || 20;
    const vPadding = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
    const max = lineHeight * maxRows + vPadding;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }, [value, maxRows]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit?.();
    }
    props.onKeyDown?.(e);
  };

  return (
    <textarea
      {...props}
      ref={ref}
      rows={1}
      className={className}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      onKeyDown={handleKeyDown}
    />
  );
});

export default AutoGrowTextarea;
