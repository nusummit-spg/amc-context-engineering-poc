# Implementation Prompt — Per-Response Feedback Container, Failure-Taxonomy Checkboxes & Clickable PDF Citations

Use this document as a build spec. It is written so it can be handed directly to a frontend engineer (React) and a backend engineer (Python), or pasted as a prompt into a coding agent. It covers: what to build, where it goes, the exact taxonomy content for the 12 checkboxes and their hover tooltips, the API contract, the SQLite schema, and the PDF-redirect behavior for ContextGraph sources.

Reference: taxonomy definitions are taken from `AMC_Feedback_loop_Architecture_v1_2.html`, §7 "Failure Taxonomy" (Component 5) and §4.5 "Human Feedback Capture" (Component 2). The 12 categories requested map 1:1 to the primary failure families **F01–F12** in that document (F13 System/Infrastructure and F14 Evaluation/Feedback Integrity are intentionally excluded — they are internal ops categories, not user-facing).

---

## 1. Feature Summary

For every LLM-generated answer shown in the **ContextGraph** result panel, add a single feedback container directly below that answer. The container lets a reviewer (the "Compliance & Regulatory Officer" persona shown in the header):

1. Tick one or more of 12 failure-taxonomy checkboxes describing what's wrong with that specific answer.
2. Hover any checkbox to see a small popover explaining what that failure category means.
3. Type free-text commentary in a box styled like the existing "Ask a follow-up" input.
4. Click **Submit** (to the right of the text box) to persist the feedback via API into SQLite.

Additionally, in the ContextGraph panel's **SOURCES** list (`[1] Guidelines for Investment Advisers.pdf`, etc.), each source must become a clickable link that opens the underlying PDF in a new browser tab, ideally scrolled/anchored to the cited page.

There is exactly **one** feedback container per turn, tied to the ContextGraph answer's `response_id`.

---

## 2. Where It Goes (Layout)

```
┌───────────────────────────────────┐
│ ContextGraph                        │
│  Answer | Ontology View             │
│  ✓ HIGH CONFIDENCE                  │
│  ⚡ Fresh LLM Synthesis ...          │
│  ⚡ Vector Search Bypassed ...       │
│  ▶ Graph Triplet Path Traversed     │
│  ▶ Document Provenance & Citations  │
│  ... answer text ...                │
│  SOURCES                            │
│  [1] Guidelines...pdf  (link)       │
│  [2] Disclosure...pdf  (link)       │
│  [3] April 2025.pdf    (link)       │
│  [Nodes][Tokens][Time]              │
│  ▶ Microsecond Telemetry            │
│ ┌─────────────────────────────────┐│
│ │ FEEDBACK  (new container)        ││
│ │ [ ] Intent/Understanding  ⓘ      ││
│ │ [ ] Entity Resolution     ⓘ      ││
│ │ ... (12 total, 2-col grid) ...   ││
│ │ [ free-text box ]     [Submit]   ││
│ └─────────────────────────────────┘│
└───────────────────────────────────┘
```

- Insert the feedback container as the **last child** inside the ContextGraph result card, after the "Microsecond Telemetry & Execution Ledger" collapsible row.
- Visually separate it from the answer above with a `<hr>` / top border, same card padding as the rest of the panel, so it reads as part of the same card, not a floating block.
- It renders **once the answer has finished streaming/loading** for that turn, and re-renders fresh (unchecked, empty text) for every new turn — feedback is scoped to one `response_id`.

---

## 3. The 12 Checkboxes — Labels, Taxonomy Codes & Tooltip Copy

Each checkbox's `value` sent to the API is the taxonomy code (`F01`…`F12`); the label shown to the user is the plain name. The tooltip is a short, reviewer-facing explanation derived from the taxonomy doc — **not** the raw subtype list, so it stays readable in a small popover.

