# Login Screen — Design & Implementation Plan
**Project:** mf-context-engine (AMC Context Engineering RAG Frontend)
**Status:** Planning only — nothing in this document has been built yet.
**Scope:** A pre-app authentication gate, backed by a static JSON user file (no database), that hands control to the existing `AppState.jsx` / `ROLE_PERMISSIONS` system once a user signs in.

---

## 1. Objective

Today the app trusts `DEFAULT_USER_PROFILES[0]` on load and lets people switch roles from a sidebar dropdown — there is no gate. This plan adds a real login screen in front of that, so:

- A person must authenticate before the Chat / Compare / Analytics / Admin views render.
- Credentials are checked against a **static JSON file** (`users.json`), not a database. This is explicitly a POC/demo auth layer, not production security (see §8).
- Once authenticated, the existing role-permission machinery (`ROLE_PERMISSIONS`, `activeUser`) takes over unchanged — the login screen only decides *who* `activeUser` is at session start.
- The screen itself should read as considered and specific to a regulatory/financial product — not a generic centered-card SaaS template.

---

## 2. What "not vibe-coded" means here, concretely

Rejected by default, unless justified:
- Centered white card, drop shadow, rounded-corners-on-everything, gradient background.
- A logo + "Welcome back" + email + password + "Forgot password?" + "Remember me" + social-login row. Half of that is dead weight for a 5-user internal POC.
- Cliché AI-generated tells: warm cream background with terracotta accent (#D97757-ish), all-caps tracked-out eyebrow labels, a "→" on the button, middle-dot separators.

Kept, deliberately:
- Only two inputs: **User ID** and **Password**. No email format, no "remember me", no forgot-password flow (this is a closed set of 5 predefined operator accounts, not public registration).
- One primary action: **Sign in**.
- One quiet, real piece of feedback: role name appears only *after* successful auth, briefly, as confirmation — not before (this file describes it as part of the success transition, §5.4).
- No decorative illustration, no marketing copy, no carousel. The screen's only job is authentication.

---

## 3. Grounding the visual identity in the subject matter

This is not a generic SaaS login — it's the entry point to a **regulatory document intelligence system for a mutual fund AMC** (SEBI circulars, compliance provenance, audit trails, role-gated access). The existing app (`streamlit-theme.css`) already uses a warm paper-like light theme (`#F8F7F3`, dotted texture, Source Sans Pro) for the *working* app. The login screen is the front door — it can hold a different, more deliberate register than the working canvas behind it, the way a bank's lobby looks different from the teller floor.

**Direction chosen:** an ink-dark, ledger/seal-inspired screen — dark charcoal-navy field, a single warm brass/gold accent (evoking an official stamp, a compliance seal, a wax-sealed circular), restrained serif for the wordmark, sans-serif for the working UI. This is distinct from the light working app (giving the login "impact" through contrast) while staying thematically anchored to regulatory/audit material rather than generic tech-startup style.

Why not the existing light cream palette for login too: reusing the exact same light theme would make the login screen feel like "just another tab" instead of a threshold moment. The dark ink field is also where the one animation (§5) gets to read clearly.

---

## 4. Design tokens

### 4.1 Color
| Token | Hex | Use |
|---|---|---|
| `--ink-950` | `#12141C` | Page background (deep ink-navy, not pure black) |
| `--ink-900` | `#1A1D28` | Card / panel surface |
| `--ink-800` | `#242837` | Input field background |
| `--hairline` | `rgba(232, 227, 214, 0.10)` | Borders, dividers |
| `--parchment` | `#EFE9DC` | Primary text on dark (warm off-white, not pure white) |
| `--parchment-dim` | `rgba(239, 233, 220, 0.55)` | Secondary text, placeholders |
| `--seal` | `#B08D57` | Single accent — brass/seal gold. CTA, focus ring, the seal glyph |
| `--seal-hover` | `#C29F6C` | Hover/active state of accent |
| `--error` | `#D9756B` | Error text/border only — muted clay-red, not alarm-red |

Only **one** accent color (`--seal`) is used. No gradients.

### 4.2 Type
- **Wordmark / heading:** a single serif, e.g. `"Source Serif 4"` or `"Lora"` (already loadable via Google Fonts, same delivery mechanism the app already uses for Source Sans Pro) — set at a restrained size, not oversized hero type. It carries the "seal/ledger" feeling.
- **UI text (labels, inputs, buttons, helper text):** `"Source Sans Pro"` — same family the rest of the app already uses, so the login doesn't introduce a third typeface into the product.
- No all-caps labels. Sentence case throughout ("User ID", not "USER ID").

### 4.3 Layout
Left-aligned, not centered-card. A centered card is the #1 login cliché; an asymmetric split reads more like a considered product.

```
┌───────────────────────────────────────────────────────────┐
│  ink-950 field, faint concentric seal-ring motif           │
│  bleeding off the right edge (static SVG, low opacity)     │
│                                                              │
│   ⬩ AMC Context Engine                                      │
│     Regulatory intelligence, with provenance.               │
│                                                              │
│     User ID                                                 │
│     [__________________________]                            │
│                                                              │
│     Password                                                │
│     [__________________________]  👁                        │
│                                                              │
│     [        Sign in        ]                               │
│                                                              │
│     ⌐ role-mismatch / bad-credential message appears here   │
│                                                              │
└───────────────────────────────────────────────────────────┘
```

- Content column is left-aligned, max-width ~360px, positioned left-of-center on desktop (roughly 40/60 split), so the right side of the viewport carries the quiet seal-ring graphic and negative space — not another content block.
- On mobile (< 640px): single column, seal-ring motif shrinks and moves behind/above the form at low opacity rather than disappearing outright.
- Generous vertical rhythm (24–32px between field groups) rather than a dense stacked form — reinforces "minimal, only required information."

### 4.4 Shadow ("little bit of shadows")
Restrained, not the generic soft-grey SaaS card shadow:
- Input fields: no shadow at rest; on focus, a **1px seal-colored border + 3px soft outer glow** (`box-shadow: 0 0 0 3px rgba(176, 141, 87, 0.15)`) instead of a drop shadow — reads as precision, not depth.
- Sign-in button: a single low, tight shadow (`0 1px 2px rgba(0,0,0,0.4)`) at rest, slightly lifting (`0 4px 10px rgba(0,0,0,0.35)`) on hover — subtle elevation change, not a floaty card shadow.
- The seal-ring background motif itself can cast a very faint inner shadow to feel etched rather than flat, since it's the one "designed" graphic on the page.

### 4.5 Motion ("small animation")
One deliberate moment, not scattered hover effects everywhere:
- **On page load:** the concentric seal-ring graphic performs a single slow rotation-settle (rotates a few degrees and eases to rest, ~900ms, `ease-out`, once — not looping). This is the "one orchestrated moment" the brief allows for, and it's thematically a "seal locking into place," reinforcing the authentication metaphor.
- **On successful sign-in:** the form doesn't just redirect — the seal-ring completes a short final rotation/click-into-place (~400ms) simultaneously with the form fading/sliding out, then the working app fades in. This is the "more impact" moment for success, using motion to represent the auth event rather than a decorative flourish.
- **Hover effects (small, as requested):** input border color shift (150ms), button background lightening + 1px lift (150ms), password-visibility icon opacity shift. All under 200ms, no bounce/elastic easing — precision, not playfulness.
- Respect `prefers-reduced-motion`: fall back to instant state changes, no rotation animation.

---

## 5. Interaction & content spec

### 5.1 Fields
- **User ID** — plain text input, placeholder `e.g. sarah.compliance`, autofocus on mount.
- **Password** — password input with a show/hide toggle (eye icon), no strength meter (not applicable to predefined accounts).
- No "remember me" checkbox. Session persists via the existing `localStorage`-backed pattern already used elsewhere in `AppState.jsx` (`safeStorageGet`/`safeStorageSet`), keyed as a new `STORAGE_KEYS.AUTH_SESSION` (or similar) — see §7.

### 5.2 Validation & errors
- Client-side only (this is a static-JSON demo auth layer): check submitted User ID + password against `users.json`.
- Empty-field submit: inline helper text under the relevant field ("Enter your user ID"), not a toast/banner.
- Wrong credentials: a single quiet message below the form — **"That User ID or password doesn't match our records."** — never confirm which of the two was wrong (baseline good practice, costs nothing here).
- No lockouts/rate-limiting needed for a 5-user POC, but note it in §8 as an intentionally-omitted production concern.

### 5.3 Copy
- Heading: **"AMC Context Engine"**
- Subhead (one line, quiet, under the heading): **"Regulatory intelligence, with provenance."** — ties to the product's actual differentiator (citation/provenance), not generic marketing ("Welcome back!").
- Button: **"Sign in"** (not "Submit" / "Login →").
- No footer legal text, no "Powered by" line — internal POC tool, doesn't need it.

### 5.4 Success transition
On successful match: button shows a brief inline confirmation state (label swaps to the person's **display name**, e.g. "Signing in as Sarah Kapoor…", for ~500ms) before the transition animation (§4.5) hands off to the main app. This is the one place identity is echoed back — deliberately *after* auth succeeds, not before, and never showing role/username lists anywhere else in the UI (per your instruction not to expose users/passwords in the frontend).

---

## 6. Predefined users — data model (no database)

New file: `mf-context-engine/src/data/users.json` (static, bundled with the frontend; not fetched from any backend or DB for this phase).

Maps 1:1 onto the **5 AMC organizational roles already defined** in the RBAC docs (`Docs/Enterprise Role-Based Access Control (RBAC) & AMC Admin Panel_v1.md`) and the sample usernames already referenced in `AppState.jsx`'s mock audit log (`sarah_compliance`, `vikram_pm`, `ananya_esg`, `rahul_sales`), plus one Retail Investor account to complete the set of 5:

| # | Role | Access level | Username pattern |
|---|---|---|---|
| 1 | Compliance & Regulatory Officer | Level 1 — full access + Admin Panel | `sarah.compliance` |
| 2 | Fund Manager / Portfolio Manager | Level 2 — investment scope | `vikram.pm` |
| 3 | ESG & Sustainability Analyst | Level 3 — ESG scope | `ananya.esg` |
| 4 | Sales & Distribution Manager | Level 4 — commercial scope | `rahul.sales` |
| 5 | Retail Investor / Public Client | Level 5 — restricted public scope | `priya.investor` |

**Record shape (per user):**
```json
{
  "username": "sarah.compliance",
  "password": "•••••••• (see chat, not written here)",
  "display_name": "Sarah Kapoor",
  "role": "Compliance & Regulatory Officer",
  "avatar_initials": "SK"
}
```

- The **Compliance & Regulatory Officer** account is the one with `can_view_admin_panel: true` in `ROLE_PERMISSIONS` (per existing `App.jsx` logic) — this is effectively "the admin user" the task refers to; there's no separate generic `admin` account, since the RBAC model is role-based rather than a single superuser.
- Passwords: plain strings in the JSON for this phase (explicitly not production-safe — see §8). I'll give you all 5 User ID + password pairs in the chat reply, not in this file or in any frontend-visible location, per your instruction.
- This file lives under `src/data/`, is imported directly (`import USERS from "../data/users.json"`), and is **never rendered** anywhere in the UI — no "demo accounts" hint box on the login screen itself.

---

## 7. Wiring into the existing app (no new architecture, extends what's there)

1. **New state:** in `AppState.jsx`, add `isAuthenticated` (bool) + `authedUsername`, persisted the same way `activeUsername` already is (`safeStorageGet`/`safeStorageSet`). On successful login, this also sets `activeUsername` to the matched user — so the existing `activeUser` / `activePermissions` memoized values downstream in `App.jsx` need no changes at all.
2. **New component:** `src/components/auth/LoginScreen.jsx` (+ `LoginScreen.css`), self-contained — owns its own form state, does the lookup against `users.json`, and on success calls a new `login(username, password)` helper exposed from `AppState.jsx`.
3. **Gate in `App.jsx`:** at the top of the existing `export default function App()`, branch: `if (!isAuthenticated) return <LoginScreen />;` before any of the existing tab/sidebar rendering.
4. **Logout:** a small, unobtrusive control (e.g. in the existing `Sidebar.jsx`, near the current profile switcher) that clears `isAuthenticated` and returns to `LoginScreen` — not in scope of the login screen itself, but noted since it's the natural counterpart.
5. **No changes needed** to `ROLE_PERMISSIONS`, `ROLE`-gated tab logic in `App.jsx`, or any admin view — they already key off `activeUser.role`, which the login screen now populates correctly at session start instead of defaulting to index 0.

This keeps the login screen additive: one new component + a few new state fields, nothing existing gets rewritten.

---

## 8. Explicit non-goals / caveats (read before building)

- **This is not real authentication.** Passwords live in a plain JSON file shipped to the client bundle; anyone who opens devtools/network tab can read `users.json` in full, credentials included. That's acceptable for an internal POC with 5 known operators, but must not be mistaken for a security boundary. Real deployment would need server-side auth (hashed passwords, session tokens, backend-verified) — explicitly out of scope per your instruction not to touch SQLite/DB yet.
- No password reset, no lockout/rate-limiting, no MFA, no audit logging of login attempts (the existing mock audit log in `AppState.jsx` is unrelated sample data, not a real log).
- No new backend endpoints. Everything above is frontend-only, static-JSON-backed.

---

## 9. File-level checklist (for the future implementation pass — not done now)

- [x] `src/data/users.json` — 5 predefined user records
- [x] `src/components/auth/LoginScreen.jsx` — form, validation, success transition
- [x] `src/components/auth/LoginScreen.css` — tokens from §4, scoped to this component
- [x] `src/components/auth/SealMotif.jsx` (or inline SVG) — the concentric seal-ring graphic + load/success animation
- [x] `AppState.jsx` — add `isAuthenticated`, `authedUsername`, `login()`, `logout()`, new `STORAGE_KEYS` entry
- [x] `App.jsx` — gate at top of component
- [x] `Sidebar.jsx` — small logout affordance (secondary, not part of this plan's visual spec)

---

## 10. Accessibility notes for the build pass

- All interactive elements reachable by keyboard in a sane tab order (User ID → Password → show/hide toggle → Sign in).
- Visible focus states use the `--seal` ring described in §4.4, not the browser default outline removed with nothing to replace it.
- Error message associated with the form via `aria-live="polite"` so it's announced without moving focus.
- Color contrast: `--parchment` on `--ink-950`/`--ink-900` and `--seal` on `--ink-950` both need a contrast check against WCAG AA at build time (brass-on-dark-navy is likely fine for large text/buttons; verify for the smaller helper text specifically).
