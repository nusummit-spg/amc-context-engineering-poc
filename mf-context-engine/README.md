# MF Context Engine — React Frontend

> Modern React 19 + Vite 8 frontend for the AMC Context Engineering Platform.

---

## 🌟 Overview

The **MF Context Engine** frontend is the enterprise web client for compliance officers, fund managers, and administrators to interact with the ContextGraph hybrid retrieval system.

### Key Capabilities
- **Chat Interface**: Multi-turn conversation workspace with full provenance tracking and source citations.
- **Feedback & Repair Loop**: Category-aware feedback submission with non-blocking status resolution.
- **Admin & Governance**: Audit trails, evaluation metrics, and user feedback triage.
- **Compliance Guardrails**: PII-redacted inspection and SEBI regulatory circular verification.

---

## 🛠️ Technology Stack

- **Framework**: [React 19](https://react.dev/)
- **Bundler**: [Vite 8](https://vite.dev/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Linter**: [Oxlint](https://oxc.rs/)
- **Testing**: Node test runner (`node:test`) + [Playwright](https://playwright.dev/) for E2E

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` in this directory (or configure via root `.env`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE` | `http://localhost:8000` | Target backend API base URL |
| `VITE_ENABLE_FEEDBACK_STATUS_AWARENESS` | `true` | Non-blocking feedback status resolution check |
| `VITE_FEEDBACK_SIDEBAR_NAV_ENABLED` | `true` | Expandable sidebar navigation for feedback triage |
| `VITE_MY_FEEDBACK_PAGE_ENABLED` | `true` | Personal user feedback history page |
| `VITE_FEEDBACK_CATEGORY_BREAKDOWN_BANNER_ENABLED` | `true` | Category breakdown badges in feedback banner |

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Development Server
```bash
npm run dev
```
The application will be accessible at: [http://localhost:5173](http://localhost:5173). Requests to `/api` and `/files` are automatically proxied to the backend at `http://127.0.0.1:8000`.

### 3. Build for Production
```bash
npm run build
```
Production static assets will be output to `dist/`.

### 4. Run Tests & Linter
```bash
# Unit tests
npm test

# Linting
npm run lint
```
