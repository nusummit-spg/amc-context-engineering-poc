# Task List: Streamlit to React Migration

## Phase 1: Core Infrastructure

- [x] 1.1 Set up React project structure with Vite build configuration
- [x] 1.2 Configure React Router with routes for /chat, /compare, /analytics, /admin
- [x] 1.3 Create Layout component with header, sidebar, and main content area
- [x] 1.4 Port complete CSS theme from Streamlit to global stylesheet (colors, typography, spacing, component styles)
- [x] 1.5 Implement UserContext with RBAC logic and role-based permission checks
- [x] 1.6 Create SessionContext for managing chat sessions and comparison history
- [x] 1.7 Implement QueryContext for tracking last query results (lastHybrid, lastTraditional)
- [x] 1.8 Configure axios HTTP client with API base URL from environment variable
- [x] 1.9 Implement error boundary component for graceful error handling
- [x] 1.10 Create toast notification system matching Streamlit notification styling

## Phase 2: User Profile & RBAC

- [x] 2.1 Create UserProfile data model with AMCRole enum
- [x] 2.2 Implement UserProfileSwitcher component in sidebar with dropdown
- [x] 2.3 Create ROLE_PERMISSIONS configuration matching Streamlit RBAC rules
- [x] 2.4 Implement tab filtering logic based on user permissions
- [x] 2.5 Add user profile display section (name, role, department) below dropdown
- [x] 2.6 Implement localStorage persistence for active user selection
- [x] 2.7 Test all 5 user roles with correct tab visibility

## Phase 3: Tab Navigation

