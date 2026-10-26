import AutoGrowTextarea from "../widgets/AutoGrowTextarea";

/**
 * Free-text commentary input + Submit button row.
 * Reuses the styling convention of the main query follow-up bar.
 */
export default function FeedbackInputRow({
  freeText,
  setFreeText,
  canSubmit,
  submitState,
  disabled = false,
  onSubmit,
}) {
  const isSubmitting = submitState === "submitting";
  const isDisabled = disabled || isSubmitting;

  const handleSubmitKey = () => {
    if (canSubmit && !isDisabled) onSubmit();
  };

  return (
    <div className={`cg-feedback-input-row ${disabled ? "cg-feedback-input-row--disabled" : ""}`}>
      <div className="cg-feedback-input-wrap">
        <AutoGrowTextarea
          className="cg-feedback-input"
          placeholder={disabled ? "Feedback is closed for previous turns" : "Add your comments on this answer…"}
          value={freeText}
          onChange={setFreeText}
          onSubmit={handleSubmitKey}
          maxRows={6}
          maxLength={2000}
          disabled={isDisabled}
        />
        {freeText.length > 1800 && (
          <span className="cg-feedback-char-count">
            {2000 - freeText.length} left
          </span>
        )}
      </div>
      <button
        type="button"
        className="cg-feedback-submit-btn"
        disabled={!canSubmit || isDisabled}
        onClick={onSubmit}
      >
        {isSubmitting ? (
          <>
            <span className="cg-feedback-spinner" /> Submitting…
          </>
        ) : (
          "Submit"
        )}
      </button>
    </div>
  );
}
