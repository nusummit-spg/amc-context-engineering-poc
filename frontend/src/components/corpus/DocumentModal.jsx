import Modal from "../common/Modal";
import { useResource } from "../../hooks/useResource";
import { api } from "../../api/client";
import { MOCK_DOCS, getMockChunks } from "../../data/mockData";
import { SkeletonLine } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice } from "../common/Banners";

export default function DocumentModal({ documentId, onClose }) {
  const mockDoc = MOCK_DOCS.find((d) => d.document_id === documentId);
  const mockValue = mockDoc ? { ...mockDoc, chunks: getMockChunks(documentId) } : undefined;

  const { data, loading, error, isMock, reload } = useResource(
    (signal) => api.getDocument(documentId, signal),
    { deps: [documentId], mockValue }
  );

  return (
    <Modal title={data?.title || data?.filename || "Document"} eyebrow="Raw Corpus" onClose={onClose}>
      {isMock && <DemoModeNotice compact />}
      {loading && (
        <div>
          <SkeletonLine width="70%" height={16} />
          <SkeletonLine width="90%" />
          <SkeletonLine width="85%" />
          <SkeletonLine width="60%" />
        </div>
      )}
      {error && <ErrorBanner error={error} onRetry={reload} title="Couldn't load this document" />}
      {data && (
        <div className="doc-detail">
          <dl className="doc-detail__meta">
            <div><dt>Type</dt><dd>{data.doc_type}</dd></div>
            <div><dt>Category</dt><dd>{data.category}</dd></div>
            {data.author && <div><dt>Author</dt><dd>{data.author}</dd></div>}
            <div><dt>Chunks</dt><dd>{data.chunk_count}</dd></div>
          </dl>
          {data.taxonomy_paths?.length > 0 && (
            <div className="doc-detail__paths">
              {data.taxonomy_paths.map((p) => <span className="badge badge--clay" key={p}>{p}</span>)}
            </div>
          )}
          <div className="doc-detail__chunks">
            <span className="eyebrow">Chunk preview</span>
            {(data.chunks || []).map((c) => (
              <p className="doc-detail__chunk" key={c.chunk_id}>
                <span className="doc-detail__chunk-order mono">#{c.order}</span> {c.text}
              </p>
            ))}
            {(!data.chunks || data.chunks.length === 0) && <p className="walkthrough__empty">No chunk text available.</p>}
          </div>
        </div>
      )}
    </Modal>
  );
}
