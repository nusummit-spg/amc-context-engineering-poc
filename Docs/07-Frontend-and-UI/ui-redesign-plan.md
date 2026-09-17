# AMC Context Engine — Main App Redesign Plan
### Unifying the product with the Login Screen's visual language

**Prepared for:** AMC Context Engine (regulatory intelligence workspace)
**Scope:** Chat Assistant, Compliance Scorecard, Violations Explorer, Fund Schemes Matrix, Remediation & SLA, Multi-Jurisdiction, Compare, Analytics, Admin & Governance
**Reference:** Login screen (`localhost:5173` sign-in view) — treated as the design system's source of truth
**Colors below were sampled directly from the provided screenshots (pixel-level), not guessed** — see §3 for method notes.

---

## 1. Why this redesign

The login screen reads as a calm, editorial, trustworthy financial/regulatory product: warm parchment background, a single restrained navy accent, a serif headline, thin outline icons, underline-style inputs, and a lot of quiet whitespace.

The rest of the app currently reads as a different, busier product: emoji used as functional icons, five or six unrelated accent colors fighting for attention (rust, green, orange, blue, purple), flat saturated badge chips, and no consistent elevation or interaction feedback. None of this is *bad* individually — but none of it was clearly *chosen*, and it doesn't match the sign-in experience the user sees first.

The goal is **not** to make the app minimal or strip it down — it's a dense, information-heavy compliance tool and should stay that way. The goal is to make it **look like it was designed by the same team**, on purpose: one accent color used with intent, a disciplined neutral palette, real icons, and small, purposeful motion instead of static flat blocks.

---

## 2. Ready-to-use design prompt

Paste this directly into a coding/design assistant (or use it as the brief for a developer) when implementing the redesign. It's self-contained; the rest of this document is the supporting detail behind every decision in it.

> Redesign the AMC Context Engine application (Chat Assistant, Compliance Scorecard, Violations Explorer, Fund Schemes Matrix, Remediation & SLA, Multi-Jurisdiction, Compare, Analytics, and Admin & Governance) to visually match the existing login screen's design language. Keep the information density — this is a professional compliance/regulatory tool, not a minimal consumer app.
>
> **Do:**
> - Replace every emoji used as an icon (in the sidebar nav, top tabs, status indicators, badges, and buttons) with a proper outline icon from the Lucide icon set — 18–20px, 1.5–1.75px stroke, rounded caps, no fill — matching the mail/lock/eye icons already used on the login screen.
> - Standardize the color system to: warm parchment backgrounds (`#FAFAF8` canvas, `#F2EFE7` secondary panels), a single navy accent (`#1F3A5F`) for every primary action, link, active nav state, and focus ring, near-black ink (`#15181D`) for headings, and muted grays for secondary text. Reserve color outside that palette *only* for a small, desaturated semantic set: sage green (success), warm gold-tan (warning/informational — this one already exists in the product and should stay), and muted terracotta (destructive actions only — delete, reject, remove).
> - Pair a serif display face (Source Serif 4 / Lora / Georgia) for page titles and hero moments with a sans-serif (Inter) for everything else — exactly the pairing on the login screen's "Welcome back."
> - Give every card, dropdown, and popover a small, consistent shadow (resting: `0 2px 6px rgba(21,24,29,0.06)`) and raise it slightly on hover (`0 6px 16px rgba(21,24,29,0.08)`) with a 150ms ease-out transition. No large drop shadows or glows.
> - Add small, purposeful hover and focus states to every interactive element (nav items, tabs, buttons, table rows, cards, badges that expand) — background tint shift, 1px border color shift, or the shadow raise above, all under 200ms. Do not add scroll-triggered or on-load entrance animations; motion should only ever respond to something the user does (hover, click, expand, confirm).
> - Rebuild the sidebar navigation, top tab bar, badge/pill system, tables, forms, and the ContextGraph answer card (pillar rows, confidence badge, session strip) using the token system and component specs in the attached plan.
> - Keep the bracket-style admin sub-tabs (`[USERS]`, `[RBAC]`, `[AUDIT]`, `[INGEST]`) only if the team wants to preserve that "system console" feel for power users; otherwise convert them to sentence case with icons for full consistency with the rest of the app (recommended).
>
> **Don't:**
> - Don't strip out information density, collapse tables into cards, or remove functional metadata (timestamps, hashes, counts) in the name of "cleaning up."
> - Don't introduce a new accent color not in the token list below.
> - Don't use all-caps labels, added just for decoration, anywhere new.
> - Don't animate on page load — only on interaction.