| # | Checkbox label (UI) | Code | Tooltip copy (shown on hover) |
|---|---|---|---|
| 1 | Intent / Understanding | `F01` | Did the system correctly understand what was being asked — the right primary intent, any secondary or multiple intents, and whether it caught ambiguity, temporal/comparison phrasing, or an advisory vs. informational request? |
| 2 | Entity Resolution | `F02` | Did the system identify the right fund/scheme/product? A response can be well-grounded and still wrong if it answers about the wrong entity, confuses Direct/Regular or Growth/IDCW plan options, or uses a stale entity mapping. |
| 3 | Context / Conversation State | `F03` | Did the system correctly carry forward relevant information from earlier turns — the right prior turn and entity, without truncating key evidence, injecting irrelevant context, or forgetting a constraint or correction the user gave earlier? |
| 4 | Retrieval | `F04` | Were the right documents found and ranked? Covers no retrieval, wrong document, low recall/precision, a missing authoritative source, or a correct document being dropped by reranking or filtering — independent of what the model did with it afterward. |
| 5 | Source / Freshness | `F05` | Was the underlying source current and correctly versioned? Covers stale, expired, or superseded documents, wrong effective dates, or low-authority sources — even when the model faithfully reproduced what that (outdated) source said. |
| 6 | Citation / Attribution | `F06` | Are the citations accurate and load-bearing — do they point to a real document and page, and does that passage actually support the claim? Covers missing, broken, wrong-document, wrong-span, or overstated citations, and claims with no citation at all. |
| 7 | Grounding / Unsupported Generation | `F07` | Is every claim actually supported by the retrieved evidence, or did the model add something not present in the sources — a fabricated fact, number, entity, or source? (Different from a wrong fact faithfully copied from a stale source — flag that as Source/Freshness instead.) |
| 8 | Factual / Numerical Accuracy | `F08` | Are the numbers, dates, percentages, currencies, and units correct against the authoritative value (e.g., stated TER vs. actual TER)? Covers numeric mismatches, unit/currency errors, and calculation mistakes. |
| 9 | Completeness / Relevance | `F09` | Does the answer cover everything the question needed — no omitted facts, risks, or constraints, and no unanswered sub-parts — without padding it with excessive or irrelevant information? |
| 10 | Reasoning / Consistency | `F10` | Is the response internally consistent and logically sound — no self-contradiction, no contradiction with its own evidence, valid comparisons, and no unsupported causal leaps or arithmetic errors in the reasoning? |
| 11 | Communication / Tone | `F11` | Is the response clearly written and appropriately worded for a compliance audience — not overly jargon-heavy, verbose, alarmist, falsely certain, or mismatched to the requested language or format? |
| 12 | Governance / Compliance / Safety | `F12` | Does the response stay inside regulatory and firm boundaries — no advice-boundary breach, missing mandatory disclosure, prohibited/promotional language, PII exposure, jurisdiction mismatch, or product-restriction violation, and is escalation flagged where required? |

Implementation note: store this table as a single constants file (`failureTaxonomy.ts` / `failure_taxonomy.py`) shared by frontend tooltip rendering and backend validation, so the two never drift apart.

---

## 4. Frontend (React) — Component Plan

### 4.1 New components

```
src/
  constants/
    failureTaxonomy.ts        # the 12-row table above, single source of truth
  components/
    feedback/
      FeedbackContainer.tsx   # renders the single container
      FailureCheckboxGrid.tsx # 2-column grid of 12 <FailureCheckbox/>
      FailureCheckbox.tsx     # checkbox + hover/focus tooltip
      FeedbackInputRow.tsx    # text input + Submit button (mirrors "Ask a follow-up" bar)
      Tooltip.tsx             # small reusable hover popover (if not already in the design system)
    sources/
      CitationLink.tsx        # renders "[1] Guidelines for Investment Advisers.pdf" as a link
```

### 4.2 `failureTaxonomy.ts`

