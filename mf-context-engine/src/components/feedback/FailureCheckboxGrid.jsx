import { FAILURE_TAXONOMY } from "../../constants/failureTaxonomy";
import FailureCheckbox from "./FailureCheckbox";

/**
 * The 12 taxonomy codes grouped by what went wrong, so a reviewer scans one
 * short list instead of twelve flat options. Presentation only — the codes
 * submitted to the API are unchanged.
 */
const GROUPS = [
  { title: "Understanding the question", codes: ["F01", "F02", "F03"] },
  { title: "Sources & accuracy", codes: ["F04", "F05", "F06", "F07", "F08"] },
  { title: "Clarity & risk", codes: ["F09", "F10", "F11", "F12"] },
];

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

  const byCode = Object.fromEntries(FAILURE_TAXONOMY.map((c) => [c.code, c]));

  return (
    <div role="group" aria-label="Failure Taxonomy Categories">
      {GROUPS.map((group) => {
        const selectedInGroup = group.codes.filter(isChecked).length;
        return (
          <div key={group.title} className="cg-failure-group">
            <div className="cg-failure-group-title">
              {group.title}
              {selectedInGroup > 0 && (
                <span className="cg-failure-group-count">{selectedInGroup}</span>
              )}
            </div>
            <div className="cg-failure-grid">
              {group.codes.map((code) => {
                const cat = byCode[code];
                if (!cat) return null;
                return (
                  <FailureCheckbox
                    key={cat.code}
                    category={cat}
                    checked={isChecked(cat.code)}
                    onChange={onChange}
                    disabled={disabled}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
