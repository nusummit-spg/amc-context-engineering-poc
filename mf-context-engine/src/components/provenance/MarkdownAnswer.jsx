import React from "react";
import CitationMark from "./CitationMark";
import MetricMark from "./MetricMark";
import "./MarkdownAnswer.css";

/**
 * Compact, robust Markdown Parser & Renderer for ContextGraph LLM responses.
 * - Formats full Markdown tables as tightly structured HTML <table> elements
 * - Preserves inline table cell structure (no broken <p> tags or multiline splits)
 * - Embeds interactive <CitationMark /> and <MetricMark /> components seamlessly inline
 * - Eliminates excessive vertical whitespace between blocks, rows, and citations
 */
export default function MarkdownAnswer({ text = "", citations = [], metrics = [] }) {
  if (!text) return null;

  // 1. Build lookup dictionaries
  const citationMap = {};
  if (Array.isArray(citations)) {
    citations.forEach((c, idx) => {
      const marker = c.marker || String(idx + 1);
      citationMap[marker] = c;
    });
  }

  const metricMap = {};
  if (Array.isArray(metrics)) {
    metrics.forEach((m, idx) => {
      const marker = m.marker || `m${idx + 1}`;
      metricMap[marker] = m;
      if (m.surface_text) {
        metricMap[m.surface_text.toLowerCase().trim()] = m;
      }
    });
  }

  // 2. Helper to parse inline tokens within any text chunk (paragraph, cell, list item)
  const renderInlineContent = (rawText, keyPrefix = "inline") => {
    if (!rawText) return null;

    // Token regex matches:
    // 1. [[cite:marker]]
    // 2. [[metric:marker|display]] or [[metric:marker]]
    // 3. [1], [16] standard bracket citations
    // 4. `code`
    // 5. **bold**
    // 6. *italic*
    const tokenRegex = /(\[\[cite:([a-zA-Z0-9_-]+)\]\]|\[\[metric:([a-zA-Z0-9_-]+)(?:\|([^\]]+))?\]\]|\[(\d{1,3})\]|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*)/g;

    const parts = rawText.split(tokenRegex);
    const elements = [];
    let pIdx = 0;

    for (let i = 0; i < parts.length; i++) {
      const chunk = parts[i];
      if (chunk === undefined || chunk === null) continue;

      // 1. [[cite:X]]
      if (chunk.startsWith("[[cite:")) {
        const marker = parts[i + 1];
        elements.push(
          <CitationMark key={`${keyPrefix}-c-${pIdx++}`} marker={marker} citation={citationMap[marker]} />
        );
        i += 1;
        continue;
      }

      // 2. [[metric:mX|display]]
      if (chunk.startsWith("[[metric:")) {
        const mId = parts[i + 2];
        const disp = parts[i + 3] || mId;
        const mData = metricMap[mId] || metricMap[disp.toLowerCase().trim()];
        elements.push(
          <MetricMark key={`${keyPrefix}-m-${pIdx++}`} metric={mData}>
            {disp}
          </MetricMark>
        );
        i += 3;
        continue;
      }

      // 3. [N] bracket citation
      if (/^\[\d{1,3}\]$/.test(chunk)) {
        const marker = parts[i + 4] || chunk.replace(/[[\]]/g, "");
        elements.push(
          <CitationMark key={`${keyPrefix}-nc-${pIdx++}`} marker={marker} citation={citationMap[marker]} />
        );
        i += 4;
        continue;
      }

      // 4. `code`
      if (chunk.startsWith("`") && chunk.endsWith("`") && chunk.length > 1) {
        const codeText = parts[i + 5] || chunk.slice(1, -1);
        elements.push(
          <code key={`${keyPrefix}-cd-${pIdx++}`} className="mf-inline-code">
            {codeText}
          </code>
        );
        i += 5;
        continue;
      }

      // 5. **bold**
      if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 3) {
        const boldText = parts[i + 6] || chunk.slice(2, -2);
        elements.push(
          <strong key={`${keyPrefix}-b-${pIdx++}`}>
            {renderInlineContent(boldText, `${keyPrefix}-b-${pIdx}`)}
          </strong>
        );
        i += 6;
        continue;
      }

      // 6. *italic*
      if (chunk.startsWith("*") && chunk.endsWith("*") && chunk.length > 1 && !chunk.startsWith("**")) {
        const italText = parts[i + 7] || chunk.slice(1, -1);
        elements.push(
          <em key={`${keyPrefix}-it-${pIdx++}`}>
            {renderInlineContent(italText, `${keyPrefix}-it-${pIdx}`)}
          </em>
        );
        i += 7;
        continue;
      }

      // Plain text chunk: auto-detect metrics if defined
      if (chunk) {
        if (metrics.length > 0) {
          let subSegments = [chunk];
          metrics.forEach((m) => {
            if (!m.surface_text) return;
            const escaped = m.surface_text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const mRegex = new RegExp(`(${escaped})`, "gi");
            const nextSubs = [];
            subSegments.forEach((sub) => {
              if (typeof sub === "string") {
                const subParts = sub.split(mRegex);
                subParts.forEach((sp) => {
                  if (sp.toLowerCase() === m.surface_text.toLowerCase()) {
                    nextSubs.push({ __isMetric: true, metric: m, text: sp });
                  } else if (sp) {
                    nextSubs.push(sp);
                  }
                });
              } else {
                nextSubs.push(sub);
              }
            });
            subSegments = nextSubs;
          });

          subSegments.forEach((sub) => {
            if (typeof sub === "string") {
              elements.push(<span key={`${keyPrefix}-t-${pIdx++}`}>{sub}</span>);
            } else if (sub.__isMetric) {
              elements.push(
                <MetricMark key={`${keyPrefix}-m-auto-${pIdx++}`} metric={sub.metric}>
                  {sub.text}
                </MetricMark>
              );
            }
          });
        } else {
          elements.push(<span key={`${keyPrefix}-t-${pIdx++}`}>{chunk}</span>);
        }
      }
    }

    return elements;
  };

  // 3. Block-level parsing (Tables, Lists, Headings, Paragraphs)
  const lines = text.split("\n");
  const blocks = [];
  let currentTable = null;
  let currentList = null;
  let currentParagraph = [];

  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      const pText = currentParagraph.join(" ").trim();
      if (pText) {
        blocks.push({
          type: "paragraph",
          content: pText,
        });
      }
      currentParagraph = [];
    }
  };

  const flushTable = () => {
    if (currentTable) {
      blocks.push(currentTable);
      currentTable = null;
    }
  };

  const flushList = () => {
    if (currentList) {
      blocks.push(currentList);
      currentList = null;
    }
  };

  const isTableRow = (line) => {
    const trimmed = line.trim();
    return trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.length > 2;
  };

  const isTableSeparator = (line) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return false;
    const inner = trimmed.slice(1, -1).replace(/\s+/g, "");
    return /^[-:|]+$/.test(inner);
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    // Check for Table Row
    if (isTableRow(trimmed)) {
      flushParagraph();
      flushList();

      if (!currentTable) {
        // First row of table -> headers
        const cells = trimmed
          .slice(1, -1)
          .split("|")
          .map((c) => c.trim());
        currentTable = {
          type: "table",
          headers: cells,
          rows: [],
        };
      } else if (isTableSeparator(trimmed)) {
        // Separator row (e.g. |---|---|) -> ignore / mark header confirmed
        continue;
      } else {
        // Data row
        const cells = trimmed
          .slice(1, -1)
          .split("|")
          .map((c) => c.trim());
        currentTable.rows.push(cells);
      }
      continue;
    } else {
      flushTable();
    }

    // Check for Empty line
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    // Check for Headings (#, ##, ###, ####)
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      blocks.push({
        type: "heading",
        level,
        content: headingMatch[2],
      });
      continue;
    }

    // Check for Bullet List (- or *)
    const bulletMatch = trimmed.match(/^[-*•]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      if (!currentList || currentList.listType !== "ul") {
        flushList();
        currentList = { type: "list", listType: "ul", items: [] };
      }
      currentList.items.push(bulletMatch[1]);
      continue;
    }

    // Check for Numbered List (1. 2. etc.)
    const numMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (numMatch) {
      flushParagraph();
      if (!currentList || currentList.listType !== "ol") {
        flushList();
        currentList = { type: "list", listType: "ol", items: [] };
      }
      currentList.items.push(numMatch[2]);
      continue;
    }

    // Regular line in paragraph
    currentParagraph.push(rawLine);
  }

  flushParagraph();
  flushTable();
  flushList();

  // 4. Render Blocks
  return (
    <div className="mf-answer-prose">
      {blocks.map((b, bIdx) => {
        if (b.type === "paragraph") {
          return (
            <p key={`p-${bIdx}`} className="mf-prose-p">
              {renderInlineContent(b.content, `p-${bIdx}`)}
            </p>
          );
        }

        if (b.type === "heading") {
          const Tag = `h${Math.min(b.level + 1, 6)}`;
          return (
            <Tag key={`h-${bIdx}`} className={`mf-prose-h mf-prose-h${b.level}`}>
              {renderInlineContent(b.content, `h-${bIdx}`)}
            </Tag>
          );
        }

        if (b.type === "table") {
          return (
            <div key={`tbl-wrap-${bIdx}`} className="mf-prose-table-container">
              <table className="mf-prose-table">
                <thead>
                  <tr>
                    {b.headers.map((h, hIdx) => (
                      <th key={`th-${hIdx}`} className="mf-prose-th">
                        {renderInlineContent(h, `th-${bIdx}-${hIdx}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {b.rows.map((row, rIdx) => (
                    <tr key={`tr-${rIdx}`} className="mf-prose-tr">
                      {row.map((cell, cIdx) => (
                        <td key={`td-${cIdx}`} className="mf-prose-td">
                          {renderInlineContent(cell, `td-${bIdx}-${rIdx}-${cIdx}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (b.type === "list") {
          const ListTag = b.listType === "ol" ? "ol" : "ul";
          return (
            <ListTag key={`lst-${bIdx}`} className={`mf-prose-${b.listType}`}>
              {b.items.map((it, itIdx) => (
                <li key={`li-${itIdx}`} className="mf-prose-li">
                  {renderInlineContent(it, `li-${bIdx}-${itIdx}`)}
                </li>
              ))}
            </ListTag>
          );
        }

        return null;
      })}
    </div>
  );
}