```ts
export interface FailureCategory {
  code: 'F01'|'F02'|'F03'|'F04'|'F05'|'F06'|'F07'|'F08'|'F09'|'F10'|'F11'|'F12';
  label: string;
  tooltip: string;
}

export const FAILURE_TAXONOMY: FailureCategory[] = [
  { code: 'F01', label: 'Intent / Understanding',
    tooltip: 'Did the system correctly understand what was being asked — the right primary intent, any secondary or multiple intents, and whether it caught ambiguity, temporal/comparison phrasing, or an advisory vs. informational request?' },
  { code: 'F02', label: 'Entity Resolution',
    tooltip: 'Did the system identify the right fund/scheme/product? A response can be well-grounded and still wrong if it answers about the wrong entity, confuses Direct/Regular or Growth/IDCW plan options, or uses a stale entity mapping.' },
  { code: 'F03', label: 'Context / Conversation State',
    tooltip: 'Did the system correctly carry forward relevant information from earlier turns — the right prior turn and entity, without truncating key evidence, injecting irrelevant context, or forgetting a constraint or correction the user gave earlier?' },
  { code: 'F04', label: 'Retrieval',
    tooltip: 'Were the right documents found and ranked? Covers no retrieval, wrong document, low recall/precision, a missing authoritative source, or a correct document dropped by reranking or filtering.' },
  { code: 'F05', label: 'Source / Freshness',
    tooltip: 'Was the underlying source current and correctly versioned? Covers stale, expired, or superseded documents, wrong effective dates, or low-authority sources — even when the model faithfully reproduced that (outdated) source.' },
  { code: 'F06', label: 'Citation / Attribution',
    tooltip: 'Are the citations accurate and load-bearing — do they point to a real document/page, and does that passage actually support the claim? Covers missing, broken, wrong-document, or overstated citations.' },
  { code: 'F07', label: 'Grounding / Unsupported Generation',
    tooltip: 'Is every claim actually supported by the retrieved evidence, or did the model add something not present in the sources — a fabricated fact, number, entity, or source?' },
  { code: 'F08', label: 'Factual / Numerical Accuracy',
    tooltip: 'Are the numbers, dates, percentages, currencies, and units correct against the authoritative value (e.g., stated TER vs. actual TER)?' },
  { code: 'F09', label: 'Completeness / Relevance',
    tooltip: 'Does the answer cover everything the question needed — no omitted facts, risks, or unanswered sub-parts — without padding it with irrelevant information?' },
  { code: 'F10', label: 'Reasoning / Consistency',
    tooltip: 'Is the response internally consistent and logically sound — no self-contradiction, no contradiction with its own evidence, and no unsupported causal leaps or arithmetic errors?' },
  { code: 'F11', label: 'Communication / Tone',
    tooltip: 'Is the response clearly written and appropriate for a compliance audience — not overly jargon-heavy, verbose, alarmist, or falsely certain?' },
  { code: 'F12', label: 'Governance / Compliance / Safety',
    tooltip: 'Does the response stay inside regulatory and firm boundaries — no advice-boundary breach, missing disclosure, promotional language, PII exposure, or product-restriction violation?' },
];
```

### 4.3 `FeedbackContainer.tsx` — props & responsibilities

```tsx
interface FeedbackContainerProps {
  responseId: string;       // ties feedback to the exact ContextGraph answer shown
  interactionId: string;    // conversation/interaction this turn belongs to
  sessionId: string;
  turnNumber: number;
  query: string;            // the user's question for this turn (for audit trail)
  actorId?: string;         // e.g. sarah_compliance, from the Active User Profile selector
  actorRole?: string;       // e.g. "Compliance & Regulatory Officer", from the same profile
}
```

Responsibilities:
- Owns local state: `selectedCodes: Set<string>`, `freeText: string`, `submitState: 'idle'|'submitting'|'success'|'error'`.
- Renders `FailureCheckboxGrid` (12 checkboxes, 2 columns × 6 rows or similar), then `FeedbackInputRow`.
- On **Submit**: build the payload (§5.1), `POST /api/feedback`, show inline success (e.g. "Feedback recorded" small green text, auto-dismiss) or error state with a retry affordance.
- Submit button is **disabled** unless at least one checkbox is checked **or** free text is non-empty (mirrors "give me something to store" — an empty submission is meaningless).
- After a successful submit, keep the checkboxes/text as-is but lock further edits behind an "Edit feedback" toggle (optional) — OR simply allow re-submit, which the backend treats as an update (upsert) to the same `(response_id, actor)` pair. Pick the **upsert** behavior (§5.2) — simpler and avoids duplicate rows per reviewer per answer.
- `actorId`/`actorRole` should be read from whatever "Active User Profile (RBAC)" selection is already active in the app shell (the left sidebar shows a user/role/department selector) rather than hardcoded, so feedback is correctly attributed per reviewer.