- [x] 3.1 Create TabNavigation component with 4 tabs (Chat, Compare, Analytics, Admin)
- [x] 3.2 Implement active/inactive tab styling (#A8412C active, #8A8378 inactive, 2px bottom border)
- [x] 3.3 Add tab icons: 💬 Chat, ⚖️ Compare, 📊 Analytics, 👥 Admin & Governance
- [x] 3.4 Implement tab click handling with React Router navigation
- [x] 3.5 Add tab filtering based on user permissions from UserContext
- [x] 3.6 Implement redirect logic when active tab becomes hidden after profile switch
- [x] 3.7 Add "🟢 Backend: {API_BASE} | Role: {user_role}" caption to each tab

## Phase 4: Traditional Panel Component

- [x] 4.1 Create TraditionalPanel component with TraditionalResult interface
- [x] 4.2 Implement panel header with grey dot indicator (#5C574C) and "vector-only" badge
- [x] 4.3 Render document list with name, page, score badge, snippet styling
- [x] 4.4 Implement expandable full text using <details>/<summary> elements
- [x] 4.5 Add warning box: "⚠ No consolidated answer — each document must be reviewed individually."
- [x] 4.6 Implement markdown-to-HTML conversion function supporting bold, italic, headers, paragraphs
- [x] 4.7 Implement XSS sanitization with DOMPurify for LLM-generated answers
- [x] 4.8 Render 3-column statistics grid (Docs returned, Tokens used, Total time)
- [x] 4.9 Create TelemetryCard component as collapsible <details> element
- [x] 4.10 Populate telemetry table with all latency metrics (Vector DB, Rerank, Graph, NER, Cypher, Post-Retrieval, LLM, Total)
- [x] 4.11 Implement conditional rendering for Cypher generation and Reranking rows
- [x] 4.12 Add token breakdown display (Input / Output / Total with comma formatting)
- [x] 4.13 Implement conditional Token Savings row with green styling if cache_hit
- [x] 4.14 Add DB Candidates and Vector Bypassed display to telemetry

## Phase 5: ContextGraph Panel Component

- [x] 5.1 Create ContextGraphPanel component with HybridResult interface
- [x] 5.2 Implement panel header with red dot indicator (#A8412C) and "hybrid graph + vector" badge
- [x] 5.3 Create tabbed interface with "Answer" and "Ontology View" tabs
- [x] 5.4 Implement tab switching with client-side JavaScript (cgTab function) without React rerenders
- [x] 5.5 In Answer tab: render confidence badge with color-coded styling (green for high confidence)
- [x] 5.6 Render dynamic Intent Traffic Controller badges from telemetry.ui_badges
- [x] 5.7 Create collapsible Graph Triplet Path card with (Subject, Relationship, Target, Conf) table
- [x] 5.8 Create collapsible Document Provenance card with (Source Document, Chunk ID, Snippet) table
- [x] 5.9 Render answer with markdown-to-HTML conversion and XSS sanitization
- [x] 5.10 Render sources list with [index] document names
- [x] 5.11 Render 3-column statistics grid (Graph nodes touched, Tokens used, Total time)
- [x] 5.12 Integrate TelemetryCard in Answer tab
- [x] 5.13 In Ontology View tab: render entity type tree with active/inactive styling
- [x] 5.14 Create mini graph SVG renderer with 4-column grid layout
- [x] 5.15 Implement node positioning algorithm (4 columns, ~55px vertical spacing)
- [x] 5.16 Render graph edges as SVG lines with relationship labels
- [x] 5.17 Render graph nodes as SVG circles with color coding (#A8412C matched, #D8D2C4 fallback, #E8A08C connected)
- [x] 5.18 Add explanatory note about colored vs grey nodes

## Phase 6: Compare Tab

- [ ] 6.1 Create CompareTab component with query input and action buttons
- [x] 6.2 Implement 4.6:1:1 column layout for (Query Input | Run query | Clear Cache)
- [x] 6.3 Add placeholder text: "Type your query and run it against both search modes…"
- [x] 6.4 Implement "Run query" button click handler with parallel API execution
- [x] 6.5 Use Promise.all() to execute POST /api/query/traditional and /api/query/contextgraph simultaneously
- [x] 6.6 Implement loading states for both panels ("Running traditional vector search…", "Running graph + vector retrieval…")
- [x] 6.7 Render TraditionalPanel (left) and ContextGraphPanel (right) in 2-column layout
- [x] 6.8 Set panel height to 520px with scrolling enabled
- [x] 6.9 Disable "Run query" button during execution (is_running state)
- [x] 6.10 Save comparison result to session state after both queries complete
- [x] 6.11 Implement "🗑️ Clear Cache" button functionality
- [x] 6.12 Display success toast after cache clear
- [x] 6.13 Add error handling for API failures with error display in respective panel

## Phase 7: Chat Tab

- [x] 7.1 Create ChatTab component with query input and 4 action buttons
- [x] 7.2 Implement 4.0:0.8:1.1:1.1 column layout for (Query | Send | New Session | Clear Cache)
- [x] 7.3 Add placeholder text: "Ask a follow-up — conversation context carries forward…"
- [x] 7.4 Implement "Send" button click handler with parallel API execution
- [x] 7.5 Execute parallel POST /api/chat calls with mode=traditional and mode=contextgraph
- [x] 7.6 Append user message to history with turn_index
- [x] 7.7 Append assistant message placeholder with loading=true flag
- [x] 7.8 Display chat history in reverse chronological order (newest first)
- [x] 7.9 Group history into (user, assistant) turn pairs
- [x] 7.10 Render each turn as: user message header → two-column assistant response
- [x] 7.11 Implement loading state rendering for in-flight turn
- [x] 7.12 Update panels as each query completes (faster one renders first)
- [x] 7.13 Set loading=false and save session after both responses received
- [x] 7.14 Implement session ID display in expandable panel with resume input
- [x] 7.15 Implement "🔄 New Session" button generating new UUID and clearing history
- [x] 7.16 Create session save function writing to logs/chat_sessions/{session_id}.json
- [x] 7.17 Create session load function reading from disk
- [x] 7.18 Handle session load errors gracefully with error message
- [x] 7.19 Implement "🗑️ Clear Cache" button functionality in Chat tab

## Phase 8: Session Management

- [ ] 8.1 Create SessionList component for sidebar
- [ ] 8.2 Implement session file listing from logs/chat_sessions/ directory
- [ ] 8.3 Sort sessions by modified time (newest first)
- [ ] 8.4 Display up to 20 most recent sessions
- [ ] 8.5 Generate preview text from first user message (45 chars + "…")
- [ ] 8.6 Display turn count for each session
- [ ] 8.7 Highlight active session with 🟢 prefix and disabled button
- [ ] 8.8 Implement session click handler loading history from disk
- [ ] 8.9 Handle corrupt/unreadable session files gracefully (skip in list)
- [ ] 8.10 Add "💬 Chat Sessions" section header in sidebar
- [ ] 8.11 Display "No saved sessions yet" message when list is empty
- [ ] 8.12 Implement session persistence with UTF-8 encoding, 2-space indentation, default=str for non-JSON types

## Phase 9: Graph Visualizer Component

- [ ] 9.1 Create GraphVisualizer component with node/edge/sourceInfo props
- [ ] 9.2 Implement 2-column layout: Graph SVG (flex 1.4) | Detail panel (flex 1, border-left)
- [ ] 9.3 Calculate node positions in 4-column grid with dynamic height
- [ ] 9.4 Render SVG edges with lines and relationship label text
- [ ] 9.5 Render SVG nodes as circles (7px radius) with click handlers
- [ ] 9.6 Color nodes based on matched status (#A8412C matched, #D8D2C4 fallback, #E8A08C connected)
- [ ] 9.7 Render node labels below circles (8.5px font, #5C574C)
- [ ] 9.8 Build node detail JSON with relationship reasons for each node
- [ ] 9.9 Implement node click handler updating detail panel WITHOUT React rerenders
- [ ] 9.10 Apply active node styling (stroke #231F1C, stroke-width 2px) on click
- [ ] 9.11 Display node details: badge (matched/connected/fallback), name, entity type, reasons, source, product name
- [ ] 9.12 Handle empty nodes array with "No graph data for this scope." message
- [ ] 9.13 Add explanatory note below graph about node colors

## Phase 10: Analytics Tab

- [ ] 10.1 Create AnalyticsTab component with scope radio buttons
- [ ] 10.2 Implement horizontal radio group: "Last query's graph" | "Full knowledge graph"
- [ ] 10.3 For "Last query's graph" scope: check if lastHybrid exists
- [ ] 10.4 Display "Run a query in the Compare tab first..." message if no lastHybrid
- [ ] 10.5 Extract edges from graph_edges_used_in_prompt (NOT graph_edges)
- [ ] 10.6 Check for fallback mode (graph_matched_by === "fallback" OR empty edges)
- [ ] 10.7 Display warning message for fallback mode: "No graph relationships were directly relevant..."
- [ ] 10.8 Use first 10 edges from graph_edges in fallback mode for reference
- [ ] 10.9 Extract nodes from edges (unique subjects and objects)
- [ ] 10.10 Fetch source info for nodes from backend API
- [ ] 10.11 Render GraphVisualizer with nodes, edges, matchedTexts, sourceInfo, isFallbackGraph
- [ ] 10.12 For "Full knowledge graph" scope: fetch subgraph from API (limit 60)
- [ ] 10.13 Add divider and "Traditional vs. ContextGraph — run history" section header
- [ ] 10.14 Display comparisons array as table (query, traditional_time, hybrid_time, tokens)
- [ ] 10.15 Render 3 metrics: Avg traditional latency, Avg hybrid latency (with delta), Avg token delta
- [ ] 10.16 Render latency comparison bar chart (traditional_time vs hybrid_time)
- [ ] 10.17 Render token comparison bar chart (traditional_tokens vs hybrid_tokens)
- [ ] 10.18 Display "Run a query in the Compare tab first." message if comparisons array is empty

## Phase 11: Admin Tab - Users Sub-Tab

- [ ] 11.1 Create AdminTab component with 4 sub-tabs
- [ ] 11.2 Implement sub-tab navigation: "[USERS] User Profile Management", "[RBAC] Role Access Matrix", "[AUDIT] Security & Audit Logs", "[INGEST] Authorized Ingest & Pipeline"
- [ ] 11.3 In Users sub-tab: display users table with all fields (username, full_name, role, department, email)
- [ ] 11.4 Create "Create / Update User Profile" form with 2-column layout
- [ ] 11.5 Add form fields: Username, Full Name, Email Address, Assign AMC Organizational Role (dropdown), Department / Unit
- [ ] 11.6 Implement "Save User Profile" button handler calling RBAC manager
- [ ] 11.7 Display success toast after user creation/update
- [ ] 11.8 Add form validation (non-empty username and full_name)
- [ ] 11.9 Create "Remove User Profile" dropdown listing all users except sarah_compliance
- [ ] 11.10 Implement "Delete Selected Profile" button handler
- [ ] 11.11 Display success toast after user deletion

## Phase 12: Admin Tab - RBAC Sub-Tab

- [ ] 12.1 Create RBAC matrix table with columns: Role Name, Authorized Domains, Admin Access, Audit Logs, Unredacted PII, Cypher Tool, Compare & Analytics
- [ ] 12.2 Populate table rows from ROLE_PERMISSIONS configuration
- [ ] 12.3 Display "YES" or "NO" for each permission based on role
- [ ] 12.4 Add security policy notes section explaining each role's clearance level
- [ ] 12.5 Style table with consistent borders and padding

## Phase 13: Admin Tab - Audit Sub-Tab

- [ ] 13.1 Implement audit log file reading from logs/query_execution_audit.jsonl
- [ ] 13.2 Extract last 30 lines from audit log
- [ ] 13.3 Display log lines in code block with JSON language highlighting
- [ ] 13.4 Handle missing audit log file with "No query audit events recorded yet." message
- [ ] 13.5 Add caption showing filename and line count

## Phase 14: Admin Tab - Ingest Sub-Tab

- [ ] 14.1 Create 2-column layout for pipeline action buttons
- [ ] 14.2 Implement "[RUN] Production Ingestion Pipeline" button handler
- [ ] 14.3 Display loading spinner during pipeline execution
- [ ] 14.4 Show success message with elapsed_seconds and sebi_rss.downloaded_count
- [ ] 14.5 Display full pipeline report JSON in expandable section
- [ ] 14.6 Implement "[CHECK] Staleness Drift Detection" button handler
- [ ] 14.7 Display staleness report with SHA-256 hashes and drift status
- [ ] 14.8 Create "Authorized Document Ingest" form with 2-column layout
- [ ] 14.9 Add form fields: Source URL, Upload PDF Document, Document Type, Department, Entity Type, Authorizing Officer
- [ ] 14.10 Implement file upload handler saving to scratch/admin_uploads
- [ ] 14.11 Implement "Ingest & Index Document" button handler calling ingestion gateway
- [ ] 14.12 Start background indexing task after successful ingest
- [ ] 14.13 Display success toast with SHA-256 hash and task ID
- [ ] 14.14 Handle duplicate documents with "Force Re-Index" button
- [ ] 14.15 Create "Live Ingestion & Background Indexing Tasks" section
- [ ] 14.16 Fetch up to 10 recent indexing tasks from backend
- [ ] 14.17 Display each task with status badge (🟢/🟡/🔴/⚪), filename, SHA-256, stage, timestamps
- [ ] 14.18 Render progress bar for PROCESSING tasks
- [ ] 14.19 Display success metrics (entities_count, relations_count, chunks_count) for COMPLETED tasks
- [ ] 14.20 Display error message for FAILED tasks
- [ ] 14.21 Implement "🔄 Refresh Status" button to reload task list
- [ ] 14.22 Create "Proposed Regulatory Supersession Edges" section
- [ ] 14.23 Display proposed edges with source, relationship, target
- [ ] 14.24 Implement "Confirm" and "Reject" buttons for each edge
- [ ] 14.25 Add "Download Regulation 16C Audit Report (.md)" button
- [ ] 14.26 Generate compliance report download file
- [ ] 14.27 Create expandable "Preview Compliance Report" section rendering markdown

## Phase 15: Background Task Monitoring

- [ ] 15.1 Implement unread notification polling in Layout component
- [ ] 15.2 Display completion toast for COMPLETED tasks: "🎉 Indexing complete: '[filename]'!"
- [ ] 15.3 Display failure toast for FAILED tasks: "⚠️ Indexing failed for '[filename]': [error_message]"
- [ ] 15.4 Mark notifications as read after displaying
- [ ] 15.5 Create "⚙️ Background Indexing" section in sidebar
- [ ] 15.6 Display active PROCESSING tasks with filename, stage, progress bar
- [ ] 15.7 Hide sidebar section if no active tasks
- [ ] 15.8 Implement notification polling interval (every 5 seconds)
- [ ] 15.9 Clear polling interval on component unmount

## Phase 16: Intent Cache Management

- [ ] 16.1 Implement "🗑️ Clear Intent Cache" button in sidebar (full width)
- [ ] 16.2 Create cache clear API call to backend
- [ ] 16.3 Display success toast: "⚡ Intent Cache cleared cleanly! Next query will execute full LLM synthesis."
- [ ] 16.4 Add "🗑️ Clear Cache" button to Compare tab action row
- [ ] 16.5 Add "🗑️ Clear Cache" button to Chat tab action row
- [ ] 16.6 Implement cache clear handler callable from all locations

## Phase 17: API Integration

- [ ] 17.1 Create API client utility with axios configuration
- [ ] 17.2 Implement POST /api/query/traditional endpoint call
- [ ] 17.3 Implement POST /api/query/contextgraph endpoint call
- [ ] 17.4 Implement POST /api/chat endpoint call with mode parameter
- [ ] 17.5 Create response adapter functions converting API responses to component props format
- [ ] 17.6 Implement _to_traditional adapter (API QueryResponse → TraditionalResult)
- [ ] 17.7 Implement _to_hybrid adapter (API QueryResponse → HybridResult)
- [ ] 17.8 Implement _adapt_traditional adapter for chat responses
- [ ] 17.9 Implement _adapt_hybrid adapter for chat responses
- [ ] 17.10 Add request timeout configuration (240 seconds)
- [ ] 17.11 Implement error handling for network failures
- [ ] 17.12 Add retry logic with exponential backoff for transient errors
- [ ] 17.13 Implement local execution fallback when API_BASE is not configured

## Phase 18: Styling & CSS

- [ ] 18.1 Port all Streamlit CSS to React global stylesheet
- [ ] 18.2 Define CSS custom properties for color palette, typography, spacing, border radius
- [ ] 18.3 Implement background pattern (radial gradient dots) on .stApp equivalent
- [ ] 18.4 Style tab navigation with exact colors, spacing, borders
- [ ] 18.5 Style primary buttons (#A8412C background, white text, 8px radius, hover states)
- [ ] 18.6 Style secondary buttons (#FFFFFF background, #E7E1D4 border, hover states)
- [ ] 18.7 Style text inputs (#EFEAE0 background, #E7E1D4 border, #A8412C focus, 8px radius)
- [ ] 18.8 Style panels with borders, padding, shadows matching Streamlit
- [ ] 18.9 Style badges with various color variants (default, success, warning)
- [ ] 18.10 Style document cards with borders, padding, spacing
- [ ] 18.11 Style telemetry tables with row borders, padding, highlighting
- [ ] 18.12 Style graph SVG elements (nodes, edges, labels)
- [ ] 18.13 Implement hover and focus states for all interactive elements
- [ ] 18.14 Add transition animations (0.2s ease) for state changes
- [ ] 18.15 Ensure all font sizes, weights, colors match Streamlit exactly
- [ ] 18.16 Test CSS across Chrome, Firefox, Safari for consistency

## Phase 19: Accessibility

- [ ] 19.1 Add ARIA labels to all icon buttons
- [ ] 19.2 Ensure all form inputs have associated <label> elements or aria-label
- [ ] 19.3 Implement keyboard navigation for all interactive elements
- [ ] 19.4 Add visible focus indicators for keyboard users
- [ ] 19.5 Implement aria-live regions for dynamic content updates (loading states, toasts)
- [ ] 19.6 Verify color contrast ratios meet WCAG 2.1 AA standards (4.5:1 for normal text)
- [ ] 19.7 Add alt text for any meaningful images
- [ ] 19.8 Ensure tab order follows logical visual flow
- [ ] 19.9 Test with keyboard-only navigation
- [ ] 19.10 Run axe-core automated accessibility tests

## Phase 20: Testing

- [ ] 20.1 Set up Jest and React Testing Library
- [ ] 20.2 Write unit tests for TraditionalPanel component (rendering, prop handling)
- [ ] 20.3 Write unit tests for ContextGraphPanel component (tab switching, rendering)
- [ ] 20.4 Write unit tests for GraphVisualizer component (node positioning, click handling)
- [ ] 20.5 Write unit tests for TelemetryCard component (conditional row rendering)
- [ ] 20.6 Write unit tests for UserProfileSwitcher component (selection, event emission)
- [ ] 20.7 Write unit tests for TabNavigation component (filtering, active state)
- [ ] 20.8 Write unit tests for ChatTab component (turn grouping, reverse order)
- [ ] 20.9 Write unit tests for CompareTab component (parallel execution, button state)
- [ ] 20.10 Write unit tests for AnalyticsTab component (scope switching, fallback detection)
- [ ] 20.11 Write unit tests for AdminTab component (sub-tab rendering, form validation)
- [ ] 20.12 Write unit tests for SessionList component (sorting, filtering, preview)
- [ ] 20.13 Write unit tests for markdown-to-HTML utility function
- [ ] 20.14 Write unit tests for node position calculation utility
- [ ] 20.15 Write unit tests for API response adapter functions
- [ ] 20.16 Write unit tests for RBAC permission calculation logic
- [ ] 20.17 Write integration test for query execution flow (Compare tab)
- [ ] 20.18 Write integration test for session persistence (Chat tab)
- [ ] 20.19 Write integration test for RBAC tab filtering
- [ ] 20.20 Write integration test for parallel query execution
- [ ] 20.21 Write integration test for background task monitoring
- [ ] 20.22 Write integration test for graph interaction (Analytics tab)
- [ ] 20.23 Set up visual regression testing with Percy or Chromatic
- [ ] 20.24 Capture baseline screenshots of Streamlit app (3 breakpoints)
- [ ] 20.25 Compare React screenshots to Streamlit baselines
- [ ] 20.26 Achieve ≥ 80% line coverage for unit tests
- [ ] 20.27 Achieve 100% coverage for utility functions

## Phase 21: Performance Optimization

- [ ] 21.1 Implement code splitting for Admin tab components using React.lazy()
- [ ] 21.2 Add Suspense boundaries with loading fallbacks
- [ ] 21.3 Memoize GraphVisualizer SVG generation with React.memo()
- [ ] 21.4 Implement virtual scrolling for large chat history (react-window)
- [ ] 21.5 Optimize session list loading with pagination or infinite scroll
- [ ] 21.6 Implement request debouncing for rapid query submissions
- [ ] 21.7 Add request cancellation for abandoned queries (AbortController)
- [ ] 21.8 Optimize bundle size with tree shaking and minification
- [ ] 21.9 Measure and optimize Time to Interactive (TTI) metric
- [ ] 21.10 Ensure 60 FPS scroll performance for all tabs

## Phase 22: Error Handling

- [ ] 22.1 Implement error boundary for component rendering errors
- [ ] 22.2 Add try-catch blocks for API calls with error state management
- [ ] 22.3 Display error messages in affected panels without crashing app
- [ ] 22.4 Handle parallel query failures independently (one fails, other succeeds)
- [ ] 22.5 Implement graceful session load error handling
- [ ] 22.6 Handle file system errors (ENOENT, write failures) without crashing
- [ ] 22.7 Add network timeout error messages (240 seconds)
- [ ] 22.8 Implement fallback UI for missing data (empty graphs, no sessions)
- [ ] 22.9 Log errors to console for debugging
- [ ] 22.10 Consider adding Sentry or similar error tracking service

## Phase 23: Deployment

- [ ] 23.1 Configure environment variables (REACT_APP_API_BASE)
- [ ] 23.2 Set up production build script (npm run build)
- [ ] 23.3 Optimize production build with minification and compression
- [ ] 23.4 Configure static file serving with correct MIME types
- [ ] 23.5 Set up client-side routing fallback (404.html redirecting to index.html)
- [ ] 23.6 Deploy to Vercel/Netlify/Cloudflare Pages (or preferred platform)
- [ ] 23.7 Configure custom domain (if applicable)
- [ ] 23.8 Set up HTTPS with SSL certificate
- [ ] 23.9 Configure CORS headers for API requests
- [ ] 23.10 Set up CI/CD pipeline for automated builds on git push
- [ ] 23.11 Configure environment-specific API base URLs (dev, staging, prod)
- [ ] 23.12 Set up monitoring and error tracking (Sentry, LogRocket)
- [ ] 23.13 Create deployment documentation with step-by-step instructions

## Phase 24: Documentation & Training

- [ ] 24.1 Write comprehensive README.md with project overview
- [ ] 24.2 Document setup instructions for local development
- [ ] 24.3 Document build and deployment process
- [ ] 24.4 Create architecture documentation explaining component hierarchy
- [ ] 24.5 Document API integration patterns and response adapters
- [ ] 24.6 Document RBAC permission system and role configuration
- [ ] 24.7 Document CSS theme and styling conventions
- [ ] 24.8 Create troubleshooting guide for common issues
- [ ] 24.9 Write user guide for non-technical stakeholders
- [ ] 24.10 Conduct training session for team members
- [ ] 24.11 Create video walkthrough demonstrating key features
- [ ] 24.12 Document known differences from Streamlit (if any)

## Phase 25: Quality Assurance

- [ ] 25.1 Conduct visual comparison testing against Streamlit (99%+ pixel similarity)
- [ ] 25.2 Test all 4 tabs with multiple user roles (5 roles × 4 tabs = 20 combinations)
- [ ] 25.3 Test query execution in Compare tab (10+ different queries)
- [ ] 25.4 Test multi-turn chat in Chat tab (5+ sessions, 10+ turns each)
- [ ] 25.5 Test session persistence (save, reload, verify data integrity)
- [ ] 25.6 Test graph interaction in Analytics tab (click 20+ different nodes)
- [ ] 25.7 Test RBAC tab filtering (switch between all 5 user profiles)
- [ ] 25.8 Test admin operations (create/delete users, ingest documents, view audit logs)
- [ ] 25.9 Test error scenarios (API failure, network timeout, session load error)
- [ ] 25.10 Test cross-browser compatibility (Chrome, Firefox, Safari, Edge)
- [ ] 25.11 Test performance (page load time, query execution time, scroll performance)
- [ ] 25.12 Conduct accessibility audit (keyboard navigation, screen reader, contrast ratios)
- [ ] 25.13 Test responsive behavior at 3 breakpoints (1024px, 1440px, 1920px)
- [ ] 25.14 Conduct user acceptance testing with stakeholders
- [ ] 25.15 Document and fix any identified issues

## Phase 26: Final Polish

- [ ] 26.1 Review all CSS for pixel-perfect alignment with Streamlit
- [ ] 26.2 Verify all colors match exactly using color picker tool
- [ ] 26.3 Verify all font sizes, weights, and line heights match
- [ ] 26.4 Verify all spacing, padding, and margins match
- [ ] 26.5 Verify all hover, focus, active states match
- [ ] 26.6 Test all toast notifications (appearance, timing, styling)
- [ ] 26.7 Test all loading states (spinners, skeleton screens)
- [ ] 26.8 Verify all icons and emoji render correctly
- [ ] 26.9 Check for any console errors or warnings
- [ ] 26.10 Optimize asset loading (lazy loading, caching)
- [ ] 26.11 Add meta tags for SEO (if applicable)
- [ ] 26.12 Add favicon matching brand identity
- [ ] 26.13 Final code review with team
- [ ] 26.14 Final stakeholder approval

## Total Tasks: 243
