# Architecture Guide: AMC Compliance Engineering Platform

## 1. System Overview

The platform is designed with a decoupled frontend-backend architecture:
- **Frontend**: React 18 single-page application bundled with Vite. Provides instantaneous interactive state updates, graph visualizations, live telemetry calculations, role-based navigation, and accessible interfaces.
- **Backend**: Python FastAPI service orchestrating a 7-step retrieval engine with Neo4j graph traversal and Qdrant vector retrieval.

---

## 2. Frontend Component Hierarchy

```
App
├── ErrorBoundary
│   └── NotificationProvider
│       └── UserProvider
│           └── SessionProvider
│               └── QueryProvider
│                   └── Router
│                       └── Layout
│                           ├── Header (Branding, User Status, Menu Toggle)
│                           ├── Sidebar (Navigation, User Switcher, Background Tasks, Clear Cache)
│                           ├── TabNavigation (Role-filtered tabs)
│                           ├── ToastContainer (Live alerts & task notifications)
│                           └── Routes (Suspense Boundaries)
│                               ├── ComparePage -> CompareTab
│                               │   ├── TraditionalPanel (Vector Search Results)
│                               │   │   ├── TelemetryCard
│                               │   │   └── DocumentCard
│                               │   └── ContextGraphPanel (Hybrid Synthesis)
│                               │       ├── ConfidenceBadge
│                               │       ├── ProvenanceSection
│                               │       ├── TelemetryCard
│                               │       └── GraphVisualizer
│                               ├── ChatPage -> ChatTab
│                               │   ├── SessionList
│                               │   └── ChatHistory (Multi-turn comparison)
│                               ├── AnalyticsPage -> AnalyticsTab
│                               │   ├── ScopeSelector
│                               │   ├── GraphVisualizer
│                               │   └── DualBarCharts (Latency & Tokens)
│                               └── AdminPage -> AdminTab
│                                   ├── UsersSubTab
│                                   ├── RBACSubTab
│                                   ├── AuditSubTab
│                                   └── IngestSubTab
```

---

## 3. Context Architecture & State Management

1. **UserContext**: Manages active user profile, role switching, and available sample personas.
2. **NotificationContext**: Manages global toast queue, automated auto-dismiss timers, and background notification polling.
3. **SessionContext**: Manages chat sessions, active session state, and disk persistence sync.
4. **QueryContext**: Manages comparison runs, latest query results for graph analytics, and metric history.