### 4.4 `FailureCheckbox.tsx`

```tsx
interface FailureCheckboxProps {
  category: FailureCategory;
  checked: boolean;
  onChange: (code: string, checked: boolean) => void;
}
```

- Renders a standard checkbox + label.
- On `mouseenter`/`focus` of the row (not just the tiny checkbox hit-area — wrap label+checkbox in one hoverable row), show a `Tooltip` positioned above or beside the row with `category.tooltip`.
- Use `onFocus`/`onBlur` too, not just mouse events, so keyboard users get the same popover (accessibility).
- Debounce show/hide by ~150ms to avoid flicker when moving the mouse across adjacent rows.
- Tooltip should be short single-paragraph, `max-width: 320px`, small font, dark background/light text (or match existing app tooltip styling if one already exists elsewhere in the codebase — check `frontend-design` conventions before inventing a new one).

### 4.5 `FeedbackInputRow.tsx`

Reuse the exact visual pattern of the existing top bar (`"Ask a follow-up — conversation context carries forward…"` input + `Send` button), but scoped to this container:

```tsx
<div className="feedback-input-row">
  <input
    type="text"
    placeholder="Add your comments on this answer…"
    value={freeText}
    onChange={e => setFreeText(e.target.value)}
    maxLength={2000}
  />
  <button
    className="feedback-submit-btn"
    disabled={!(selectedCodes.size > 0 || freeText.trim().length > 0) || submitState === 'submitting'}
    onClick={handleSubmit}
  >
    {submitState === 'submitting' ? 'Submitting…' : 'Submit'}
  </button>
</div>
```

