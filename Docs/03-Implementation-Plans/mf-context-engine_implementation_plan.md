# Implementation Plan: Response Provenance, Citation/Metric Tooltips, and Sidebar Layout Fix
### Project: MF Context Engine (mf-context-engine) — Backend: Python | Frontend: React

---

## 0. Scope Summary (what "done" looks like)

| # | Requirement | Current state (from screenshots) | Target state |
|---|---|---|---|
| 1 | "Document Provenance & Exact Page Citations (n Sources)" block | Rendered as its own collapsible **table** sitting above/outside the chat response bubble | Merged into the response's own **"Sources"** section (the `[1] April 2025.pdf p.1 …` list already seen at the bottom of Image 1) |
| 2 | Column "Chunk ID / Clause" | Shows internal chunk id (`src.1`, `src.2`) | Shows **Page number** (`p. 16`, `p. 18`, …) |
| 3 | "Verbatim Text Snippet" column | Truncated single line, no way to see full text | Per-row **chevron (▾/▸) expand/collapse**, independent per source, revealing the **full verbatim text**, not the truncated preview |
| 4 | Inline citation markers (`[1]`, `[16]`, `[18]`) in the LLM prose | Plain bracketed numbers, not interactive | **Tooltip on hover/focus**, with a clickable redirect to the source (deep link to page/doc) when a URL/path is resolvable; falls back to a **description-only tooltip** when no redirect target exists |
| 5 | Inline **metrics** the LLM states (e.g. "20% of Net Assets", "6 months", "August 03, 2026") | Plain text, no way to know if it's a verbatim figure from a source or an LLM computation/inference | Same tooltip affordance as citations, but content explains **provenance of the number**: verbatim-from-source vs. computed/assumed, and if computed/assumed, **how** (formula, source values used, assumption stated) |
| 6 | Sidebar collapse | Collapsing the left sidebar breaks the width of the main content area (screenshot 3: content is edge-to-edge / overlapping, horizontal scrollbar appears) | Sidebar collapse/expand must **never** change the total viewport math incorrectly — content reflows correctly in both states |

This document is the implementation plan only (no repo was attached, so no code has been modified). It's written so it can be executed as-is against the `mf-context-engine` React app and its Python backend.

---

## 1. Root-cause analysis (before proposing fixes)

### 1.1 Why provenance is currently a separate block
Judging from Image 1 and Image 3, the backend is returning the LLM's answer and a **separate, independently-rendered provenance table** (probably a distinct JSON key like `citations` or `provenance`, rendered by a dedicated `<ProvenanceTable />` component that isn't aware of the `<Sources />` list rendered under "SOURCES" at the bottom of the same answer). Two components are drawing overlapping information:
- `SOURCES [1]..[5]` — light, doc+page only.
- `Document Provenance & Exact Page Citations (n Sources)` — heavy, includes chunk id + verbatim snippet.

These need to become **one single component with two density levels** (collapsed = `[n] Document.pdf — p.X`, expanded = full verbatim text), not two components.

### 1.2 Why "Chunk ID / Clause" instead of Page number
This is a data-availability problem, not just a rendering one. The retrieval layer stores `chunk_id` (an internal vector-store identifier) as the primary key for a retrieved passage. Page number is very likely present in the chunk's metadata already (Image 1's footer shows `p.16`, `p.18`, `p.1` — so the data **exists**, it's just not the field the provenance table is bound to). Fix is mostly a frontend binding change + a backend contract normalization to guarantee `page_number` is always populated (with a defined fallback when a source genuinely has no page, e.g. a scraped HTML circular).

### 1.3 Why the sidebar collapse breaks layout
Classic symptom: **main content width is computed as a hardcoded offset from a fixed sidebar width**, e.g.
```css
.app-shell { display: flex; }
.sidebar { width: 260px; flex-shrink: 0; }
.main-content { margin-left: 260px; width: calc(100% - 260px); }
```
When the sidebar collapses (via a `collapsed` class or conditional unmount), the sidebar's rendered width changes (or the sidebar unmounts) but `.main-content`'s `margin-left`/`width` calc **doesn't update because it isn't derived from the sidebar's actual runtime width** — it's a second, independently hardcoded value (or worse, the sidebar toggle only adds `display:none` without updating the flex sibling). That produces exactly what screenshot 3 shows: content pinned far left/right, a huge dead gutter, or content overflowing under a floating rail button. This is confirmed further by the fact that the visible chat UI in screenshot 3 is a **narrow strip** while the sidebar is collapsed to an icon rail behind an "Expand sidebar" tooltip — the content did not reflow to reclaim the freed space.

