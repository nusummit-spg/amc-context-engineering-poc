import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import "./UploadPanel.css";

const SUPPORTED = [".pdf", ".docx", ".pptx", ".xlsx", ".msg", ".eml", ".md", ".txt"];
const POLL_MS = 1500;

function newJobEntry(file) {
  return {
    key: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    filename: file.name,
    sizeKb: Math.round(file.size / 1024),
    status: "uploading",   // uploading | queued | running | completed | failed | error
    progress: null,
    error: null,
    jobId: null,
  };
}

export default function UploadPanel({ onIngestComplete }) {
  const [jobs, setJobs] = useState([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const pollTimers = useRef({});

  useEffect(() => () => Object.values(pollTimers.current).forEach(clearInterval), []);

  function updateJob(key, patch) {
    setJobs((prev) => prev.map((j) => (j.key === key ? { ...j, ...patch } : j)));
  }

  function pollStatus(key, jobId) {
    pollTimers.current[key] = setInterval(async () => {
      try {
        const status = await api.getIngestStatus(jobId);
        updateJob(key, { status: status.status, progress: status.progress });
        if (["completed", "failed"].includes(status.status)) {
          clearInterval(pollTimers.current[key]);
          // Real backend ingest finished — taxonomy doc counts and the
          // knowledge graph may now have new nodes, so let the Ontology
          // View know it should re-fetch.
          if (status.status === "completed") onIngestComplete?.();
        }
      } catch (err) {
        clearInterval(pollTimers.current[key]);
        updateJob(key, { status: "error", error: err });
      }
    }, POLL_MS);
  }

  const uploadFiles = useCallback((fileList) => {
    const files = Array.from(fileList);
    files.forEach(async (file) => {
      const entry = newJobEntry(file);
      setJobs((prev) => [entry, ...prev]);
      try {
        const res = await api.ingestFile(file);
        updateJob(entry.key, { status: res.status, jobId: res.job_id });
        pollStatus(entry.key, res.job_id);
      } catch (err) {
        const isDemo = err instanceof ApiError && (err.status === 0 || err.status === 502);
        if (isDemo) {
          // No live backend — simulate a realistic ingest run so the flow is reviewable offline.
          updateJob(entry.key, { status: "queued", progress: { stage: "parsing", docs_done: 0, docs_total: 1 } });
          simulateIngest(entry.key, updateJob);
        } else {
          updateJob(entry.key, { status: "failed", error: err });
        }
      }
    });
  }, []);

  function simulateIngest(key, update) {
    const stages = ["parsing", "chunking", "classifying", "extracting entities", "indexing"];
    let i = 0;
    const timer = setInterval(() => {
      i += 1;
      if (i >= stages.length) {
        update(key, { status: "completed", progress: { stage: "done", docs_done: 1, docs_total: 1 } });
        clearInterval(timer);
        return;
      }
      update(key, { status: "running", progress: { stage: stages[i], docs_done: 0, docs_total: 1 } });
    }, 700);
  }

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
  }

  return (
    <div className="upload-panel">
      <div
        className={`upload-panel__zone ${dragging ? "is-dragging" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
      >
        <div className="upload-panel__icon" aria-hidden="true">↥</div>
        <p><strong>Drop files here</strong> or click to browse</p>
        <p className="upload-panel__types">{SUPPORTED.join("  ·  ")}</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="visually-hidden"
          onChange={(e) => e.target.files?.length && uploadFiles(e.target.files)}
        />
      </div>

      {jobs.length > 0 && (
        <div className="upload-panel__jobs">
          <span className="eyebrow">Ingest jobs, this session</span>
          <ul>
            {jobs.map((j) => <JobRow job={j} key={j.key} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

const STATUS_META = {
  uploading: { label: "Uploading…", tone: "" },
  queued: { label: "Queued", tone: "" },
  running: { label: "Processing", tone: "blue" },
  completed: { label: "Completed", tone: "moss" },
  failed: { label: "Failed", tone: "brick" },
  error: { label: "Error", tone: "brick" },
};

function JobRow({ job }) {
  const meta = STATUS_META[job.status] || STATUS_META.queued;
  const pct = job.progress?.docs_total
    ? Math.round((job.progress.docs_done / job.progress.docs_total) * 100)
    : job.status === "completed" ? 100 : job.status === "running" ? 60 : 15;

  return (
    <li className="job-row">
      <div className="job-row__head">
        <span className="job-row__name">{job.filename}</span>
        <span className={`badge ${meta.tone ? `badge--${meta.tone}` : ""}`}>{meta.label}</span>
      </div>
      <div className="job-row__bar">
        <div className={`job-row__bar-fill job-row__bar-fill--${job.status}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="job-row__meta">
        <span>{job.sizeKb} KB</span>
        {job.progress?.stage && <span>· {job.progress.stage}</span>}
        {job.jobId && <span className="mono">· job {job.jobId.slice(0, 8)}</span>}
      </div>
      {job.error && <p className="job-row__error">{job.error.message}</p>}
    </li>
  );
}
