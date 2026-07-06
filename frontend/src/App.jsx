import { useState, useCallback } from "react";
import Header from "./components/layout/Header";
import UploadPanel from "./components/upload/UploadPanel";
import DocumentModal from "./components/corpus/DocumentModal";
import ComparePage from "./components/compare/ComparePage";
import Modal from "./components/common/Modal";
import { useBackendStatus } from "./hooks/useBackendStatus";
import "./components/layout/AppShell.css";

export default function App() {
  const { status: backendStatus, refreshKey: statusRefreshKey } = useBackendStatus();
  const [openDocumentId, setOpenDocumentId] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [ingestRefreshKey, setIngestRefreshKey] = useState(0);

  const handleIngestComplete = useCallback(() => {
    setIngestRefreshKey((k) => k + 1);
  }, []);

  const dataRefreshKey = statusRefreshKey + ingestRefreshKey;

  return (
    <div className="app-shell">
      <div className="app-shell__main">
        <Header status={backendStatus} />
        <div className="app-shell__content">
          <div className="app-shell__content-inner">
            <ComparePage onOpenDocument={setOpenDocumentId} refreshKey={dataRefreshKey} />
          </div>
        </div>
      </div>

      <button
        className="upload-fab"
        onClick={() => setUploadOpen(true)}
        aria-label="Upload documents"
        title="Upload documents"
      >
        <span className="upload-fab__icon" aria-hidden="true">↥</span>
        <span className="upload-fab__label">Upload</span>
      </button>

      {uploadOpen && (
        <Modal title="Upload Documents" eyebrow="Add to the corpus" onClose={() => setUploadOpen(false)}>
          <UploadPanel onIngestComplete={handleIngestComplete} />
        </Modal>
      )}

      {openDocumentId && (
        <DocumentModal documentId={openDocumentId} onClose={() => setOpenDocumentId(null)} />
      )}
    </div>
  );
}
