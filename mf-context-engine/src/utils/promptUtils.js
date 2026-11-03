/**
 * Safely extracts query/prompt text from different content representations.
 */
export function getPromptText(content) {
  if (typeof content === "string") return content;
  if (!content) return "";
  return content.text || content.query || JSON.stringify(content) || "";
}

/**
 * Copies text to the clipboard with fallback support.
 */
export async function copyTextToClipboard(text) {
  if (!text) return false;
  try {
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    if (typeof document !== "undefined") {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const successful = document.execCommand("copy");
      document.body.removeChild(textarea);
      return successful;
    }
    return false;
  } catch {
    return false;
  }
}