---

## 3. Source-of-truth: what the login screen actually uses

These values were sampled pixel-by-pixel from the provided login screenshot (not estimated from memory), so they can be dropped straight into CSS variables or a Figma style library.

| Element | Sampled value | Notes |
|---|---|---|
| Left panel background | `#FAFAF8` | Near-white warm parchment, not pure white |
| Right panel background | `#F2EFE7` | Slightly deeper warm tan |
| Heading ("Welcome back") | `#15181D` | Near-black ink, serif typeface |
| Body / subtext | `#6B7280` | Neutral gray |
| Form labels | `#3B4149` | Slightly darker than body text |
| Footer / muted copy | `#9AA1AC` | Lightest text tone still legible |
| Icon glyphs (mail, lock, eye) | `#A4AAB4` | Thin outline icons, muted gray |
| "Sign In" button fill | `#1F3A5F` | **The single navy accent — used nowhere else on this screen except the "Forgot password?" link** |
| "Forgot password?" link | `#1F3A5F` | Same navy, confirming navy (not rust) is the product's real accent color |
| Emblem line art / star accent | `#D4C9B3` – `#DCD2C3` | Decorative gold-tan, very low contrast, used once |
| Border radius (button, logo mark) | ~8–10px | Consistent throughout |
| Input style | Bottom border only, no box | 1px hairline, no fill |

**Important correction for the team:** a common assumption (and the current state of the rest of the app) is that this product's accent color is rust/terracotta. **It is not.** The login screen's only accent color is navy. The rust tones currently used for the Send button, active tab text, and avatar circle in the main app don't exist anywhere on the sign-in screen — that's the single biggest visual inconsistency to fix.

---

## 4. Current state audit (from the provided screens)

| Screen | What's inconsistent with the login theme |
|---|---|
| Chat Assistant (ContextGraph answer) | Rust "Send" button and rust active-tab text where login uses navy; 🔴/⚡/✓/🕸 emoji used as functional status icons; five badge colors (green, two shades of tan, blue) with no clear hierarchy; no shadow/elevation on the answer card |
| Admin → Users | Sidebar nav icons are all emoji (💬🎯⚠️📁🔧🌐); flat table with no row hover state; primary button ("Save User Profile") is rust, not navy |
| Admin → RBAC | "YES / NO" rendered as plain text — hard to scan; no icon; table has no visual hierarchy between the matrix and the security-policy text block below it |
| Admin → Audit & Governance | 🎨/🧠-style emoji on "Cognitive Intent Cache"; raw JSON Lines dumped as monospace text with no formatting; five colored domain-partition badges compete with each other; buttons ("Refresh Stats", "Clear All") have no icon-to-label pairing convention |
| Admin → Ingest | ✨ and 📄-style emoji in the ingestion log; "Confirm / Reject" buttons for supersession edges are plain outline buttons with no color meaning (Confirm should read as an affirmative/navy action, Reject as the one destructive/terracotta action) |
| Analytics | Chart colors (dark gray + rust) don't reference the navy/gold palette; empty-state banner uses a flat warning-yellow block with no icon |
| Sidebar (global) | Active nav item uses a peach/rust tint instead of the pale-navy tint that would match the login's single-accent system; every icon is an emoji glyph at inconsistent visual weight |

---

## 5. Design tokens

### 5.1 Color

