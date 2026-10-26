import Tooltip from "./Tooltip";

/**
 * Checkbox for one failure-taxonomy category (F01–F12).
 * The entire row is interactive and triggers the tooltip on hover and keyboard focus.
 */
export default function FailureCheckbox({ category, checked, onChange, disabled = false }) {
  const tooltipId = `tooltip-${category.code}`;

  return (
    <Tooltip text={category.tooltip} id={tooltipId}>
      <label className={`cg-failure-checkbox-row ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}`}>
        <input
          type="checkbox"
          className="cg-failure-checkbox-input"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(category.code, e.target.checked)}
          aria-describedby={tooltipId}
        />
        <span className="cg-failure-checkbox-code">{category.code}</span>
        <span className="cg-failure-checkbox-label">{category.label}</span>
        <span className="cg-failure-checkbox-info" title="Hover or focus for description">ⓘ</span>
      </label>
    </Tooltip>
  );
}