**This must be fixed at the layout-primitive level** (CSS Grid with a variable column, or Flexbox with `flex: 1 1 auto` + `min-width: 0` and no manually duplicated width math), not by patching the specific pixel numbers.

---

## 2. Backend (Python) — Data Contract Changes

### 2.1 New unified response schema
Define (Pydantic) models so the frontend never has to guess field names or reimplement truncation/expansion logic.

```python
# schemas/provenance.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

class SourceChunk(BaseModel):
    chunk_id: str                     # keep internally for debugging/telemetry, but NOT primary display field
    document_id: str                  # stable id, e.g. hash of file
    document_name: str                # "Categorization and Rationalization of Mutual Fund Schemes.pdf"
    page_number: Optional[int] = None # primary display field going forward
    page_label: Optional[str] = None  # e.g. "16" or "16-17" for multi-page chunks; falls back to str(page_number)
    section_heading: Optional[str] = None   # e.g. "2. Debt oriented FOF (Domestic)" — nice-to-have, improves tooltip context
    verbatim_text: str                # FULL text, not truncated — truncation is a display concern only
    source_url: Optional[str] = None  # deep link if the doc is web-hosted (SEBI circular URL etc.)
    local_doc_path: Optional[str] = None  # path/URI the frontend's internal PDF viewer can open
    char_start: Optional[int] = None  # for future PDF.js highlight-on-open
    char_end: Optional[int] = None

class Citation(BaseModel):
    marker: str            # "1", "16", "18" — must match what's embedded in the answer text
    source: SourceChunk

class MetricProvenance(BaseModel):
    marker: str                        # unique id for this numeric claim, e.g. "m1"
    surface_text: str                  # the exact substring as it appears in the answer, e.g. "20% of Net Assets"
    value: Optional[str] = None        # normalized value if extractable, e.g. "20%"
    provenance_type: Literal["verbatim", "computed", "assumed"]
    explanation: str                   # REQUIRED. Human-readable justification.
    # if verbatim -> explanation should just point to the citing source(s) (reuse Citation.marker list)
    supporting_citation_markers: list[str] = Field(default_factory=list)
    # if computed -> show the actual arithmetic/formula
    formula: Optional[str] = None          # e.g. "min(scheme_net_assets * 0.20, ...)"
    inputs_used: Optional[dict[str, str]] = None  # {"Net Assets": "as defined in Reg. 42(1)", ...}
    # if assumed -> state the assumption plainly, and its basis
    assumption_basis: Optional[str] = None

class LLMAnswer(BaseModel):
    answer_markdown: str                    # contains inline markers like [[cite:1]] and [[metric:m1]]
    citations: list[Citation]
    metrics: list[MetricProvenance]
    retrieval_mode: Optional[str] = None    # "HYBRID GRAPH + VECTOR" badge already shown in screenshot 3
```

**Why this matters for the "chunk id vs page number" fix**: `page_number` becomes a first-class, guaranteed-present-or-explicitly-None field. The frontend table stops reading `chunk_id` for display entirely; `chunk_id` remains only as a debug/telemetry field (useful for support tickets, never shown to the end user).

### 2.2 Guaranteeing `page_number` is populated
In the ingestion/chunking pipeline:
1. When chunking a PDF, always carry `page_number` (or `page_start`/`page_end` for chunks spanning a page break) from the PDF parser (e.g. `PyMuPDF`/`pdfplumber` gives page index per extracted block) into chunk metadata **at chunk-creation time**, not derived later.
2. For chunks whose source is not paginated (scraped HTML circular, a table extracted from a webpage), set `page_number = None` and set `page_label` to something meaningful instead (e.g. `"Web"` or the `<section>` anchor slug). The frontend must handle this fallback (see §3.2).
3. Add a migration/backfill script for already-indexed documents: iterate the vector store, re-open the source PDF by `document_id`, and patch in `page_number` for any chunk missing it. This is necessary because the screenshots show the system already has a large indexed corpus (`April 2025.pdf`, `Categorization and Rationalization of Mutual Fund Schemes.pdf`, `Borrowing by Mutual Funds.pdf`, etc.) — you don't want a two-tier experience where old answers show blank pages and new ones don't.

