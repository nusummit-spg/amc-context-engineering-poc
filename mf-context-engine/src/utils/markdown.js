// Minimal markdown->HTML for LLM-generated answers, mirrors compare_view.py's
// _markdown_to_html: headers, bold, italics, paragraphs only.
export function markdownToHtml(text) {
  if (!text) return "";
  if (typeof text === "object") {
    text = text.answer || text.text || text.content || JSON.stringify(text);
  }
  let out = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  out = out.replace(/^#{1,6}\s*(.+)$/gm, "<strong>$1</strong>");
  out = out.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  out = out.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<i>$1</i>");
  out = out.replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>");
  return `<p>${out}</p>`;
}
