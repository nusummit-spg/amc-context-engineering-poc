# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

## 📦 **Deliverables Overview**

### **1. Architecture & User Flows**
- **Authentication Layer**: JWT + refresh tokens, MFA support, role-based access control
- **4 Role-Based Dashboards**: AMC Manager, Portfolio Analyst, Compliance Officer, Financial Advisor
- **Component Hierarchy**: Clear separation of concerns (auth, layout, pages, components, services)

### **2. Detailed Wireframes (6 Major Screens)**

| Screen | Purpose | Key Features |
|--------|---------|--------------|
| **Login Page** | Initial auth | Email/password, SSO options, 2FA |
| **Comparison Showcase** | Hero feature | Traditional RAG vs ContextGraph side-by-side, performance metrics |
| **Multi-Turn Chat** | Dedicated chatbot | Session history, parallel query execution, streaming |
| **Citation Panel** | Trust builder | Sources, document provenance, audit trail, download |
| **Analytics Dashboard** | Management view | Query trends, user activity, cost savings, ROI metrics |
| **Admin Panel** | User management | RBAC, audit logs, feature flags, compliance reports |

### **3. Design System**
- **Color Palette**: Warm, earthy tones (rust #A8412C, warm cream #F8F7F3, forest green #3F6B42)
- **10+ Reusable Components**: QueryBox, ResultPanel, CitationPanel, MetricsCard, SessionSelector, UserMenu, ActivityLog, etc.
- **Typography**: Clean, accessible hierarchy (14px bold headers, 13px body, 10.5px labels)
- **Responsive Design**: Mobile-first approach (xs, sm, md, lg, 2xl breakpoints)

### **4. State Management Architecture**
- **Zustand Stores**: `authStore`, `sessionStore`, `uiStore`, `analyticsStore`
- **Type-Safe API Clients**: Axios with JWT interceptors, retry logic, token refresh
- **React Query Integration**: Caching, background sync, optimistic updates

### **5. User Activity Tracking** 
**7 PostgreSQL Tables**:
- `activity_logs`: Every query, click, feedback (with JSONB metadata)
- `audit_trail`: Auth events, role changes, system access
- `sessions`: Active/expired user sessions with IP, user agent
- `query_analytics_daily`: Rollups for dashboards
- `user_feedback`: Ratings linked to specific queries
- `feature_flags`: A/B testing and gradual rollouts

**Events Captured**:
- `query_executed` (latency, cost, tokens, satisfaction)
- `citation_interacted` (hover, click, download)
- `session_created/saved`
- `export_action` (format, content type)
- `login/logout` (with device fingerprint)

### **6. API Contracts**
**New endpoints to implement**:
- `POST /api/activity/log` — Client-side event tracking
- `GET /api/activity/history` — Query history with filters
- `GET /api/admin/audit-trail` — Compliance audit log
- `POST /api/feedback/rate` — User satisfaction ratings
- `GET /api/analytics/dashboard` — High-level KPIs
- **Auth**: `/api/auth/register`, `/api/auth/mfa/setup`, `/api/auth/refresh`

### **7. Component Translation Guide**
**From Streamlit → React patterns**:
- HTML-in-state → structured TypeScript components
- Color strings → CSS variables + Tailwind theme
- Parallel execution → `Promise.allSettled()`
- Collapsible details → Headless UI Disclosure
- Markdown rendering → `react-markdown`
- SVG graph viz → Cytoscape.js or Visx

### **8. Security & Compliance**
- **Frontend**: HTTPOnly cookies for tokens, CSRF protection, input sanitization
- **Backend**: Role-based route guards, audit logging, data retention policies
- **Database**: Partitioning for audit_logs (by month), soft deletes for users
- **Monitoring**: Prometheus metrics, DataDog alerts, anomaly detection

### **9. Implementation Roadmap**

**Phase 1 (Week 1)**: Foundation
- Scaffold Vite + React + Zustand
- Auth flow (login, JWT refresh, logout)
- Chat interface with session persistence
- Activity logging to PostgreSQL

**Phase 2 (Week 2)**: Enhanced Features
- Graph visualization (Cytoscape)
- Query history with export
- Error boundaries, skeleton loaders
- Admin dashboard (user list, basic metrics)

**Phase 3 (Week 3-4)**: Analytics & Polish
- Full analytics dashboard with charts
- Audit log viewer
- Performance optimization
- Security audit + deployment readiness

### **10. Tech Stack Recommendations**
```
Frontend:
  • Vite (blazing fast builds)
  • React 18 + TypeScript
  • Zustand (lightweight state)
  • TanStack Query (data fetching)
  • Tailwind CSS (styling)
  • Headless UI (components)
  • Cytoscape.js (graph viz)
  • Recharts (dashboards)
  • Vitest + Playwright (testing)

Backend (Additions):
  • PostgreSQL (activity logs)
  • Redis (session cache)
  • Celery (async logging)
  • Prometheus (metrics)
  • ELK/DataDog (logging)
```

---

## 🎯 **Key Design Principles**

1. **Preserve Streamlit's Warmth**: Keep the earthy, accessible color palette
2. **Parallel Execution**: Render faster pipeline result before slower, avoid waiting
3. **Session Persistence**: Resume any chat by ID, auto-save after each turn
4. **Trust Through Citations**: Every claim linked to sources, fully auditable
5. **Role-Based Simplicity**: Each role sees only what they need
6. **Activity Intelligence**: Every user action tracked for analytics + compliance
7. **Performance First**: Stream responses, lazy load, cache aggressively

---

## 🚀 **Next Steps**

1. **Design Review**: Share wireframes with stakeholders for feedback
2. **Prototype**: Create interactive Figma prototype for user testing
3. **Database Setup**: Deploy PostgreSQL schema to staging environment
4. **API Implementation**: Add activity logging and admin endpoints to FastAPI
5. **Frontend Build**: Initialize Vite + React, build auth flow first
6. **Integration**: Connect frontend to existing backend
7. **Testing**: Unit (Vitest) + E2E (Playwright) coverage
8. **Deployment**: CI/CD pipeline, load testing, canary rollout

---

**All design decisions are grounded in your existing Streamlit codebase patterns and tailored to your multi-role user base (AMC managers, portfolio analysts, compliance officers, financial advisors).**