### 2.3 Merging "Document Provenance" into "Sources" at the API level
Today the two blocks look independently generated. Make the backend emit **one** array (`citations: list[Citation]`, as above) that is the single source of truth. The frontend then derives both the compact `SOURCES [1]..[5]` list-view and the expandable-verbatim view **from the same array** — never two separate calls/fields. This removes the duplication and guarantees consistency (no risk of the compact list and the detailed table disagreeing on page numbers, ordering, or dedup).

De-duplication rule: if two chunks come from the same `(document_id, page_number)`, merge them into a single citation entry unless their `verbatim_text` differs meaningfully (use a cheap similarity check, e.g. normalized Levenshtein/Jaccard > 0.9 ⇒ merge, keep the longer text).

### 2.4 Forcing the LLM to emit inline markers reliably
This is the highest-risk part of the whole plan: today the LLM (per Image 1) is already producing bracket citations like `[16]`, `[18]` inline in prose, and separately a table. To get **tooltip-addressable** markers, free-text bracket numbers are not enough — you need a machine-parseable token the frontend can regex/AST-match, decoupled from the human-visible bracket rendering.

**Approach — structured generation, not regex-scraping the final prose:**
- Use tool-calling / JSON schema-constrained decoding (Anthropic's structured outputs, or a two-pass "generate then annotate" pipeline) so the model returns `LLMAnswer` directly, with `answer_markdown` containing **custom inline tokens**:
  - `Equity oriented FOF (Domestic) [[cite:1]]`
  - `20% of Net Assets[[metric:m1]]`
- Never ask the model to hand-write `[1]`-style brackets and separately hope they line up with a table — that's the exact fragility visible in the current UI (Image 1's inline `[16]`, `[18]` markers vs. the SOURCES list at the bottom is already a manually-synced pattern, which is brittle).
- Validate post-generation: every `[[cite:N]]`/`[[metric:mX]]` token in `answer_markdown` **must** have a matching entry in `citations`/`metrics`; every entry **must** be referenced at least once in the text. Log/alert on mismatch (dangling citation or unused citation) — do not silently drop, because a citation the model claims but doesn't render breaks user trust, and an inline token with no matching data will crash/blank the tooltip on the frontend if not guarded.
- For **metrics specifically**, add a dedicated post-processing step (regex over the *raw* model draft for `\d+(\.\d+)?\s*%|\d+\s*(months?|days?|years?)|₹[\d,]+|\bcrore\b|\blakh\b` etc.) that cross-checks: every numeric claim matching these patterns must have a `[[metric:...]]` token; if the model forgot to tag one, run a lightweight second LLM call ("here is your draft, here is the list of numeric substrings found — tag each with a metric id and classify verbatim/computed/assumed") rather than shipping an inconsistent answer. This two-pass safety net matters because numeric under-citation is the exact failure mode that erodes trust in a compliance/regulatory tool like this one.

