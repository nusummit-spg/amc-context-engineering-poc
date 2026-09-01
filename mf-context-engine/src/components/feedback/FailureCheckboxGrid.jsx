import { FAILURE_TAXONOMY } from "../../constants/failureTaxonomy";
import FailureCheckbox from "./FailureCheckbox";

/**
 * 2-column grid of all 12 failure taxonomy categories.
 */
export default function FailureCheckboxGrid({ selectedCodes, onChange, disabled = false }) {
  const isChecked = (code) => {
    if (selectedCodes instanceof Set) {
      return selectedCodes.has(code);
    }
    if (Array.isArray(selectedCodes)) {
      return selectedCodes.includes(code);
    }
    return false;
  };

  return (
    <div className="cg-failure-grid" role="group" aria-label="Failure Taxonomy Categories">
      {FAILURE_TAXONOMY.map((cat) => (
        <FailureCheckbox
          key={cat.code}
          category={cat}
          checked={isChecked(cat.code)}
          onChange={onChange}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
