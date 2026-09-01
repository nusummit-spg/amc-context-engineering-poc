# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Idempotent Ingestion Ledger.

Tracks document versions through the ingestion pipeline stages:
  - parsed
  - chunked
  - graph_written
  - vector_written
  - validated
  - activated
  - failed

Ensures retries resume safely and never duplicate vector or graph writes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ingestion.ledger")


class IngestionStage(str, Enum):
    PARSED = "parsed"
    CHUNKED = "chunked"
    GRAPH_WRITTEN = "graph_written"
    VECTOR_WRITTEN = "vector_written"
    VALIDATED = "validated"
    ACTIVATED = "activated"
    FAILED = "failed"


class IngestionLedger:
    def __init__(self, corpus_version: str = "v2_baseline_20260814", ledger_dir: Optional[Path] = None):
        self.corpus_version = corpus_version
        self.ledger_dir = ledger_dir or Path("./data/corpora") / corpus_version
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_file = self.ledger_dir / "ledger.json"
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.ledger_file.exists():
            try:
                self._entries = json.loads(self.ledger_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not read ledger file %s: %s", self.ledger_file, exc)
                self._entries = {}

    def _persist(self) -> None:
        try:
            self.ledger_file.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to write ledger file %s: %s", self.ledger_file, exc)

    def record_stage(
        self,
        document_version_id: str,
        stage: IngestionStage,
        metadata: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        entry = self._entries.setdefault(document_version_id, {
            "document_version_id": document_version_id,
            "corpus_version": self.corpus_version,
            "history": [],
            "current_stage": stage.value,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        entry["current_stage"] = stage.value
        entry["updated_at"] = datetime.utcnow().isoformat()
        if error:
            entry["error"] = error
        if metadata:
            entry.setdefault("metadata", {}).update(metadata)
        entry["history"].append({
            "stage": stage.value,
            "timestamp": datetime.utcnow().isoformat(),
            "error": error,
        })
        self._persist()

    def is_activated(self, document_version_id: str) -> bool:
        entry = self._entries.get(document_version_id)
        return entry is not None and entry.get("current_stage") == IngestionStage.ACTIVATED.value

    def get_stage(self, document_version_id: str) -> Optional[str]:
        entry = self._entries.get(document_version_id)
        return entry.get("current_stage") if entry else None

    def get_all_entries(self) -> dict[str, dict[str, Any]]:
        return self._entries
