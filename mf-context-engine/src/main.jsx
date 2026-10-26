import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/streamlit-theme.css";
import App from "./App.jsx";
import { AppStateProvider } from "./state/AppState";
import { ToastProvider } from "./components/widgets/Toast";
import ErrorBoundary from "./components/ErrorBoundary";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ErrorBoundary>
      <AppStateProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AppStateProvider>
    </ErrorBoundary>
  </StrictMode>
);
