import React from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import CitationMark from "./CitationMark";
import MetricMark from "./MetricMark";
import "./MarkdownAnswer.css";

/**
 * Clickable inline badge/pill for downloading CSV files directly to the user's local machine.
 */
export function CsvDownloadPill({ filename, url, children }) {
  const cleanName = (filename || "")
    .trim()
    .replace(/^(&lt;|<|`|\*|")+|(&gt;|>|`|\*|")+$/g, "")
    .replace(/^[(\s]+|[)\s.,:;]+$/g, "");

  const baseFilename = cleanName.split("/").pop() || cleanName;
  const targetUrl = url || `/api/files/${encodeURIComponent(cleanName)}?download=true`;

  return (
    <a
      href={targetUrl}
      download={baseFilename}
      className="mf-csv-download-pill"
      title={`Download ${baseFilename} to your local system`}
      onClick={(e) => {
        e.stopPropagation();
      }}
    >
      <FileSpreadsheet className="mf-csv-pill-icon" size={13} strokeWidth={2} />
      <span className="mf-csv-pill-text">{children || cleanName}</span>
      <Download className="mf-csv-pill-dl-icon" size={12} strokeWidth={2.2} />
    </a>
  );
}

/**
 * Compact, robust Markdown Parser & Renderer for ContextGraph LLM responses.
 * - Formats full Markdown tables as tightly structured HTML <table> elements
 * - Preserves inline table cell structure (no broken <p> tags or multiline splits)
 * - Embeds interactive <CitationMark /> and <MetricMark /> components seamlessly inline
 * - Eliminates excessive vertical whitespace between blocks, rows, and citations
 */
export default function MarkdownAnswer({ text = "", citations = [], metrics = [] }) {
  if (!text) return null;

  let cleanText = typeof text === "string" ? text : "";
  if (!cleanText.trim()) return null;

  // 1. Strip outer markdown or code fences (e.g. ```markdown ... ``` or ``` ... ```)
  cleanText = cleanText.trim();
  const fenceMatch = cleanText.match(/^```(?:markdown|html|md)?\s*\r?\n([\s\S]*?)\r?\n```$/);
  if (fenceMatch) {
    cleanText = fenceMatch[1].trim();
  }

  // 2. Normalize HTML tables into Markdown tables if raw HTML table tags were returned
  if (/<table[\s>]/i.test(cleanText)) {
    cleanText = cleanText.replace(/<table[\s\S]*?<\/table>/gi, (tableHtml) => {
      try {
        const rows = [];
        const trMatches = tableHtml.match(/<tr[\s\S]*?<\/tr>/gi) || [];
        for (const tr of trMatches) {
          const cells = [];
          const cellMatches = tr.match(/<(?:td|th)[\s\S]*?<\/(?:td|th)>/gi) || [];
          for (const cell of cellMatches) {
            const inner = cell.replace(/<[^>]+>/g, "").trim().replace(/\|/g, "\\|");
            cells.push(inner);
          }
          if (cells.length > 0) {
            rows.push(cells);
          }
        }
        if (rows.length === 0) return tableHtml;
        const maxCols = Math.max(...rows.map((r) => r.length));
        const normalizedRows = rows.map((r) => {
          while (r.length < maxCols) r.push("");
          return `| ${r.join(" | ")} |`;
        });
        const separator = `| ${new Array(maxCols).fill("---").join(" | ")} |`;
        return "\n\n" + [normalizedRows[0], separator, ...normalizedRows.slice(1)].join("\n") + "\n\n";
      } catch (e) {
        return tableHtml;
      }
    });
  }

  // 3. Clean remaining raw HTML line breaks or paragraph tags
  cleanText = cleanText
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>\s*<p>/gi, "\n\n")
    .replace(/<\/?(?:p|div|span)[^>]*>/gi, "");

  // 4. Normalize comma-separated bracket citations (e.g. [1, 2] or [1,2,3]) into separate [1] [2] tokens
  cleanText = cleanText.replace(/\[(\d+(?:\s*,\s*\d+)+)\]/g, (_, nums) => {
    return nums.split(/\s*,\s*/).map((n) => `[${n}]`).join(" ");
  });

  // 1. Build lookup dictionaries
  const citationMap = {};
  if (Array.isArray(citations)) {
    citations.forEach((c, idx) => {
      const marker = c.marker || String(idx + 1);
      citationMap[marker] = c;
    });
  }

  const metricMap = {};
  const sortedMetrics = Array.isArray(metrics)
    ? [...metrics].sort((a, b) => (b.surface_text || "").length - (a.surface_text || "").length)
    : [];

  if (Array.isArray(metrics)) {
    metrics.forEach((m, idx) => {
      const marker = m.marker || `m${idx + 1}`;
      metricMap[marker] = m;
      if (m.surface_text) {
        metricMap[m.surface_text.toLowerCase().trim()] = m;
      }
    });
  }

  // 2. Helper to parse plain text chunks for CSV filenames and metrics
  const csvRegex = /(<[a-zA-Z0-9_.\-/]+\.csv>|&lt;[a-zA-Z0-9_.\-/]+\.csv&gt;|\b[a-zA-Z0-9_.\-/]+\.csv\b)/gi;

  const renderPlainTextChunk = (plainChunk, keyPrefix, startIdx) => {
    let pIdx = startIdx;
    const elements = [];
    if (!plainChunk) return { elements, nextIdx: pIdx };

    const csvParts = plainChunk.split(csvRegex);

    for (let c = 0; c < csvParts.length; c++) {
      const part = csvParts[c];
      if (!part) continue;

      const isCsv = csvRegex.test(part);
      csvRegex.lastIndex = 0;

      if (isCsv) {
        elements.push(
          <CsvDownloadPill key={`${keyPrefix}-csv-${pIdx++}`} filename={part} />
        );
      } else {
        // Handle metrics if present
        if (sortedMetrics.length > 0) {
          let subSegments = [part];
          sortedMetrics.forEach((m) => {
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
          elements.push(<span key={`${keyPrefix}-t-${pIdx++}`}>{part}</span>);
        }
      }
    }

    return { elements, nextIdx: pIdx };
  };

  // 3. Helper to parse inline tokens within any text chunk (paragraph, cell, list item)
  const renderInlineContent = (rawText, keyPrefix = "inline") => {
    if (!rawText) return null;

    // Token regex matches:
    // 1. [[cite:marker]]
    // 2. [[metric:marker|display]] or [[metric:marker]]
    // 3. [1], [16] standard bracket citations
    // 4. [text](url) markdown link
    // 5. <name.csv> or &lt;name.csv&gt; angle-bracket CSV
    // 6. `code`
    // 7. **bold**
    // 8. *italic*
    const tokenRegex = /(\[\[cite:[a-zA-Z0-9_-]+\]\]|\[\[metric:[a-zA-Z0-9_-]+(?:\|[^\]]+)?\]\]|\[\d{1,3}\]|\[[^\]]+\]\([^)]+\)|<[a-zA-Z0-9_.\-/]+\.csv>|&lt;[a-zA-Z0-9_.\-/]+\.csv&gt;|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;

    const parts = rawText.split(tokenRegex);
    const elements = [];
    let pIdx = 0;

    for (let i = 0; i < parts.length; i++) {
      const chunk = parts[i];
      if (chunk === undefined || chunk === null || chunk === "") continue;

      // 1. [[cite:X]]
      if (chunk.startsWith("[[cite:") && chunk.endsWith("]]")) {
        const marker = chunk.slice(7, -2);
        elements.push(
          <CitationMark key={`${keyPrefix}-c-${pIdx++}`} marker={marker} citation={citationMap[marker]} />
        );
        continue;
      }

      // 2. [[metric:mX|display]]
      if (chunk.startsWith("[[metric:") && chunk.endsWith("]]")) {
        const inner = chunk.slice(9, -2);
        const barIdx = inner.indexOf("|");
        const mId = barIdx !== -1 ? inner.slice(0, barIdx) : inner;
        const disp = barIdx !== -1 ? inner.slice(barIdx + 1) : mId;
        const mData = metricMap[mId] || metricMap[disp.toLowerCase().trim()];
        elements.push(
          <MetricMark key={`${keyPrefix}-m-${pIdx++}`} metric={mData}>
            {disp}
          </MetricMark>
        );
        continue;
      }

      // 3. [N] bracket citation
      if (/^\[\d{1,3}\]$/.test(chunk)) {
        const marker = chunk.replace(/[[\]]/g, "");
        elements.push(
          <CitationMark key={`${keyPrefix}-nc-${pIdx++}`} marker={marker} citation={citationMap[marker]} />
        );
        continue;
      }

      // 4. Markdown link [text](url)
      const linkMatch = chunk.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (linkMatch) {
        const linkText = linkMatch[1];
        const linkUrl = linkMatch[2];
        const isCsvLink =
          linkText.toLowerCase().endsWith(".csv") ||
          linkUrl.toLowerCase().includes(".csv") ||
          linkUrl.includes("download=true");

        if (isCsvLink) {
          elements.push(
            <CsvDownloadPill key={`${keyPrefix}-link-csv-${pIdx++}`} filename={linkText} url={linkUrl}>
              {linkText}
            </CsvDownloadPill>
          );
        } else {
          elements.push(
            <a
              key={`${keyPrefix}-link-${pIdx++}`}
              href={linkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mf-prose-link"
            >
              {linkText}
            </a>
          );
        }
        continue;
      }

      // 5. Angle-bracket CSV: <filename.csv> or &lt;filename.csv&gt;
      if (
        (chunk.startsWith("<") && chunk.endsWith(">") && chunk.toLowerCase().endsWith(".csv>")) ||
        (chunk.startsWith("&lt;") && chunk.endsWith("&gt;") && chunk.toLowerCase().endsWith(".csv&gt;"))
      ) {
        elements.push(
          <CsvDownloadPill key={`${keyPrefix}-ab-csv-${pIdx++}`} filename={chunk} />
        );
        continue;
      }

      // 6. `code`
      if (chunk.startsWith("`") && chunk.endsWith("`") && chunk.length > 1) {
        const codeText = chunk.slice(1, -1);
        if (codeText.trim().toLowerCase().endsWith(".csv")) {
          elements.push(
            <CsvDownloadPill key={`${keyPrefix}-code-csv-${pIdx++}`} filename={codeText.trim()} />
          );
        } else {
          elements.push(
            <code key={`${keyPrefix}-cd-${pIdx++}`} className="mf-inline-code">
              {codeText}
            </code>
          );
        }
        continue;
      }

      // 7. **bold**
      if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 3) {
        const boldText = chunk.slice(2, -2);
        if (boldText.trim().toLowerCase().endsWith(".csv")) {
          elements.push(
            <CsvDownloadPill key={`${keyPrefix}-b-csv-${pIdx++}`} filename={boldText.trim()} />
          );
        } else {
          elements.push(
            <strong key={`${keyPrefix}-b-${pIdx++}`}>
              {renderInlineContent(boldText, `${keyPrefix}-b-${pIdx}`)}
            </strong>
          );
        }
        continue;
      }

      // 8. *italic*
      if (chunk.startsWith("*") && chunk.endsWith("*") && chunk.length > 1 && !chunk.startsWith("**")) {
        const italText = chunk.slice(1, -1);
        if (italText.trim().toLowerCase().endsWith(".csv")) {
          elements.push(
            <CsvDownloadPill key={`${keyPrefix}-it-csv-${pIdx++}`} filename={italText.trim()} />
          );
        } else {
          elements.push(
            <em key={`${keyPrefix}-it-${pIdx++}`}>
              {renderInlineContent(italText, `${keyPrefix}-it-${pIdx}`)}
            </em>
          );
        }
        continue;
      }

      // 9. Plain text chunk: auto-detect plain CSV references and metrics
      const { elements: textElems, nextIdx } = renderPlainTextChunk(chunk, keyPrefix, pIdx);
      pIdx = nextIdx;
      elements.push(...textElems);
    }

    return elements;
  };

  // 3. Block-level parsing (Tables, Lists, Headings, Paragraphs)
  const lines = cleanText.split("\n");
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
