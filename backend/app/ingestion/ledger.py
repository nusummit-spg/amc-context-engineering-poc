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
        """Initialize a new instance of IngestionLedger.

        Args:
            corpus_version (str): Version of the active document corpus.
            ledger_dir (Optional[Path]): The ledger dir.
        """
        self.corpus_version = corpus_version
        if ledger_dir:
            self.ledger_dir = Path(ledger_dir)
        else:
            candidates = [
                Path("./data/corpora") / corpus_version,
                Path(__file__).resolve().parent.parent.parent / "data" / "corpora" / corpus_version,
                Path(__file__).resolve().parent.parent.parent.parent / "data" / "corpora" / corpus_version,
            ]
            self.ledger_dir = candidates[0]
            for cand in candidates:
                if cand.exists():
                    self.ledger_dir = cand
                    break

        try:
            self.ledger_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create ledger dir %s: %s", self.ledger_dir, exc)

        self.ledger_file = self.ledger_dir / "ledger.json"
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load operation.
        """
        if self.ledger_file.exists():
            try:
                self._entries = json.loads(self.ledger_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not read ledger file %s: %s", self.ledger_file, exc)
                self._entries = {}

    def _persist(self) -> None:
        """Persist.
        """
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
        """Record stage.

        Args:
            document_version_id (str): Unique identifier of the document version.
            stage (IngestionStage): The stage.
            metadata (Optional[dict[str, Any]]): Associated metadata dictionary.
            error (Optional[str]): The error.
        """
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
        """Check whether activated.

        Args:
            document_version_id (str): Unique identifier of the document version.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        entry = self._entries.get(document_version_id)
        return entry is not None and entry.get("current_stage") == IngestionStage.ACTIVATED.value

    def get_stage(self, document_version_id: str) -> Optional[str]:
        """Retrieve stage.

        Args:
            document_version_id (str): Unique identifier of the document version.

        Returns:
            Optional[str]: Matching object or record if found, None otherwise.
        """
        entry = self._entries.get(document_version_id)
        return entry.get("current_stage") if entry else None

    def get_all_entries(self) -> dict[str, dict[str, Any]]:
        """Retrieve all entries.

        Returns:
            dict[str, dict[str, Any]]: Dictionary containing result data or status.
        """
        return self._entries