```css
/* Neutrals — warm parchment family, sampled from login screen */
--color-canvas:        #FAFAF8;  /* app background */
--color-surface:        #FFFFFF; /* cards, sidebar, modals — sits "above" canvas */
--color-surface-tan:    #F2EFE7; /* secondary panels, empty states, right-rail */
--color-surface-tan-deep:#EDE6D8; /* illustration/emblem backgrounds only */

/* Ink */
--color-ink-900: #15181D; /* headings, primary text */
--color-ink-700: #3B4149; /* labels, strong secondary text */
--color-ink-500: #6B7280; /* body copy, descriptions */
--color-ink-400: #9AA1AC; /* muted / disabled / timestamps */
--color-border:  #E4E1D8; /* hairline dividers, table rules, input underlines */

/* The one accent */
--color-navy-900: #16283F; /* hover/active state of navy elements */
--color-navy-700: #1F3A5F; /* primary buttons, links, active nav, focus ring */
--color-navy-100: #E7ECF2; /* pale tint — active nav background, selected rows */

/* Decorative only (emblem, dividers on marketing-style empty states) */
--color-gold-300: #D9CFC1;
--color-gold-500: #C9BBA0;

/* Restrained semantic set — desaturated to sit inside the same warm palette */
--color-success-bg:   #E4EEE1;
--color-success-text: #3F6B42;
--color-warning-bg:   #F3E4C9;  /* keep — already harmonizes with the tan palette */
--color-warning-text: #8A6229;
--color-danger-bg:    #F5E4E1;
--color-danger-text:  #9C4A3A;  /* the only place a terracotta-family color survives: destructive actions */
--color-info-bg:      #E7ECF2;  /* reuses navy-100 rather than introducing blue */
--color-info-text:    #1F3A5F;
```

**Rule of one accent:** navy is the only color allowed on a primary button, an active tab, a selected nav item, a link, or a focus ring. Green/gold/terracotta are reserved exclusively for status meaning (success/warning/danger) — never for navigation or emphasis.

### 5.2 Typography

```css
--font-serif: "Source Serif 4", "Lora", Georgia, serif;   /* page titles / hero moments only */
--font-sans:  "Inter", -apple-system, "Segoe UI", sans-serif; /* everything else */

--text-display: 600 32px/1.2 var(--font-serif);  /* e.g. a "Welcome, Sarah" moment, empty states */
--text-h1:      600 24px/1.3 var(--font-serif);  /* page titles: "Admin Panel & Enterprise RBAC Governance" */
--text-h2:      600 16px/1.4 var(--font-sans);   /* section headers: "Active User Profiles" */
--text-body:    400 14px/1.6 var(--font-sans);
--text-small:   400 13px/1.5 var(--font-sans);
--text-label:   500 13px/1.4 var(--font-sans);   /* form labels, table headers — sentence case, never all-caps */
```

Using the serif *only* for page titles (not for every card heading) keeps it feeling like an intentional accent — exactly how the login screen uses it once, for "Welcome back," and nowhere else.

### 5.3 Elevation

```css
--shadow-resting: 0 1px 2px rgba(21,24,29,0.04);
--shadow-sm:      0 2px 6px rgba(21,24,29,0.06), 0 1px 2px rgba(21,24,29,0.04);
--shadow-hover:   0 6px 16px rgba(21,24,29,0.08), 0 2px 4px rgba(21,24,29,0.04);
--shadow-focus:   0 0 0 3px rgba(31,58,95,0.25); /* navy focus ring, accessibility-required */
```

Every card and interactive surface starts at `--shadow-sm` and raises to `--shadow-hover` on hover/focus — never bigger than that. No glows, no colored shadows.

### 5.4 Shape & spacing

```css
--radius-sm:   6px;   /* inputs, chips, small icon buttons */
--radius-md:   10px;  /* buttons, cards, table containers */
--radius-lg:   14px;  /* modals, large panels */
--radius-pill: 999px; /* status badges, avatar, "Coming soon"-style tags */

--space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
--space-6: 24px; --space-8: 32px; --space-12: 48px;
```

