# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
indexing_manager.py
===================
Manages asynchronous background document indexing, stage progress tracking,
and user acknowledgement / toast notification dispatch.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config

TASKS_LOG_FILE = config.LOG_DIR / "indexing_tasks.json"

_lock = threading.Lock()
_active_tasks: Dict[str, Dict[str, Any]] = {}
_worker_thread: Optional[threading.Thread] = None


class IndexingStage(str, Enum):
    QUEUED = "Queued in ingestion queue"
    EXTRACTING = "Extracting text and tables (OCR/PDF Parser)"
    PII_SCRUBBING = "Scrubbing PII & DPDP redactions"
    CHUNKING = "Building parent & child hierarchical chunks"
    NER_GRAPH = "Running 3-layer NER extraction & Neo4j graph update"
    EMBEDDING_FAISS = "Generating vector embeddings & updating FAISS index"
    RESOLVING = "Resolving cross-document entity links in Neo4j"
    COMPLETED = "Indexing completed successfully"
    FAILED = "Indexing failed"


def _load_persisted_tasks() -> Dict[str, Dict[str, Any]]:
    tasks = {}
    if TASKS_LOG_FILE.exists():
        try:
            with open(TASKS_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    tasks = data
        except Exception:
            pass
    return tasks


def _save_persisted_tasks(tasks: Dict[str, Dict[str, Any]]) -> None:
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = TASKS_LOG_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, default=str)
        if os.path.exists(temp_file):
            os.replace(temp_file, TASKS_LOG_FILE)
    except Exception as exc:
        print(f"  [indexing_manager] Failed to save tasks: {exc}", flush=True)


# Initialize in-memory cache from disk
with _lock:
    _active_tasks.update(_load_persisted_tasks())


def _update_task(task_id: str, **kwargs) -> None:
    with _lock:
        if task_id in _active_tasks:
            _active_tasks[task_id].update(kwargs)
            _active_tasks[task_id]["last_updated"] = datetime.now().isoformat()
            _save_persisted_tasks(_active_tasks)


def _index_worker(task_id: str, file_path_str: str, use_gemini: bool = True) -> None:
    file_path = Path(file_path_str)
    try:
        _update_task(
            task_id,
            status="PROCESSING",
            stage=IndexingStage.EXTRACTING.value,
            progress=0.15,
        )

        import document_extractors
        import faiss_store
        import graph_store
        import ner_pipeline
        import pii_scrub
        import taxonomy as taxonomy_mod
        import build_index

        print(f"[indexing_manager] Starting index task {task_id} for {file_path.name}", flush=True)

        # Step 0: Ensure taxonomy and neo4j schema
        taxonomy_mod.build_taxonomy()
        graph_store.init_schema()

        # Step 1: Extract document
        pages_data = document_extractors.extract_any(str(file_path), use_gemini=use_gemini)

        # Step 2: PII Scrubbing
        _update_task(
            task_id,
            stage=IndexingStage.PII_SCRUBBING.value,
            progress=0.30,
        )
        if config.PII_SCRUB_ENABLED:
            pages_data = pii_scrub.scrub_pages(pages_data)

        # Step 3: Chunking
        _update_task(
            task_id,
            stage=IndexingStage.CHUNKING.value,
            progress=0.45,
        )
        product_name = file_path.stem
        parents, children = faiss_store.build_parent_child_chunks(pages_data, product_name)

        # Step 4: NER & Neo4j graph
        _update_task(
            task_id,
            stage=IndexingStage.NER_GRAPH.value,
            progress=0.60,
        )
        parents_map = {p["parent_id"]: p for p in parents}
        ner_out = ner_pipeline.run_full_ner_for_chunk_set(children, parents_map)
        
        entities = ner_out.get("entities", [])
        relations = ner_out.get("relations", [])
        graph_store.upsert_entities(entities, product_name, file_path.name)
        graph_store.upsert_relations(relations, product_name, file_path.name)

        # Step 5: Embeddings & FAISS
        _update_task(
            task_id,
            stage=IndexingStage.EMBEDDING_FAISS.value,
            progress=0.80,
        )
        
        # Run master build to synchronize FAISS master index cleanly
        build_index.build(rebuild=False, use_gemini=use_gemini)

        # Step 6: Entity resolution
        _update_task(
            task_id,
            stage=IndexingStage.RESOLVING.value,
            progress=0.95,
        )
        try:
            graph_store.resolve_unresolved_entities()
        except Exception:
            pass

        # Update provenance ledger if available
        try:
            import provenance_ledger
            rec = provenance_ledger.find_by_filename(file_path.name)
            if rec:
                provenance_ledger.update_graph_node_count(file_path.name, len(entities))
        except Exception:
            pass

        # Step 7: Completed
        _update_task(
            task_id,
            status="COMPLETED",
            stage=IndexingStage.COMPLETED.value,
            progress=1.0,
            completed_at=datetime.now().isoformat(),
            chunks_count=len(children),
            parents_count=len(parents),
            entities_count=len(entities),
            relations_count=len(relations),
            unread_notification=True,
        )
        print(f"[indexing_manager] Task {task_id} COMPLETED for {file_path.name} ({len(entities)} entities, {len(children)} chunks)", flush=True)

    except Exception as exc:
        print(f"[indexing_manager] Task {task_id} FAILED for {file_path.name}: {exc}", flush=True)
        _update_task(
            task_id,
            status="FAILED",
            stage=IndexingStage.FAILED.value,
            progress=1.0,
            completed_at=datetime.now().isoformat(),
            error_message=str(exc),
            unread_notification=True,
        )


def start_background_indexing(
    file_path: Path | str,
    sha256: str,
    requested_by: str = "system",
    use_gemini: bool = True
) -> str:
    """
    Enqueues a document for background indexing and starts the background worker thread.
    Returns the task_id.
    """
    path_obj = Path(file_path)
    task_id = f"idx_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    
    task_data = {
        "task_id": task_id,
        "filename": path_obj.name,
        "file_path": str(path_obj.resolve()),
        "sha256_hash": sha256,
        "requested_by": requested_by,
        "status": "QUEUED",
        "stage": IndexingStage.QUEUED.value,
        "progress": 0.05,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "chunks_count": 0,
        "parents_count": 0,
        "entities_count": 0,
        "relations_count": 0,
        "error_message": None,
        "unread_notification": False,
        "last_updated": datetime.now().isoformat(),
    }

    with _lock:
        _active_tasks[task_id] = task_data
        _save_persisted_tasks(_active_tasks)

    worker = threading.Thread(
        target=_index_worker,
        args=(task_id, str(path_obj), use_gemini),
        daemon=True,
        name=f"IndexingWorker-{task_id}"
    )
    worker.start()

    return task_id


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _active_tasks.get(task_id)


def get_all_tasks(limit: int = 20) -> List[Dict[str, Any]]:
    with _lock:
        sorted_tasks = sorted(
            _active_tasks.values(),
            key=lambda t: t.get("started_at", ""),
            reverse=True
        )
        return sorted_tasks[:limit]


def get_unread_notifications() -> List[Dict[str, Any]]:
    with _lock:
        return [
            t for t in _active_tasks.values()
            if t.get("unread_notification") is True
        ]


def mark_notification_read(task_id: str) -> None:
    with _lock:
        if task_id in _active_tasks:
            _active_tasks[task_id]["unread_notification"] = False
            _save_persisted_tasks(_active_tasks)


def mark_all_notifications_read() -> None:
    with _lock:
        for t in _active_tasks.values():
            t["unread_notification"] = False
        _save_persisted_tasks(_active_tasks)