### 2.5 Streaming considerations
If the answer is streamed token-by-token to the frontend (common for chat UIs):
- `answer_markdown` chunks may arrive **before** the full `citations`/`metrics` arrays are known (they're typically emitted at the end, or via a separate tool-call block).
- Frontend must render `[[cite:1]]` tokens as **inert/loading placeholders** (small dim circle, no tooltip yet) until the final `citations` array lands, then hydrate. Do not attempt to open a tooltip against data that doesn't exist yet — guard with `if (!citation) return <span className="cite-marker cite-pending">{n}</span>`.
- Recommend sending `citations`/`metrics` as a **single final SSE event** (`event: provenance`) right after the last text token, rather than incrementally, since partial provenance is not actionable for tooltips anyway.

---

## 3. Frontend (React) — Component Architecture

### 3.1 Component tree change

```
Before:
<AnswerBubble>
  <MarkdownAnswer text={answer} />       # plain text w/ [16], [18] etc, not interactive
  <SourcesList citations={citations} />  # compact "[1] doc.pdf p.1" list
</AnswerBubble>
<ProvenanceTable rows={provenanceRows} />  # SEPARATE component, chunk id + truncated snippet

After:
<AnswerBubble>
  <MarkdownAnswer
     text={answer_markdown}
     citations={citationsById}
     metrics={metricsById}
  />                                      # renders [[cite:N]]/[[metric:mX]] as <CitationMark/> / <MetricMark/>
  <ProvenancePanel citations={citations} /> # THE ONLY sources block now; replaces both old blocks
</AnswerBubble>
```

`ProvenancePanel` renders:
- Header: `📌 Document Provenance & Exact Page Citations (${citations.length} Sources)` (kept, since user only asked to relocate it, not rename it) — collapsible at the **panel** level (the ▼ chevron already visible top-left in Image 1) **and**
- Each row independently collapsible at the **row** level (new requirement #3): `Source Document | Page | Verbatim Text Snippet [▾]`.

### 3.2 `ProvenancePanel` / row-level accordion

```jsx
// components/ProvenancePanel.jsx
function ProvenanceRow({ citation }) {
  const [expanded, setExpanded] = useState(false);
  const { document_name, page_label, page_number, verbatim_text } = citation.source;
  const pageDisplay = page_label ?? (page_number != null ? `p. ${page_number}` : "—");

  return (
    <>
      <tr className="provenance-row" onClick={() => setExpanded(e => !e)}>
        <td>{document_name}</td>
        <td>{pageDisplay}</td>
        <td className="snippet-cell">
          <button
            className="chevron-btn"
            aria-expanded={expanded}
            aria-controls={`snippet-${citation.marker}`}
            onClick={(e) => { e.stopPropagation(); setExpanded(x => !x); }}
          >
            <ChevronIcon direction={expanded ? "down" : "right"} />
          </button>
          {expanded ? null : truncate(verbatim_text, 80)}
        </td>
      </tr>
      {expanded && (
        <tr className="provenance-row-expanded" id={`snippet-${citation.marker}`}>
          <td colSpan={3}>
            <blockquote className="verbatim-full">{verbatim_text}</blockquote>
            {citation.source.source_url && (
              <a href={citation.source.source_url} target="_blank" rel="noopener noreferrer">
                Open source ↗
              </a>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export function ProvenancePanel({ citations }) {
  const [panelOpen, setPanelOpen] = useState(true);
  return (
    <section className="provenance-panel">
      <button className="panel-header" onClick={() => setPanelOpen(o => !o)} aria-expanded={panelOpen}>
        <ChevronIcon direction={panelOpen ? "down" : "right"} /> 📌 Document Provenance & Exact Page
        Citations ({citations.length} Sources)
      </button>
      {panelOpen && (
        <table>
          <thead>
            <tr><th>Source Document</th><th>Page</th><th>Verbatim Text Snippet</th></tr>
          </thead>
          <tbody>
            {citations.map(c => <ProvenanceRow key={c.marker} citation={c} />)}
          </tbody>
        </table>
      )}
    </section>
  );
}
```
Edge cases handled here on purpose:
- Clicking the row background *or* the chevron both toggle (better hit target, common UX request) but the chevron button calls `stopPropagation` so nested-click doesn't double-toggle.
- `page_label` fallback → `p. {page_number}` → `"—"` covers the non-paginated-source case from §2.2.
- Truncation for the **collapsed** row only — the full text is never truncated once expanded, per requirement #3 ("having all the text for particular source").
- Long verbatim text (multi-paragraph) — wrap in `blockquote` with `white-space: pre-wrap; max-height: 400px; overflow-y: auto;` so an extremely long page (e.g. a dense annexure) doesn't blow out page layout; user can scroll within the expanded card instead of the row growing unboundedly.

### 3.3 `CitationMark` (inline tooltip + redirect)

```jsx
// components/CitationMark.jsx
function CitationMark({ marker, citation }) {
  if (!citation) return <sup className="cite-mark cite-pending">[{marker}]</sup>; // streaming guard, §2.5

  const { document_name, page_label, source_url, local_doc_path, verbatim_text } = citation.source;
  const href = source_url ?? (local_doc_path ? `${local_doc_path}#page=${citation.source.page_number ?? ""}` : null);

  const content = (
    <>
      <strong>{document_name}</strong>{page_label ? ` — p. ${page_label}` : ""}
      <p className="cite-tooltip-snippet">{truncate(verbatim_text, 160)}</p>
      {href && <span className="cite-tooltip-cta">Click to open source ↗</span>}
    </>
  );

  const Wrapper = href ? "a" : "span";
  const wrapperProps = href ? { href, target: "_blank", rel: "noopener noreferrer" } : {};

  return (
    <Tooltip content={content}>
      <Wrapper className={`cite-mark ${href ? "cite-mark--linked" : "cite-mark--info-only"}`} {...wrapperProps}>
        [{marker}]
      </Wrapper>
    </Tooltip>
  );
}
```

Notes:
- **Redirect vs description-only** is decided per-citation, not globally: `source_url` (public SEBI/AMFI circular link) wins if present; otherwise fall back to the app's own PDF viewer route with a page-anchor (`local_doc_path#page=N`) if the doc is only stored locally; otherwise it's description-only (no `href`, tooltip still shows doc+page+snippet, just isn't clickable). This matches "tooltip with redirection if possible otherwise only description will do" exactly.
- Use a **portal-based tooltip** (e.g. Radix UI `Tooltip` or Floating UI) rather than plain CSS `:hover title=""`, because: (a) native `title` tooltips can't contain rich HTML/formatting, (b) portal tooltips can be repositioned to avoid clipping at viewport edges (important since citations can appear near the right edge of a narrow chat column), (c) they support keyboard focus (`Tab` to the citation, tooltip shows) — required for accessibility, and (d) they support **click-to-pin on touch devices** (see §3.5).

### 3.4 `MetricMark` (inline tooltip explaining provenance of a number)

```jsx
// components/MetricMark.jsx
function MetricMark({ marker, metric }) {
  if (!metric) return null; // never render a bare number as "interactive" if metadata is missing — fail closed

  const { surface_text, provenance_type, explanation, supporting_citation_markers,
          formula, inputs_used, assumption_basis } = metric;

  const badge = { verbatim: "From source", computed: "Calculated", assumed: "Assumption" }[provenance_type];

  const content = (
    <>
      <span className={`metric-badge metric-badge--${provenance_type}`}>{badge}</span>
      <p>{explanation}</p>
      {provenance_type === "computed" && formula && (
        <pre className="metric-formula">{formula}</pre>
      )}
      {provenance_type === "computed" && inputs_used && (
        <ul className="metric-inputs">
          {Object.entries(inputs_used).map(([k, v]) => <li key={k}><b>{k}:</b> {v}</li>)}
        </ul>
      )}
      {provenance_type === "assumed" && assumption_basis && (
        <p className="metric-assumption"><b>Basis:</b> {assumption_basis}</p>
      )}
      {supporting_citation_markers?.length > 0 && (
        <p className="metric-sources">
          See: {supporting_citation_markers.map(m => `[${m}]`).join(", ")}
        </p>
      )}
    </>
  );

  return (
    <Tooltip content={content}>
      <span className={`metric-mark metric-mark--${provenance_type}`} tabIndex={0}>
        {surface_text}
      </span>
    </Tooltip>
  );
}
```

CSS affordance so users can tell at a glance, without hovering, whether a number is trustworthy-verbatim or model-derived (important for a regulatory-compliance tool where silently blending "the circular literally says 20%" with "I computed/guessed 20%" is a real risk):
```css
.metric-mark--verbatim  { border-bottom: 1px dashed var(--color-success); }
.metric-mark--computed  { border-bottom: 1px dashed var(--color-info); }
.metric-mark--assumed   { border-bottom: 1px dashed var(--color-warning); background: color-mix(in srgb, var(--color-warning) 8%, transparent); }
```

### 3.5 Markdown rendering pipeline (wiring `[[cite:N]]` / `[[metric:mX]]` into React)

Use `react-markdown` + a small `remark`/`rehype` plugin (or a simple pre-tokenizing regex pass before handing text to `react-markdown`, whichever the existing stack already uses — check current `MarkdownAnswer` implementation first). General approach:
1. Split `answer_markdown` on `/\[\[(cite|metric):([\w.-]+)\]\]/g`.
2. Feed the surrounding markdown fragments through the normal renderer.
3. Splice in `<CitationMark>`/`<MetricMark>` React elements at the split points (an array-of-nodes render, not string concatenation, so React components stay live).
4. **Never** `dangerouslySetInnerHTML` the tooltip `content` — it's LLM-generated text; render it as React children (auto-escaped) to avoid XSS, even though this is presumably an internal tool. Treat all LLM output as untrusted for rendering purposes as a matter of policy.

### 3.6 Touch / mobile behavior
- Hover-only tooltips are unusable on touch. Implement: tap on `.cite-mark`/`.metric-mark` toggles the tooltip open (pinned) instead of navigating immediately if it's a link — first tap shows tooltip, second tap (on the "Open source ↗" CTA specifically) navigates. Alternatively, use a bottom-sheet on narrow viewports instead of a floating tooltip (better ergonomics for a paragraph of "computed" explanation text). Detect via `window.matchMedia('(pointer: coarse)')`, not just viewport width, since a touch laptop still benefits from hover tooltips when a mouse is attached.
- Close on outside-tap and on `Escape`.

---

## 4. Sidebar / layout fix (root-cause fix, not a pixel patch)

### 4.1 Replace fixed-margin flex layout with a CSS Grid + variable-driven column

```css
/* app-shell.css */
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-w, 260px) 1fr;
  min-height: 100vh;
  transition: grid-template-columns 200ms ease;
}

.app-shell[data-sidebar-collapsed="true"] {
  --sidebar-w: 64px; /* icon rail width, NOT 0 — keep the rail so the "Expand sidebar" affordance stays docked */
}

.sidebar {
  overflow: hidden; /* prevents inner content from forcing the column wider than --sidebar-w during the transition */
  min-width: 0;
}

.main-content {
  min-width: 0;      /* CRITICAL: without this, a grid/flex child with wide content (long chunk-id strings, wide tables) will refuse to shrink and blow out the column, exactly the "sidebar closed = width messed up" symptom */
  width: 100%;
  overflow-x: auto;  /* the ProvenancePanel table specifically should scroll internally rather than pushing the whole shell */
}
```

Key points that directly address the screenshot-3 bug:
- **No component computes `100% - sidebarWidthPx` manually anywhere.** The grid's second track is `1fr`, i.e. "whatever's left" — it is *definitionally* correct in both states, so there is no second source of truth to fall out of sync.
- Toggling collapse only ever changes **one CSS custom property** (`--sidebar-w`), set once at the shell root (e.g. via a `data-sidebar-collapsed` attribute driven by a `SidebarContext`), so every descendant recomputes from the same value — no per-component "is the sidebar open?" prop-drilling required, which is usually where these bugs creep back in after a refactor.
- `min-width: 0` on the `.main-content` grid item is the single most commonly-missed line in exactly this bug class — grid/flex items default to `min-width: auto`, meaning they refuse to shrink below their content's intrinsic width (a wide table, a long verbatim snippet, a long URL). That forces the grid to overflow the viewport, which is consistent with the horizontal scroll/edge-to-edge look in screenshot 3.
- Collapse the sidebar to an **icon rail (64px)**, not `display: none`/`width: 0`. Fully removing it from flow is what typically causes the layout to "jump" or mis-measure during the transition (React re-render timing vs. CSS transition timing race) — keeping a stable rail avoids that class of bug entirely and matches what screenshot 3 already shows (a collapsed rail with an "Expand sidebar" tooltip is present, it's the *content pane* that's currently broken, not the rail).

### 4.2 State source of truth
Put `sidebarCollapsed` in a single top-level context/store (not local state duplicated in both `<Sidebar/>` and `<AppShell/>`). Persist to `localStorage` so the layout is stable across reloads/sessions (avoids a flash-of-wrong-layout on mount). On mount, read the persisted value **before** first paint if possible (e.g. inline script or `useLayoutEffect` + `visibility: hidden` guard) to avoid a collapse/expand flicker.

### 4.3 Regression test to add
Add a Playwright/Cypress test: load the app, toggle sidebar collapse, assert:
- `.main-content` bounding box `width` equals `viewport width - sidebar rendered width` (±1px) in both states.
- No horizontal scrollbar appears on `body` in either state at common breakpoints (1280, 1440, 1920, and a 768 tablet breakpoint).
- The `ProvenancePanel` table doesn't force page-level horizontal scroll — only its own container does (`overflow-x: auto` scoped correctly, not leaking).

---

## 5. Edge cases & failure-mode checklist

1. **A citation marker appears in `answer_markdown` with no matching entry in `citations`.** → Render as inert `[N]`, log a client-side warning + backend telemetry event (`citation_orphan`), never throw/blank the whole answer.
2. **A `citations` entry is never referenced in the text.** → Still show it in `ProvenancePanel` (it may legitimately support the answer without an inline marker, e.g. general background context) but do not fabricate a fake inline marker for it.
3. **Two documents share the same file name but different `document_id`** (e.g. re-uploaded/updated circular). Always key by `document_id`, display `document_name`; if a name collision exists, append a short disambiguator in the tooltip (e.g. last-modified date) so users don't confuse versions of "Categorization and Rationalization of Mutual Fund Schemes.pdf".
4. **`verbatim_text` contains Markdown-special characters** (`|`, `*`, `#` from a table-heavy source, as visibly the case in Image 1's `src.4` row which literally contains a markdown table fragment `"| 2. | Debt oriented FOF..."`). Render the expanded snippet as **plain preformatted text**, not through the markdown renderer, so stray `|`/`#` don't get reinterpreted as table/heading syntax inside the tooltip/expanded card.
5. **Metric value appears multiple times with different provenance** (e.g. "20%" appears once as a verbatim quote from Reg. 42 and again later as a computed example figure). Each occurrence must get its **own** `[[metric:mX]]` id — never reuse one metric id for multiple surface occurrences, or the tooltip will show the wrong explanation for one of them.
6. **LLM asserts a number with no source at all and no honest way to justify it** (hallucination risk). The `provenance_type: "assumed"` bucket must be used defensively here — the pipeline should treat "no citation and no computable basis" as a hard requirement to mark `assumed` with `assumption_basis` explaining the reasoning, rather than silently presenting it as fact. Consider a backend guardrail: any numeric claim with `provenance_type` missing/unclassified blocks the response from shipping (return an error to the generation step, force a retry with the two-pass tagging from §2.4) rather than surfacing an untagged number to a compliance user.
7. **Very long documents / very many citations** (n=20+). Virtualize the `ProvenancePanel` rows if perf becomes an issue (`react-window`), but the per-row expand/collapse behavior above already keeps DOM light since full text only mounts when expanded.
8. **RTL/i18n**: chevron direction and tooltip placement logic should use logical properties (`inset-inline-start` etc.) if the app ever supports RTL locales — flag as future-proofing, not urgent given SEBI/AMFI content is English-only today.
9. **PDF deep-linking accuracy**: `#page=N` works for browser-native PDF viewers but not all embedded viewers (e.g. `react-pdf`). If the app uses a custom in-app PDF viewer, expose a proper route param (`/documents/:id?page=N`) instead of relying on `#page=` fragment support.
10. **Printing/export**: if answers are ever exported to PDF/Word for compliance record-keeping, tooltips are invisible in print. Ensure the `ProvenancePanel`'s expanded-by-default-on-print state (via `@media print { .verbatim-full { display: block !important; } }`) so exported records retain the audit trail even without interactive tooltips.

---

## 6. Rollout sequence

1. **Backend**: ship the unified `LLMAnswer`/`Citation`/`MetricProvenance` schema behind a feature flag; backfill `page_number` for the existing index (§2.2); add the citation/metric validation + two-pass tagging safety net (§2.4).
2. **Frontend**: build `ProvenancePanel`, `CitationMark`, `MetricMark`, `Tooltip` primitives against mock data matching the new schema; ship behind the same flag.
3. **Layout**: land the Grid-based sidebar fix independently (it's decoupled from the provenance work and safe to ship first — lower risk, immediately fixes a visibly broken UI).
4. **Integrate + dark-launch**: enable the flag for internal users only, compare old vs new provenance panel output on a fixed set of historical queries (regression corpus), specifically check page-number correctness and citation/metric completeness (§5.1/§5.6 guardrails).
5. **GA**: remove the old `ProvenanceTable`/duplicate `SourcesList` components entirely once parity is confirmed, to avoid maintaining two provenance renderers.