### 5.5 Motion

```css
--ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
--duration-fast: 120ms;  /* hover color/shadow changes, button press */
--duration-base: 180ms;  /* tab underline slide, badge expand */
--duration-slow: 240ms;  /* modal/drawer open only */
```

**Motion rule:** animate only in response to a user action (hover, click, expand, confirm, tab switch). No fade-in/slide-up choreography on page load or scroll — that reads as generic and adds no information. A tab's underline sliding to its new position, a card lifting 2px on hover, a button darkening on press, an accordion smoothly expanding — that's the entire motion vocabulary this app needs.

---

## 6. Icon system

**Library:** [Lucide](https://lucide.dev) (MIT-licensed, visually a near-exact match to the mail/lock/eye icons already on the login screen — thin stroke, rounded caps, no fill).
**Default size:** 18px inline (nav, buttons, table cells), 20px in card headers, 1.5px stroke weight.
**Color:** inherits `--color-ink-400` at rest, `--color-navy-700` when active/selected, never colored per-icon just for decoration.

### 6.1 Sidebar navigation

| Current | Replace with (Lucide) |
|---|---|
| 💬 Chat Assistant | `MessageSquare` |
| 🎯 Compliance Scorecard | `ShieldCheck` |
| ⚠️ Violations Explorer | `AlertTriangle` |
| 📁 Fund Schemes Matrix | `LayoutGrid` |
| 🔧 Remediation & SLA | `Wrench` |
| 🌐 Multi-Jurisdiction | `Globe2` |

### 6.2 Top tab bar

| Current | Replace with |
|---|---|
| 💬 Chat | `MessageCircle` |
| ⚖️ Compare | `Scale` |
| 📊 Analytics | `BarChart3` |
| 👥 Admin & Governance | `UserCog` |

### 6.3 Admin sub-tabs (if kept as icon + label instead of bracket text)

| Current | Replace with |
|---|---|
| [USERS] User Profile Management | `Users` |
| [RBAC] Role Access Matrix | `KeyRound` |
| [AUDIT] Security & Audit Logs | `FileClock` |
| [INGEST] Authorized Ingest & Pipeline | `UploadCloud` |

### 6.4 In-content icons

| Current | Replace with | Notes |
|---|---|---|
| 🔴 status dot on "ContextGraph" | CSS status dot (`8px` filled circle, `--color-navy-700` or `--color-success-text` depending on state) | Not an icon — a styled `<span>`, so its color can carry meaning |
| ⚡ next to every Pillar row | A small filled diamond bullet (◆, as inline SVG) in `--color-gold-500` | Deliberately echoes the diamond at the center of the login emblem — a small, intentional brand callback rather than a generic bullet |
| ✓ HIGH CONFIDENCE | `CheckCircle2`, `--color-success-text` | Pair with the existing pale-sage badge background |
| ▶ expand arrows | `ChevronRight` (collapsed) / `ChevronDown` (expanded), animated rotation over `--duration-base` | |
| 🕸 Graph Triplet Path | `Share2` | |
| 📄 file rows (e.g. "April 2025.pdf") | `FileText` | |
| ✨ "Indexing Finished!" | `CheckCircle2` in success color, not a sparkle | |
| 🧠/🎨 "Cognitive Intent Cache" panel header | `Database` (cache) — keep the "green AI" framing in copy, not in an icon | |
| 🗑 "Clear Intent Cache" | `Trash2`, styled as the destructive/tertiary button variant | |
| ➕ "New chat" | `Plus` | |
| YES / NO in RBAC matrix | `Check` (navy) / `Minus` (muted gray) icons instead of plain text — faster to scan a matrix visually | |

---

## 7. Component specs

### 7.1 Buttons

| Variant | Use for | Style |
|---|---|---|
| **Primary** | Sign In-equivalent actions: "Send," "Save User Profile," "Ingest & Index Document," "Run Production Ingestion Pipeline," "Confirm" | Solid `--color-navy-700` fill, white text, `--radius-md`, `--shadow-sm` at rest → `--shadow-hover` + `--color-navy-900` fill on hover, `--duration-fast` transition |
| **Secondary** | "Refresh Stats," "Refresh Status," "Browse files" | 1px `--color-navy-700` border, transparent fill, navy text; on hover, fill with `--color-navy-100` |
| **Tertiary / ghost** | "Sign out," in-card links, "Preview Compliance Report" | No border/fill, navy text, underline appears on hover only |
| **Destructive** | "Delete Selected Profile," "Reject," "Clear All" | Solid `--color-danger-text` fill (muted terracotta) — the *only* place this hue is used for an action, so it reads as a genuine warning rather than a brand color |

All buttons: `--radius-md`, `14px` label at `--text-label` weight, `8px` icon-to-label gap when an icon is present, `1px` `--color-navy-700` focus ring offset by 2px on keyboard focus.

### 7.2 Sidebar navigation

- Rest state: `--color-ink-500` text and icon, no background.
- Hover: `--color-surface-tan` background, `--duration-fast`.
- Active: `--color-navy-100` background, `--color-navy-700` text and icon, a 2px navy left-edge indicator bar (not a full color fill) — quieter than the current solid peach block.

### 7.3 Top tab bar

- Inactive: `--color-ink-500` text, icon at `--color-ink-400`.
- Active: `--color-navy-700` text and icon, 2px underline in `--color-navy-700` that **slides** between tabs on click (`--duration-base`, `--ease-standard`) rather than just appearing.

### 7.4 Cards / panels (e.g. the ContextGraph answer card)

- `--color-surface` background, `--radius-md`, `--shadow-sm` at rest.
- Header row: session/model badge (e.g. "HYBRID GRAPH + VECTOR") restyled as a single pale-navy pill instead of a solid dark block, `--text-label`, sentence case instead of tracked-out caps.
- Pillar rows: replace the five different badge-background colors with **one consistent card row style** (`--color-surface-tan` background, `--radius-sm`, diamond bullet per §6.4) and let *only the confidence badge* carry a semantic color (success/warning/danger). Right now every row is a different color and nothing stands out — giving the whole card one quiet visual rhythm makes the one thing that should stand out (confidence level) actually stand out.
- On hover (if the card is expandable): raise to `--shadow-hover`, `--duration-fast`.

### 7.5 Badges / status pills

- Shape: `--radius-pill`, `12px` horizontal padding, `--text-small`.
- Palette: exactly the four semantic pairs in §5.1 — no other badge colors anywhere in the product.
- Icon-left convention: every badge gets a matching 14px icon (`CheckCircle2` / `AlertTriangle` / `Info` / `XCircle`) so meaning doesn't rely on color alone (accessibility).

### 7.6 Tables (Admin Users, RBAC Matrix, Analytics run history)

- Header row: `--color-ink-700`, `--text-label`, `--color-surface-tan` background, bottom border `1px --color-border`. Sentence case, not all-caps.
- Body rows: `--color-surface` background, `1px --color-border` row dividers (no zebra striping — it fights the warm neutral palette).
- Row hover: `--color-surface-tan` background over `--duration-fast` — signals interactivity where rows are clickable (e.g. selecting a user).
- Boolean cells (YES/NO): `Check`/`Minus` icons per §6.4 instead of text, center-aligned.

### 7.7 Forms (Create/Update User Profile, Document Ingest)

- Inputs match the login screen exactly: bottom-border only (`1px --color-border`, `2px --color-navy-700` on focus), no filled box, `8px` left icon where relevant (e.g. a `Mail` icon on an email field), label above in `--text-label`.
- Dropdowns: same underline treatment, `ChevronDown` icon right-aligned.
- File upload dropzone: dashed `1px --color-border`, `--radius-md`, `--color-surface-tan` background on drag-over, `UploadCloud` icon centered rather than a plain folder glyph.

### 7.8 Avatar / user menu

- Replace the rust-filled "SJ" circle with a `--color-navy-700` filled circle, white initials, `--text-label` weight — matching the single-accent rule and giving better contrast.

### 7.9 Empty / info states (e.g. "Run a query in the Compare tab first")

- `--color-surface-tan` background, `--radius-md`, `Info` icon in `--color-info-text`, no harsh yellow block. Reserve the yellow/warning tone strictly for the warning semantic, not for neutral "nothing here yet" messaging.

---

## 8. Motion & micro-interaction spec

| Interaction | Behavior | Duration |
|---|---|---|
| Button hover | Fill darkens one step (`navy-700` → `navy-900`) or border/background tint appears | 120ms |
| Button press | Scale to 98%, shadow drops to `--shadow-resting` | 100ms |
| Card hover (if clickable) | `--shadow-sm` → `--shadow-hover`, 1px lift via `transform: translateY(-1px)` | 150ms |
| Tab switch | Underline bar slides to new position; label color crossfades | 180ms |
| Sidebar nav select | Left indicator bar slides vertically to the new active item | 180ms |
| Accordion / pillar detail expand | Height auto-animates, chevron rotates 90° | 180ms |
| Toast / confirmation (e.g. "Indexing Finished") | Slide up 8px + fade in on appearance only, no ongoing motion | 200ms |
| Focus (keyboard) | Navy focus ring fades in | 100ms |

Nothing in this table triggers on scroll or on page load — every entry is a direct response to something the person did.

---

## 9. Accessibility & quality floor

- Every color pairing above meets **WCAG AA** for text-on-background (navy-700 on parchment ≈ 8.6:1; ink-500 on white ≈ 4.6:1).
- Color is never the only signal: badges and boolean table cells always pair an icon with the color.
- All interactive elements get a visible keyboard focus ring (`--shadow-focus`) — currently absent from the screenshots reviewed.
- Respect `prefers-reduced-motion`: fall back to instant state changes (no slide/fade) when set.
- Icon-only buttons (e.g. trash, refresh) get an accessible label via `aria-label`, not just a tooltip.

---

## 10. Implementation phases

1. **Tokens first.** Land the CSS variables in §5 as a single source of truth (design tokens file / Tailwind theme extension) before touching any component — this is what prevents the "five accent colors" problem from recurring.
2. **Icon swap.** Replace every emoji with the Lucide mapping in §6. This alone will visibly move the app toward the login screen's tone even before color/shadow work lands.
3. **Global chrome.** Sidebar nav, top tab bar, avatar — highest-visibility surfaces, seen on every screen.
4. **Buttons + badges.** Apply the four-variant button system and the four-pair semantic badge system everywhere; this is where the rust→navy correction happens.
5. **Cards + tables + forms.** Roll out elevation, hover states, and the form input style.
6. **Motion pass.** Add the micro-interactions in §8 last, once the static states are correct — motion should refine already-correct components, not compensate for unfinished ones.
7. **Audit pass.** Screenshot every screen side-by-side with the login screen and check: one accent color, no emoji, consistent shadow depth, consistent radius, sentence case throughout.

---

## 11. Quick recap: what changes, what doesn't

**Changes:**
- Every emoji → a real outline icon (Lucide)
- Rust as the "primary action" color → navy is the one accent, rust survives only as the destructive-action color
- Five unrelated badge colors → four disciplined semantic pairs
- Flat, shadowless cards → consistent small resting shadow + subtle hover lift
- Static UI → small, purposeful hover/click/expand animations only
- All-caps bracket admin tabs → sentence case + icon (recommended, optional to preserve as a deliberate "power user console" cue)

**Stays exactly the same:**
- Information density — every table, log, and metric stays visible
- The warm parchment/cream base palette (it already matches the login screen well)
- The overall layout and navigation structure
- The serif-for-headline / sans-for-body pairing convention, extended app-wide from where it currently only exists on the login screen
