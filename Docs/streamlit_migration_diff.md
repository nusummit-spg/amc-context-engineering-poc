# Streamlit to React Migration Differences & Enhancements

## Key Architectural & UX Enhancements

| Area | Legacy Streamlit Implementation | React 18 + Vite Production Implementation |
|---|---|---|
| **Rendering Model** | Full-page rerun on every button click or input | Zero full-page reruns; granular React state updates |
| **Parallel Execution** | Sequential or blocking execution | True async `Promise.all` with independent error boundaries |
| **Graph Visualizer** | Static iframe or reloaded HTML string | Pure client-side SVG with interactive node exploration |
| **Session Persistence** | Memory-bound session state | Resilient JSON session persistence to disk |
| **Styling & Design** | Streamlit default theme overrides | Pixel-perfect design system matching terracotta theme with WCAG AA compliance |
| **Accessibility** | Basic default Streamlit markup | ARIA roles, focus-visible outlines, live regions for screen readers |
| **Performance** | Multi-second page reloads | <1s initial load, route code-splitting, memoized SVG rendering |