- Submit button sits to the **right** of the text input, same row, matching the reference `Send` button styling (same accent color as the app's primary action button in the screenshot — the muted red/rose).

### 4.6 `CitationLink.tsx` — clickable PDF sources

Current ContextGraph "SOURCES" block renders plain text like:
```
[1] Guidelines for Investment Advisers.pdf
[2] Disclosure of Risk adjusted Return - Information Ratio (IR) for Mutual Fund Schemes.pdf
[3] April 2025.pdf
```

Each of these must become a real link. Requirements:
- Opens in a **new tab** (`target="_blank" rel="noopener noreferrer"`).
- Opens the **actual PDF file**, not a search results page.
- Where possible, deep-link to the **cited page** (the ContextGraph pipeline already knows page-level provenance — see §7).
- Visually: keep the `[1]`, `[2]`, `[3]` numbering, underline/blue-link the filename on hover, standard link affordance (cursor pointer, focus outline for keyboard nav).
- If a source has no resolvable file (broken/missing mapping), render as plain (non-clickable) text with a small "unavailable" indicator instead of a dead link — **do not** silently render a broken `<a href="#">`. This doubles as a live signal for `F06 citation_broken`.

```tsx
interface CitationLinkProps {
  index: number;
  title: string;
  url: string | null;   // resolved, absolute URL to the PDF (optionally #page=N)
}

function CitationLink({ index, title, url }: CitationLinkProps) {
  if (!url) {
    return <span className="citation citation--unavailable">[{index}] {title} (source unavailable)</span>;
  }
  return (
    <a className="citation" href={url} target="_blank" rel="noopener noreferrer">
      [{index}] {title}
    </a>
  );
}
```

---

## 5. API Contract

### 5.1 `POST /api/feedback`

**Request body:**

```json
{
  "response_id": "resp_9f1c2a...",
  "interaction_id": "int_4b7e...",
  "session_id": "300c8a08-5235-41ec-87dd-704e62bcd415",
  "turn_number": 3,
  "query_text": "Can Large Cap mutual fund schemes invest the remaining amount in debt instruments?",
  "actor_id": "sarah_compliance",
  "actor_role": "Compliance & Regulatory Officer",
  "selected_categories": ["F06", "F09"],
  "feedback_text": "Citation [2] doesn't actually cover the debt-instrument clause; feels padded with unrelated risk-ratio content.",
  "client_timestamp": "2026-09-01T11:52:03.421+05:30"
}
```

Notes:
- `selected_categories` is an array of zero-or-more codes from `F01`–`F12`; validate server-side against the fixed set (§3).
- `actor_id`/`actor_role` should be populated from the active "Active User Profile (RBAC)" selection already shown in the app shell.
- At least one of `selected_categories` (non-empty) or `feedback_text` (non-empty, trimmed) is required — return `422` otherwise.

**Response (201 Created / 200 OK on upsert):**

```json
{
  "feedback_id": "fb_7e2c9a1d",
  "response_id": "resp_9f1c2a...",
  "stored_at": "2026-09-01T06:22:04.113Z",
  "status": "recorded"
}
```

**Errors:**
- `400` — malformed JSON / missing required fields.
- `422` — empty submission (no categories AND no free text), or invalid category code.
- `500` — DB write failure (frontend shows the error state + a manual "Retry" button; do not silently drop the feedback).

### 5.2 Idempotency / upsert key

Treat `(response_id, actor_id)` as the natural key. If a POST arrives for a key that already has a row, **update** that row (new `selected_categories`, `feedback_text`, `updated_at`) rather than inserting a duplicate. This lets a reviewer revise their feedback on the same answer without creating noise.

### 5.3 `GET /api/feedback?response_id=...` (optional, for Admin & Governance tab)

Returns the stored feedback record(s) for a given response — useful for the existing "Admin & Governance" tab in the header to later build a review dashboard. Not required for the checkbox feature itself, but cheap to add now since the table already supports it.

### 5.4 `GET /api/sources/{document_id}` — PDF resolution (see §7)

Returns (or redirects to) the actual file so the frontend has a real `url` to put in `CitationLink`.

---

## 6. Backend (Python) — Implementation Plan

Assume the existing backend is a Python API (the UI shows `Backend: /api`) — spec below is framework-agnostic but written against **FastAPI + SQLite** since that's the lightest fit for "stored in SQLite via API." Adjust import paths if the existing backend uses Flask/Django instead — the schema and endpoint contracts stay the same.

### 6.1 SQLite schema

```sql
CREATE TABLE IF NOT EXISTS response_feedback (
    feedback_id        TEXT PRIMARY KEY,
    response_id         TEXT NOT NULL,
    interaction_id       TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    turn_number          INTEGER NOT NULL,
    query_text            TEXT,
    actor_id              TEXT,
    actor_role            TEXT,
    selected_categories   TEXT NOT NULL,        -- JSON array of codes, e.g. '["F06","F09"]'
    feedback_text             TEXT,
    client_timestamp      TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(response_id, actor_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_response ON response_feedback(response_id);
CREATE INDEX IF NOT EXISTS idx_feedback_session   ON response_feedback(session_id);
```

- `selected_categories` stored as a JSON-encoded text column (SQLite has no native array type) — decode/encode at the API boundary.
- Add a `CHECK` at the application layer too (validate against the 12-code allowlist before insert), since SQLite `CHECK` on JSON contents is awkward.
- `UNIQUE(response_id, actor_id)` backs the upsert behavior in §5.2. Until real per-user auth exists beyond the RBAC profile selector, `actor_id` can fall back to the `session_id` so at least one reviewer per session can't spam duplicate rows.

### 6.2 Endpoint skeleton

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
import sqlite3, json, uuid, datetime

router = APIRouter(prefix="/api")

VALID_CODES = {f"F{str(i).zfill(2)}" for i in range(1, 13)}  # F01..F12

class FeedbackIn(BaseModel):
    response_id: str
    interaction_id: str
    session_id: str
    turn_number: int
    query_text: str | None = None
    actor_id: str | None = None
    actor_role: str | None = "compliance_officer"
    selected_categories: list[str] = Field(default_factory=list)
    feedback_text: str | None = None
    client_timestamp: str | None = None

    @field_validator("selected_categories")
    @classmethod
    def validate_codes(cls, v):
        bad = set(v) - VALID_CODES
        if bad:
            raise ValueError(f"Unknown failure category codes: {bad}")
        return v

@router.post("/feedback", status_code=201)
def submit_feedback(payload: FeedbackIn):
    if not payload.selected_categories and not (payload.feedback_text or "").strip():
        raise HTTPException(422, "Submit at least one category or a comment.")

    actor_id = payload.actor_id or payload.session_id
    now = datetime.datetime.utcnow().isoformat()

    conn = get_db_connection()  # existing app's SQLite connection helper
    existing = conn.execute(
        "SELECT feedback_id FROM response_feedback WHERE response_id=? AND actor_id=?",
        (payload.response_id, actor_id),
    ).fetchone()

    if existing:
        feedback_id = existing["feedback_id"]
        conn.execute(
            """UPDATE response_feedback
               SET selected_categories=?, feedback_text=?, updated_at=?
               WHERE feedback_id=?""",
            (json.dumps(payload.selected_categories), payload.feedback_text, now, feedback_id),
        )
    else:
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO response_feedback
               (feedback_id, response_id, interaction_id, session_id, turn_number,
                query_text, actor_id, actor_role, selected_categories, feedback_text,
                client_timestamp, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (feedback_id, payload.response_id, payload.interaction_id, payload.session_id,
             payload.turn_number, payload.query_text, actor_id, payload.actor_role,
             json.dumps(payload.selected_categories), payload.feedback_text,
             payload.client_timestamp, now, now),
        )
    conn.commit()

    return {
        "feedback_id": feedback_id,
        "response_id": payload.response_id,
        "stored_at": now,
        "status": "recorded",
    }
```

- `get_db_connection()` should reuse whatever SQLite connection pattern the existing `/api` backend already uses (don't hand-roll a second DB layer).
- Wrap the DB call in `try/except sqlite3.Error` → `HTTPException(500, ...)` with a generic message (don't leak raw DB errors to the client).
- Add this table's creation to whatever startup/migration step already initializes the app's SQLite file.

---

## 7. Clickable PDF Sources — Backend + Frontend Changes

Today the ContextGraph "SOURCES" list is rendered as plain filenames with no link. To make each one open the real PDF in a new tab:

**Backend changes needed:**
1. Every source object the ContextGraph endpoint returns must include, at minimum:
   ```json
   { "index": 2, "title": "Disclosure of Risk adjusted Return - Information Ratio (IR) for Mutual Fund Schemes.pdf", "document_id": "doc_5521", "page": 4, "url": "/files/doc_5521.pdf#page=4" }
   ```
   `document_id`/`page` should already exist internally as part of the graph's document provenance tracking (the "Document Provenance & Exact Page Citations" collapsible already references page-level citations) — this just needs to be surfaced on the returned source objects.
2. Serve the PDFs from a static/protected file route, e.g. `GET /api/files/{document_id}` (or a signed URL if these documents are access-controlled) — do not expose raw filesystem paths to the frontend.
3. If a `document_id` cannot be resolved to a stored file (deleted, not yet ingested, mapping broken), set `"url": null` and let `CitationLink` (§4.6) render the "source unavailable" state instead of a dead link. This is a real, useful signal — it's effectively a live instance of the `F06 citation_broken` failure subtype and should ideally also nudge the reviewer to check that box.

**Frontend changes needed:**
1. Replace the plain-text SOURCES list with a mapped list of `<CitationLink/>` using the `url` field above.
2. Preserve the existing `[1]`, `[2]`, `[3]` numbering.
3. `target="_blank" rel="noopener noreferrer"` so it opens in a new tab and doesn't leak a `window.opener` reference back to the app.
4. If the browser/PDF viewer doesn't support `#page=N` fragment anchoring (varies by browser/PDF viewer), it's an acceptable degrade to just open the PDF at page 1 — the anchor is a "nice to have," not a hard requirement.

---

## 8. Validation, Edge Cases & UX Rules

- **Empty submit blocked.** Submit stays disabled until ≥1 checkbox is checked or free text is non-empty (also enforced server-side — never trust the client-side disable alone).
- **One container per turn.** When a new turn is submitted (Turn 4, Turn 5, …), the new turn's answer gets its own fresh, empty `FeedbackContainer` — do not carry over checkbox state from the previous turn's container.
- **Resubmission = update, not duplicate.** See §5.2 — same reviewer/session resubmitting on the same answer updates the existing row.
- **No destructive resets.** If a submit fails (network/500), keep the user's checked boxes and typed text in place; only clear the form after a confirmed success.
- **Tooltip accessibility.** Tooltip must be reachable via keyboard (`Tab` to the row, tooltip shows on focus) as well as mouse hover — don't build a hover-only interaction.
- **Character limit.** Cap free text client-side (`maxLength`, e.g. 2000 chars) and re-validate server-side; show a small counter near the input if the design system already does that elsewhere.
- **Broken citation link.** Never render an `<a>` with an empty/`"#"` href — render the "unavailable" fallback (§4.6, §7) instead.
- **Loading state while the answer streams.** Do not mount `FeedbackContainer` until the ContextGraph answer has fully rendered — feedback on a half-streamed answer isn't meaningful and `response_id` may not exist yet.

---

## 9. Styling Guidance

Match the existing visual language from the screenshots (rounded-corner white cards, thin grey borders, the muted rose/red accent used on the `Send` button and the `HIGH CONFIDENCE` badge tone):

- Container: same card padding/border as the parent panel, separated by a `1px solid #eee` top rule and a small `FEEDBACK` eyebrow label (uppercase, small, grey — matching `SOURCES` styling already used).
- Checkboxes: 2-column grid on desktop (`grid-template-columns: 1fr 1fr`), single column on narrow/mobile widths; generous row height so the hover target is the whole row, not just the tiny box.
- Submit button: same rose/red fill as the top `Send` button, disabled state = greyed out per existing disabled-button convention in the app.
- Tooltip: small elevation/shadow, dark-on-light or light-on-dark (match whatever the app already uses for any existing tooltip/popover; if none exists yet, default to a small white card with `box-shadow: 0 2px 8px rgba(0,0,0,0.15)` and 12–13px text).
- Citation links: standard link blue on hover/underline, but keep default (unvisited) state visually close to the current plain text so the SOURCES block doesn't suddenly look like a different UI — only the interactive affordance (cursor + hover underline) should change.

---

## 10. Task Breakdown

**Frontend**
1. Add `failureTaxonomy.ts` constants file (§4.2).
2. Build `Tooltip`, `FailureCheckbox`, `FailureCheckboxGrid`, `FeedbackInputRow`, `FeedbackContainer` components.
3. Mount one `FeedbackContainer` per turn, wired to that turn's ContextGraph `response_id`/`interaction_id`, and to the currently active user profile (`actor_id`/`actor_role`) from the RBAC selector.
4. Wire `Submit` to `POST /api/feedback`; handle loading/success/error states.
5. Add `CitationLink` and swap it into the ContextGraph SOURCES rendering, consuming the new `url`/`page` fields from the API response.
6. Responsive pass (mobile: single-column checkbox grid, stacked input+button).
7. Accessibility pass (keyboard focus, `aria-describedby` linking each checkbox to its tooltip text).

**Backend**
1. Create `response_feedback` SQLite table + migration (§6.1).
2. Implement `POST /api/feedback` with Pydantic validation against the 12-code allowlist and the "at least one field" rule (§6.2).
3. Implement upsert-by-`(response_id, actor_id)` logic.
4. Extend the ContextGraph answer endpoint to include `document_id` / `page` / `url` per source (§7).
5. Add `GET /api/files/{document_id}` (or signed-URL equivalent) to actually serve the PDFs.
6. (Optional, low effort now) `GET /api/feedback?response_id=...` for the future Admin & Governance dashboard.
7. Error handling: 422 for invalid/empty payloads, 500 wrapped generically for DB failures.

**QA / Acceptance criteria**
- [ ] Each of the 12 checkboxes shows the correct label and correct tooltip text on both hover and keyboard focus.
- [ ] Submitting with zero checkboxes and empty text is blocked (button disabled + server also rejects with 422 if forced).
- [ ] Resubmitting on the same answer updates the existing row instead of creating a duplicate.
- [ ] A new turn renders a fresh, empty feedback container.
- [ ] Every SOURCES entry in the ContextGraph panel opens the correct PDF in a new tab; a source with no resolvable file shows the "unavailable" state instead of a dead link.
- [ ] Feedback rows are queryable in SQLite with correct `session_id`, `turn_number`, `selected_categories` (valid JSON array), `actor_id`, and `feedback_text`.
