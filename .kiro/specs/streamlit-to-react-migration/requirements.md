# Requirements Document: Streamlit to React Migration

## 1. Functional Requirements

### 1.1 UI Fidelity Requirements

**REQ-1.1.1**: The React application SHALL reproduce the Streamlit UI with 100% visual fidelity including exact colors, typography, spacing, borders, shadows, and all visual elements.

**REQ-1.1.2**: The color palette SHALL match exactly: background #F8F7F3, accent #A8412C, text #231F1C/#5C574C/#8A8378, borders #E7E1D4/#1C1917, surfaces #FFFFFF/#EFEAE0.

**REQ-1.1.3**: The background pattern SHALL be a radial gradient (#E5E0D8 1px dots on transparent) with 24px × 24px size.

**REQ-1.1.4**: Typography SHALL use 'Segoe UI', Arial, sans-serif with font sizes 10.5px, 11.5px, 13px, 14px, and 17px as specified.

**REQ-1.1.5**: Button styling SHALL match exactly: primary (#A8412C background, white text, #8C3523 border, 8px radius, 0.6rem/1.2rem padding) and secondary (#FFFFFF background, #E7E1D4 border, #5C574C text) with 2D flat appearance (no box-shadow).

**REQ-1.1.6**: Tab styling SHALL match: 24px gap, #8A8378 inactive color, #A8412C active color with 2px bottom border, 600 font-weight.

**REQ-1.1.7**: Input styling SHALL match: #EFEAE0 background, #E7E1D4 border, 8px radius, #A8412C focus border.

**REQ-1.1.8**: All hover, focus, active, and disabled states SHALL match the Streamlit implementation exactly.

### 1.2 Navigation & Routing Requirements

**REQ-1.2.1**: The application SHALL implement client-side routing with 4 main routes: /chat, /compare, /analytics, /admin.

**REQ-1.2.2**: The application SHALL display a tab navigation bar with icons: 💬 Chat, ⚖️ Compare, 📊 Analytics, 👥 Admin & Governance.

**REQ-1.2.3**: Tab visibility SHALL be filtered based on user RBAC permissions (e.g., Admin tab only visible to Compliance Officers).

**REQ-1.2.4**: When a user switches profiles and the active tab becomes hidden, the application SHALL redirect to the first visible tab.

**REQ-1.2.5**: The active tab SHALL persist across page refreshes using URL-based routing.

### 1.3 User Authentication & RBAC Requirements

**REQ-1.3.1**: The application SHALL support 5 AMC organizational roles: Compliance Officer, Fund Manager, ESG Analyst, Sales Manager, Retail Investor.

**REQ-1.3.2**: The sidebar SHALL display a user profile switcher dropdown with all available users.

**REQ-1.3.3**: The active user's name, role, and department SHALL be displayed below the dropdown.

**REQ-1.3.4**: User profile selection SHALL immediately update the UI to reflect the new user's permissions (tab visibility, data access).

**REQ-1.3.5**: Role permissions SHALL include: can_access_compare_tab, can_access_analytics_tab, can_view_admin_panel, can_view_audit_logs, can_view_unredacted_pii, can_run_cypher_tools.

**REQ-1.3.6**: Compliance Officers SHALL have all permissions enabled; Retail Investors SHALL have minimal permissions.

### 1.4 Chat Tab Requirements

**REQ-1.4.1**: The Chat tab SHALL display a query input field with placeholder text "Ask a follow-up — conversation context carries forward…".

**REQ-1.4.2**: The Chat tab SHALL provide 4 action buttons: "Send" (primary), "🔄 New Session", "🗑️ Clear Cache", arranged in 4.0:0.8:1.1:1.1 column ratio.

**REQ-1.4.3**: Clicking "Send" SHALL execute two parallel API calls: POST /api/chat with mode=traditional and mode=contextgraph.

**REQ-1.4.4**: The Chat tab SHALL display chat history in reverse chronological order (newest first).

**REQ-1.4.5**: Each turn SHALL be rendered as: user message header → two-column assistant response (Traditional | ContextGraph).

**REQ-1.4.6**: During query execution, the Chat tab SHALL display loading states: "Traditional RAG is generating…" (left), "ContextGraph is generating…" (right).

**REQ-1.4.7**: When one query completes before the other, its panel SHALL render immediately without waiting.

**REQ-1.4.8**: The Chat tab SHALL display the session ID in an expandable panel with a text input for resuming sessions.

**REQ-1.4.9**: Clicking "🔄 New Session" SHALL generate a new UUID session_id and clear the chat history.

**REQ-1.4.10**: After each turn completion, the session SHALL be saved to logs/chat_sessions/{session_id}.json with the complete history.

**REQ-1.4.11**: The session JSON SHALL include: session_id, history (array of {role, content, turn_index, traditional?, hybrid?, error_trad?, error_hybrid?}).

**REQ-1.4.12**: The sidebar SHALL display a "💬 Chat Sessions" section listing up to 20 recent sessions with preview text (first 45 characters + "…").

**REQ-1.4.13**: Clicking a session in the sidebar SHALL load that session's history and set it as the active session.

**REQ-1.4.14**: The active session SHALL be indicated with a 🟢 prefix and disabled button state.

### 1.5 Compare Tab Requirements

**REQ-1.5.1**: The Compare tab SHALL display a query input field with placeholder text "Type your query and run it against both search modes…".

**REQ-1.5.2**: The Compare tab SHALL provide 3 action buttons: "Run query" (primary), "🗑️ Clear Cache", arranged in 4.6:1:1 column ratio.

**REQ-1.5.3**: Clicking "Run query" SHALL disable the button and execute two parallel API calls: POST /api/query/traditional and POST /api/query/contextgraph.

**REQ-1.5.4**: The Compare tab SHALL display two panels side-by-side (50/50 split): Traditional (left) | ContextGraph (right).

**REQ-1.5.5**: During execution, each panel SHALL display a loading indicator with appropriate text.

**REQ-1.5.6**: Each panel SHALL render with 520px height and scrolling enabled.

**REQ-1.5.7**: After both queries complete, the comparison result SHALL be saved to session state with: query, traditional_time, hybrid_time, traditional_tokens, hybrid_tokens.

**REQ-1.5.8**: The "Run query" button SHALL re-enable after both panels render.

### 1.6 Traditional Panel Requirements

**REQ-1.6.1**: The Traditional Panel SHALL display a header with: grey dot indicator (#5C574C), "Traditional Document Search" title, "vector-only" badge.

**REQ-1.6.2**: The Traditional Panel SHALL render a list of documents with: name, page number, similarity score badge, snippet (italic, #6B6558), expandable full text.

**REQ-1.6.3**: Each document SHALL be styled with: #E7E1D4 border, 8px radius, 9px/11px padding, 7px bottom margin.

**REQ-1.6.4**: The score badge SHALL display: #EFEAE0 background, #5C574C text, 6px radius, "score {value}" format.

**REQ-1.6.5**: The Traditional Panel SHALL display a warning box: "⚠ No consolidated answer — each document must be reviewed individually." with #F3E4C9 background, #8A5A20 text, 8px radius.

**REQ-1.6.6**: The Traditional Panel SHALL render the LLM-synthesized answer with markdown-to-HTML conversion supporting: bold (**text**), italic (*text*), headers (# text), paragraphs (\n\n).

**REQ-1.6.7**: The Traditional Panel SHALL display 3 statistics: Docs returned (count), Tokens used (formatted with commas), Total time (seconds with 2 decimals).

**REQ-1.6.8**: The Traditional Panel SHALL include a collapsible telemetry card with microsecond-level metrics.

### 1.7 ContextGraph Panel Requirements

**REQ-1.7.1**: The ContextGraph Panel SHALL display a header with: red dot indicator (#A8412C), "ContextGraph" title, "hybrid graph + vector" badge.

**REQ-1.7.2**: The ContextGraph Panel SHALL implement a tabbed interface with "Answer" (default active) and "Ontology View" tabs.

**REQ-1.7.3**: In the Answer tab, the panel SHALL display a confidence badge with color-coded background: green (#E4EEE1, #3F6B42 text) for high confidence, amber for low.

**REQ-1.7.4**: The Answer tab SHALL display dynamic Intent Traffic Controller badges from telemetry.ui_badges with appropriate styling.

**REQ-1.7.5**: The Answer tab SHALL include a collapsible "🕸️ Graph Triplet Path Traversed" card with a table of (Subject Node, Relationship, Target Node, Conf).

**REQ-1.7.6**: The Answer tab SHALL include a collapsible "📌 Document Provenance & Exact Page Citations" card with (Source Document, Chunk ID, Verbatim Text Snippet).

**REQ-1.7.7**: The Answer tab SHALL render the LLM-synthesized answer with markdown-to-HTML conversion.

**REQ-1.7.8**: The Answer tab SHALL display sources list with [index] document names.

**REQ-1.7.9**: The Answer tab SHALL display 3 statistics: Graph nodes touched (count), Tokens used, Total time.

**REQ-1.7.10**: In the Ontology View tab, the panel SHALL display an entity type tree with active/inactive styling based on entity_summary data.

**REQ-1.7.11**: The Ontology View tab SHALL render a mini graph SVG with nodes (7px radius circles) and edges (lines with relationship labels).

**REQ-1.7.12**: Graph nodes SHALL be colored: #A8412C (matched entities), #D8D2C4 (fallback/unmatched entities), #E8A08C (connected entities).

**REQ-1.7.13**: Node positions SHALL be calculated in a 4-column grid layout with ~55px vertical spacing.

**REQ-1.7.14**: The Ontology View SHALL display an explanatory note: "Colored nodes/edges matched this query directly; grey nodes are one hop of surrounding context."

**REQ-1.7.15**: Tab switching SHALL be client-side JavaScript without triggering React rerenders (cgTab function).

### 1.8 Telemetry Card Requirements

**REQ-1.8.1**: The Telemetry Card SHALL be implemented as a collapsible <details> element, collapsed by default.

**REQ-1.8.2**: The summary text SHALL be "⚡ Microsecond Telemetry & Execution Ledger" (12px font, 700 weight, #5C574C color).

**REQ-1.8.3**: The card SHALL display a table with rows for: Vector DB Lookup (FAISS), Cross-Encoder Reranking (if > 0), Graph Traversal (Neo4j UNWIND), NER & Entity Resolution, Cypher Generation (if > 0), Post-Retrieval Pruning, LLM Synthesis Latency, Total Pipeline Execution.

**REQ-1.8.4**: The Total Pipeline Execution row SHALL have #EFEAE0 background and 700 font-weight.

**REQ-1.8.5**: The card SHALL display token breakdown: Tokens (Input / Output / Total) with formatted numbers (commas).

**REQ-1.8.6**: If cache_hit is true, the card SHALL display a Token Savings row with green background (#E4EEE1, #3F6B42 text) showing tokens_saved and tokens_cold_equivalent.

**REQ-1.8.7**: The card SHALL display: DB Candidates Surfaced (count with "nodes" or "chunks" label), Vector Noise Bypassed (boolean in caps, green if true).

**REQ-1.8.8**: Table styling SHALL include: 1px solid #EAEAEA row borders, 11.5px font, 4px vertical padding.

### 1.9 Analytics Tab Requirements

**REQ-1.9.1**: The Analytics tab SHALL display two radio buttons: "Last query's graph" (default) | "Full knowledge graph", arranged horizontally.

**REQ-1.9.2**: When "Last query's graph" is selected and no lastHybrid exists, the tab SHALL display: "Run a query in the Compare tab first to see its graph here."

**REQ-1.9.3**: When "Last query's graph" is selected, the tab SHALL use graph_edges_used_in_prompt (NOT graph_edges) for rendering.

**REQ-1.9.4**: If graph_matched_by === "fallback" OR graph_edges_used_in_prompt is empty, the tab SHALL display a warning: "No graph relationships were directly relevant to this query — the answer was grounded on document search, not the graph. Showing the broader graph neighborhood below for reference only, not as verification."

**REQ-1.9.5**: In fallback mode, the tab SHALL show the first 10 edges from graph_edges for reference.

**REQ-1.9.6**: When "Full knowledge graph" is selected, the tab SHALL fetch up to 60 relationships from the backend API.

**REQ-1.9.7**: The tab SHALL render a GraphVisualizer component with two columns: Graph SVG (flex 1.4) | Node detail panel (flex 1, border-left #E7E1D4).

**REQ-1.9.8**: Clicking a node SHALL update the detail panel WITHOUT triggering a React rerender (pure client-side JS).

**REQ-1.9.9**: The active node SHALL have visual styling: stroke #231F1C, stroke-width 2px.

**REQ-1.9.10**: The node detail panel SHALL display: badge (matched/connected/fallback), node name, entity type label, relationship reasons (list), source document, product name (if available).

**REQ-1.9.11**: Below the graph, the tab SHALL display a divider and "Traditional vs. ContextGraph — run history" section.

**REQ-1.9.12**: The run history section SHALL display a table of comparisons with columns: query, traditional_time, hybrid_time, traditional_tokens, hybrid_tokens.

**REQ-1.9.13**: The run history section SHALL display 3 metrics: Avg traditional latency, Avg hybrid latency (with delta), Avg hybrid token delta.

**REQ-1.9.14**: The run history section SHALL display two bar charts: Latency comparison (traditional_time vs hybrid_time), Token comparison (traditional_tokens vs hybrid_tokens).

### 1.10 Admin Tab Requirements

**REQ-1.10.1**: The Admin tab SHALL display 4 sub-tabs: "[USERS] User Profile Management", "[RBAC] Role Access Matrix", "[AUDIT] Security & Audit Logs", "[INGEST] Authorized Ingest & Pipeline".

**REQ-1.10.2**: In the Users tab, the Admin SHALL see a table of all users with columns: username, full_name, role, department, email.

**REQ-1.10.3**: The Users tab SHALL provide a "Create / Update User Profile" form with fields: Username, Full Name, Email Address, Assign AMC Organizational Role (dropdown), Department / Unit.

**REQ-1.10.4**: The form SHALL be arranged in a 2-column layout.

**REQ-1.10.5**: Clicking "Save User Profile" SHALL create or update the user and display a success toast.

**REQ-1.10.6**: The Users tab SHALL provide a "Remove User Profile" dropdown and "Delete Selected Profile" button.

**REQ-1.10.7**: In the RBAC tab, the Admin SHALL see a role access matrix table with columns: Role Name, Authorized Domains, Admin Access, Audit Logs, Unredacted PII, Cypher Tool, Compare & Analytics.

**REQ-1.10.8**: Each permission column SHALL display "YES" or "NO" based on ROLE_PERMISSIONS configuration.

**REQ-1.10.9**: The RBAC tab SHALL display security policy notes explaining each role's clearance level.

**REQ-1.10.10**: In the Audit tab, the Admin SHALL see the contents of logs/query_execution_audit.jsonl (last 30 lines) in a code block.

**REQ-1.10.11**: If the audit log file doesn't exist, the tab SHALL display: "No query audit events recorded yet."

**REQ-1.10.12**: In the Ingest tab, the Admin SHALL see two action buttons in a 2-column layout: "[RUN] Production Ingestion Pipeline", "[CHECK] Staleness Drift Detection".

**REQ-1.10.13**: Clicking "Production Ingestion Pipeline" SHALL execute the pipeline and display a success message with: elapsed_seconds, sebi_rss.downloaded_count, and full JSON report.

**REQ-1.10.14**: The Ingest tab SHALL provide an "Authorized Document Ingest" form with fields: Source URL, Upload PDF Document, Document Type (dropdown), Department (dropdown), Entity Type (dropdown), Authorizing Officer.

**REQ-1.10.15**: The form SHALL be arranged in a 2-column layout.

**REQ-1.10.16**: Clicking "Ingest & Index Document" SHALL upload the file, save it to scratch/admin_uploads, start a background indexing task, and display a success toast with SHA-256 hash and task ID.

**REQ-1.10.17**: The Ingest tab SHALL display a "Live Ingestion & Background Indexing Tasks" section listing up to 10 recent tasks.

**REQ-1.10.18**: Each task SHALL display: status badge (🟢 Completed, 🟡 Indexing, 🔴 Failed, ⚪ Queued), filename, SHA-256 hash (first 12 chars), stage, started_at, completed_at.

**REQ-1.10.19**: For PROCESSING tasks, a progress bar SHALL be displayed with the current stage text.

**REQ-1.10.20**: For COMPLETED tasks, a success message SHALL display: entities_count, relations_count, chunks_count.

**REQ-1.10.21**: For FAILED tasks, an error message SHALL display the error_message.

**REQ-1.10.22**: The Ingest tab SHALL provide a "🔄 Refresh Status" button to reload the task list.

**REQ-1.10.23**: The Ingest tab SHALL display a "Proposed Regulatory Supersession Edges (Review Queue)" section.

**REQ-1.10.24**: Each proposed edge SHALL display: source, relationship, target, and two buttons: "Confirm", "Reject".

**REQ-1.10.25**: The Ingest tab SHALL provide a "Download Regulation 16C Audit Report (.md)" button that downloads a compliance report.

**REQ-1.10.26**: The Ingest tab SHALL include an expandable "Preview Compliance Report" section rendering the markdown report.

### 1.11 Session Management Requirements

**REQ-1.11.1**: Each chat session SHALL be assigned a unique UUID v4 session_id.

**REQ-1.11.2**: Session files SHALL be stored at logs/chat_sessions/{session_id}.json.

**REQ-1.11.3**: Session JSON SHALL contain: session_id, history array (role, content, turn_index, traditional?, hybrid?, error_trad?, error_hybrid?).

**REQ-1.11.4**: Sessions SHALL be saved after each turn completion (both Traditional and ContextGraph responses received).

**REQ-1.11.5**: Session save SHALL use JSON.stringify with ensure_ascii=false, indent=2, default=str for non-JSON types.

**REQ-1.11.6**: The sidebar SHALL list up to 20 most recent sessions sorted by modified time (newest first).

**REQ-1.11.7**: Session preview text SHALL be the first user message truncated to 45 characters with "…" suffix.

**REQ-1.11.8**: Clicking a session SHALL load its history from disk and set it as the active session.

**REQ-1.11.9**: Session load failure SHALL display an error message without disrupting the current session.

**REQ-1.11.10**: Corrupt session files SHALL be skipped in the sidebar list (not crash the app).

### 1.12 Background Task Monitoring Requirements

**REQ-1.12.1**: When a new indexing task completes, a toast notification SHALL appear: "🎉 Indexing complete: '[filename]'! Added [entities_count] entities to Neo4j & [chunks_count] chunks to FAISS."

**REQ-1.12.2**: When an indexing task fails, a toast notification SHALL appear: "⚠️ Indexing failed for '[filename]': [error_message]"

**REQ-1.12.3**: Toast notifications SHALL auto-dismiss after 5 seconds.

**REQ-1.12.4**: The sidebar SHALL display an "⚙️ Background Indexing" section showing active PROCESSING tasks.

**REQ-1.12.5**: Each active task SHALL display: filename, stage, progress bar (0.0 to 1.0).

**REQ-1.12.6**: The sidebar section SHALL be hidden if no active tasks exist.

**REQ-1.12.7**: Notifications SHALL be marked as "read" after being displayed to prevent re-showing on refresh.

### 1.13 Intent Cache Management Requirements

**REQ-1.13.1**: The application SHALL provide a "🗑️ Clear Intent Cache" button in the sidebar (full width).

**REQ-1.13.2**: The Compare tab SHALL provide a "🗑️ Clear Cache" button in the action row.

**REQ-1.13.3**: The Chat tab SHALL provide a "🗑️ Clear Cache" button in the action row.

**REQ-1.13.4**: Clicking any "Clear Cache" button SHALL flush in-memory and disk intent cache.

**REQ-1.13.5**: After clearing cache, a toast notification SHALL display: "⚡ Intent Cache cleared cleanly! Next query will execute full LLM synthesis."

**REQ-1.13.6**: The cache clear operation SHALL complete without requiring a page refresh.

## 2. Non-Functional Requirements

### 2.1 Performance Requirements

**REQ-2.1.1**: The React application SHALL load the initial page in ≤ 2 seconds on a standard broadband connection (10 Mbps).

**REQ-2.1.2**: Tab switching SHALL complete in ≤ 100ms with smooth visual transitions.

**REQ-2.1.3**: Query execution time in Compare or Chat tabs SHALL match the Streamlit implementation within ±100ms.

**REQ-2.1.4**: The GraphVisualizer SHALL render up to 60 nodes without frame drops (maintain 60 FPS).

**REQ-2.1.5**: Session save operations SHALL complete in ≤ 50ms to avoid blocking the UI.

**REQ-2.1.6**: The Admin tab's user table SHALL render 100+ users without noticeable lag.

**REQ-2.1.7**: Chat history with 100+ turns SHALL maintain smooth scrolling performance using virtual scrolling.

**REQ-2.1.8**: Parallel query execution SHALL reduce total wait time to max(T_traditional, T_hybrid) instead of sum.

### 2.2 Scalability Requirements

**REQ-2.2.1**: The application SHALL support up to 1000 concurrent users without degradation (assuming adequate backend capacity).

**REQ-2.2.2**: The session list in the sidebar SHALL paginate or implement infinite scroll for users with 100+ sessions.

**REQ-2.2.3**: The Admin tab's indexing task list SHALL handle 1000+ tasks with pagination (10 per page).

**REQ-2.2.4**: The run history table in Analytics SHALL support 1000+ comparison entries with client-side filtering and sorting.

### 2.3 Reliability Requirements

**REQ-2.3.1**: The application SHALL gracefully handle API failures by displaying error messages in the affected panel without crashing.

**REQ-2.3.2**: If one query in a parallel execution fails, the other SHALL still render successfully.

**REQ-2.3.3**: Session save failures SHALL log a warning but not disrupt the user's ability to continue chatting.

**REQ-2.3.4**: The application SHALL implement error boundaries to catch and display component rendering errors.

**REQ-2.3.5**: Network timeouts SHALL trigger a user-friendly error message after 240 seconds.

### 2.4 Usability Requirements

**REQ-2.4.1**: All interactive elements SHALL provide visual feedback on hover (cursor change, color transition).

**REQ-2.4.2**: Buttons SHALL be disabled during loading states to prevent duplicate submissions.

**REQ-2.4.3**: Form inputs SHALL display validation errors inline with red text.

**REQ-2.4.4**: Toast notifications SHALL appear in the top-right corner and auto-dismiss after 5 seconds.

**REQ-2.4.5**: The application SHALL maintain responsive design for screen widths ≥ 1024px (desktop/laptop focus, mobile not required).

**REQ-2.4.6**: Loading states SHALL use spinners or skeleton screens that match the Streamlit loading indicators.

**REQ-2.4.7**: All collapsible sections (telemetry, triplets, provenance) SHALL indicate their state with ▶ (collapsed) or ▼ (expanded) arrows.

### 2.5 Accessibility Requirements

**REQ-2.5.1**: All interactive elements SHALL be keyboard-navigable with Tab and Enter/Space keys.

**REQ-2.5.2**: The active tab SHALL have a visible focus indicator matching the active tab styling.

**REQ-2.5.3**: Color contrast ratios SHALL meet WCAG 2.1 AA standards (4.5:1 for normal text, 3:1 for large text).

**REQ-2.5.4**: Form inputs SHALL have associated <label> elements or aria-label attributes.

**REQ-2.5.5**: Buttons SHALL have descriptive aria-label attributes where icons are used without text.

**REQ-2.5.6**: The application SHALL provide alt text for all meaningful images (if any).

**REQ-2.5.7**: Dynamic content updates (loading panels, toast notifications) SHALL announce changes to screen readers using aria-live regions.

### 2.6 Security Requirements

**REQ-2.6.1**: The application SHALL escape all user-generated and LLM-generated text before rendering to prevent XSS attacks.

**REQ-2.6.2**: The application SHALL use DOMPurify to sanitize HTML converted from markdown.

**REQ-2.6.3**: Session IDs SHALL be treated as sensitive data and not logged to console or analytics.

**REQ-2.6.4**: The application SHALL validate all inputs (query length ≤ 2000 characters, username non-empty, etc.) before API submission.

**REQ-2.6.5**: RBAC permissions SHALL be enforced on the backend; frontend tab hiding is UX-only, not security.

**REQ-2.6.6**: API requests SHALL include appropriate authentication headers (JWT or session cookie).

**REQ-2.6.7**: The application SHALL implement CSRF protection for state-changing operations.

**REQ-2.6.8**: All API calls SHALL use HTTPS in production.

### 2.7 Maintainability Requirements

**REQ-2.7.1**: The codebase SHALL follow a component-based architecture with clear separation of concerns.

**REQ-2.7.2**: CSS SHALL be modular with component-scoped stylesheets or a single global stylesheet organized by section.

**REQ-2.7.3**: All components SHALL have TypeScript interfaces for props and state.

**REQ-2.7.4**: Complex business logic (API adapters, node position calculation, markdown conversion) SHALL be extracted into utility functions with unit tests.

**REQ-2.7.5**: The codebase SHALL include inline comments explaining non-obvious logic (especially parallel execution, tab switching without rerenders).

**REQ-2.7.6**: The project SHALL include a README.md with setup instructions, architecture overview, and development guidelines.

### 2.8 Compatibility Requirements

**REQ-2.8.1**: The application SHALL work in the latest 2 versions of Chrome, Firefox, and Safari.

**REQ-2.8.2**: The application SHALL work in Edge (Chromium-based versions).

**REQ-2.8.3**: The application SHALL NOT target Internet Explorer.

**REQ-2.8.4**: The application SHALL maintain API compatibility with the existing FastAPI backend endpoints: /api/query/traditional, /api/query/contextgraph, /api/chat.

**REQ-2.8.5**: Session JSON files SHALL maintain schema compatibility with Streamlit-generated files for seamless migration.

### 2.9 Deployment Requirements

**REQ-2.9.1**: The application SHALL be deployable as a static site (HTML, CSS, JS) on CDN platforms (Vercel, Netlify, Cloudflare Pages, S3+CloudFront).

**REQ-2.9.2**: The application SHALL read the API_BASE URL from an environment variable (process.env.REACT_APP_API_BASE or equivalent).

**REQ-2.9.3**: The production build SHALL be optimized with code splitting, minification, and tree shaking.

**REQ-2.9.4**: The application SHALL include a build command (npm run build or yarn build) that produces a dist/ folder with static assets.

**REQ-2.9.5**: The application SHALL serve a 404.html for client-side routing to work on static hosts.

**REQ-2.9.6**: The deployment process SHALL support CI/CD pipelines for automated builds on git push.

### 2.10 Testing Requirements

**REQ-2.10.1**: The application SHALL have ≥ 80% line coverage for unit tests.

**REQ-2.10.2**: Critical user flows (query execution, session persistence, tab switching, RBAC filtering) SHALL have integration tests.

**REQ-2.10.3**: Visual regression tests SHALL compare React screenshots to Streamlit screenshots at 3 breakpoints (1024px, 1440px, 1920px).

**REQ-2.10.4**: All 12 main components SHALL have unit tests for rendering, prop handling, and event emission.

**REQ-2.10.5**: Utility functions (markdown-to-HTML, node position calculation, API adapters) SHALL have 100% coverage.

**REQ-2.10.6**: RBAC permission logic SHALL have unit tests covering all 5 roles × 4 tabs = 20 combinations.

**REQ-2.10.7**: Error handling scenarios (API failure, session load error, race conditions) SHALL have integration tests.

## 3. Data Requirements

### 3.1 Session Data Persistence

**REQ-3.1.1**: Session files SHALL be stored in the logs/chat_sessions/ directory with filename format {session_id}.json.

**REQ-3.1.2**: Each session file SHALL contain: session_id (string), history (array of Message objects).

**REQ-3.1.3**: Message objects SHALL contain: role ("user" | "assistant"), content (string), turn_index (number), traditional (object, optional), hybrid (object, optional), error_trad (string, optional), error_hybrid (string, optional).

**REQ-3.1.4**: Session files SHALL use UTF-8 encoding.

**REQ-3.1.5**: Session files SHALL be human-readable JSON with 2-space indentation.

### 3.2 User Profile Data

**REQ-3.2.1**: User profiles SHALL be stored in an in-memory data structure (array of UserProfile objects) or fetched from the backend API.

**REQ-3.2.2**: Each UserProfile SHALL contain: username (string), full_name (string), role (AMCRole enum), department (string), email (string, optional).

**REQ-3.2.3**: The active user SHALL be stored in React Context and persisted to localStorage for session continuity.

### 3.3 Comparison History Data

**REQ-3.3.1**: Comparison results SHALL be stored in session state as an array of Comparison objects.

**REQ-3.3.2**: Each Comparison SHALL contain: query (string), traditional_time (number), hybrid_time (number), traditional_tokens (number), hybrid_tokens (number).

**REQ-3.3.3**: Comparison history SHALL persist across tab switches but NOT across page refreshes (session-scoped only).

### 3.4 Graph Data

**REQ-3.4.1**: Graph nodes SHALL be represented as strings (entity names).

**REQ-3.4.2**: Graph edges SHALL be represented as objects with: s (string, subject), rel (string, relationship), o (string, object), conf (number, confidence, optional).

**REQ-3.4.3**: Source info SHALL be fetched from the backend and contain: label (string, entity type), source (string, document name), product_name (string, optional).

## 4. Interface Requirements

### 4.1 API Endpoints

**REQ-4.1.1**: POST /api/query/traditional SHALL accept: { query: string } and return QueryResponse with traditional field.

**REQ-4.1.2**: POST /api/query/contextgraph SHALL accept: { query: string } and return QueryResponse with answer, sources, graph_highlight fields.

**REQ-4.1.3**: POST /api/chat SHALL accept: { query: string, session_id: string, history: Message[], mode: "traditional" | "contextgraph" } and return ChatResponse.

**REQ-4.1.4**: All endpoints SHALL return JSON with Content-Type: application/json.

**REQ-4.1.5**: All endpoints SHALL have a 240-second timeout.

**REQ-4.1.6**: All endpoints SHALL return HTTP 200 on success, 4xx for client errors, 5xx for server errors.

### 4.2 File System Interface

**REQ-4.2.1**: The application SHALL read session files from logs/chat_sessions/{session_id}.json.

**REQ-4.2.2**: The application SHALL write session files to the same directory after each turn.

**REQ-4.2.3**: The application SHALL read audit logs from logs/query_execution_audit.jsonl (Admin tab only).

**REQ-4.2.4**: File operations SHALL handle ENOENT errors gracefully (file not found) without crashing.

**REQ-4.2.5**: File write operations SHALL use atomic writes (write to temp file, then rename) to prevent corruption.

## 5. Constraints

### 5.1 Technical Constraints

**CONST-5.1.1**: The application MUST be built with React 19.2.7+ and React Router 6.20.0+.

**CONST-5.1.2**: The application MUST use Vite 8.1.1+ as the build tool.

**CONST-5.1.3**: The application MUST use axios 1.6.2+ for HTTP requests.

**CONST-5.1.4**: The application MUST NOT use any UI component libraries (Material-UI, Ant Design, etc.) to ensure exact CSS replication.

**CONST-5.1.5**: The application MUST NOT use CSS-in-JS libraries (styled-components, emotion) unless absolutely necessary for dynamic styling.

**CONST-5.1.6**: The application MUST render graphs as inline SVG (not canvas) for accessibility and inspectability.

### 5.2 Design Constraints

**CONST-5.2.1**: The application MUST replicate the Streamlit UI at 99%+ pixel similarity.

**CONST-5.2.2**: The application MUST NOT introduce new features or UI improvements beyond the Streamlit scope.

**CONST-5.2.3**: The application MUST preserve all Streamlit quirks and unusual patterns (e.g., tab switching without rerenders, reversed chat history).

### 5.3 Operational Constraints

**CONST-5.3.1**: The application MUST run in modern browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+).

**CONST-5.3.2**: The application MUST NOT require server-side rendering (SSR) or Node.js runtime in production.

**CONST-5.3.3**: The application MUST be deployable on static hosting platforms without custom server configuration.

## 6. Assumptions

**ASSUM-6.1**: The FastAPI backend is available and returns responses in the documented format.

**ASSUM-6.2**: The file system (logs/chat_sessions/) is writable by the application.

**ASSUM-6.3**: Users have modern browsers with JavaScript enabled.

**ASSUM-6.4**: The deployment environment supports serving single-page applications with client-side routing.

**ASSUM-6.5**: The backend enforces RBAC permissions; frontend tab hiding is purely UX-focused.

**ASSUM-6.6**: Session files are managed by a single user at a time (no concurrent writes to the same session_id.json).

**ASSUM-6.7**: The Neo4j database for graph queries is read-only from the frontend's perspective.

**ASSUM-6.8**: Toast notifications are sufficient for user feedback (no modal dialogs required).

## 7. Dependencies

**DEP-7.1**: The application depends on the FastAPI backend for all query execution and data retrieval.

**DEP-7.2**: The application depends on the Neo4j database for graph data in the Analytics tab.

**DEP-7.3**: The application depends on the FAISS vector store (accessed via API) for document retrieval.

**DEP-7.4**: The application depends on the file system for session persistence (logs/chat_sessions/).

**DEP-7.5**: The application depends on the provenance ledger for audit logs (logs/query_execution_audit.jsonl).

**DEP-7.6**: The application depends on the indexing manager for background task monitoring.

**DEP-7.7**: The application depends on the RBAC manager for user profiles and permissions.

## 8. Success Criteria

**SUCCESS-8.1**: Visual Fidelity: Screenshots of React app match Streamlit app at 99%+ pixel similarity (excluding browser chrome).

**SUCCESS-8.2**: Functional Parity: All 4 tabs render correctly with identical behavior to Streamlit.

**SUCCESS-8.3**: Performance: Page load time ≤ 2 seconds, query execution time matches Streamlit ±100ms.

**SUCCESS-8.4**: RBAC: Tab visibility changes correctly when switching user profiles (all 5 roles tested).

**SUCCESS-8.5**: Session Persistence: Chat sessions save and load without data loss (tested with 10+ sessions, 20+ turns each).

**SUCCESS-8.6**: Graph Interaction: Node clicks in Analytics update detail panel without page refresh (100% of clicks successful).

**SUCCESS-8.7**: Parallel Execution: Compare and Chat tabs execute both queries simultaneously (measured with network profiling).

**SUCCESS-8.8**: Error Handling: All error scenarios (API failure, session load error, race conditions) display appropriate messages without crashes.

**SUCCESS-8.9**: Accessibility: Passes WCAG 2.1 AA automated checks using axe-core or similar tool.

**SUCCESS-8.10**: Cross-Browser: Works identically in Chrome, Firefox, Safari, Edge (latest 2 versions, tested manually).

**SUCCESS-8.11**: Test Coverage: Unit tests achieve ≥ 80% line coverage, critical flows have integration tests.

**SUCCESS-8.12**: User Acceptance: Stakeholders confirm the React application is indistinguishable from the Streamlit application in day-to-day usage.
