# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
cypher_audit_log.py
===================
Compliance audit logging for Cypher queries executed via the feedback loop.
Writes structured JSON records to dedicated audit file for 90-day retention.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import threading

logger = logging.getLogger("app.graph.cypher_audit")


class CypherAuditLogger:
    """
    Compliance audit trail for Cypher queries executed via feedback evaluation.
    Logs each query execution with timestamps, query parameters, timing, and errors.
    """
    _instance: Optional["CypherAuditLogger"] = None
    _lock = threading.Lock()

    def __init__(self, log_file: str = "logs/cypher_audit.jsonl"):
        """Initialize a new instance of CypherAuditLogger.

        Args:
            log_file (str): The log file.
        """
        self.log_path = Path(log_file)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    @classmethod
    def get_logger(cls, log_file: str = "logs/cypher_audit.jsonl") -> "CypherAuditLogger":
        """Retrieve logger.

        Args:
            log_file (str): The log file.

        Returns:
            'CypherAuditLogger': Resulting 'CypherAuditLogger' instance.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(log_file)
            return cls._instance

    def log_query(
        self,
        query_method: str,
        parameters: Dict[str, Any],
        rows_returned: int,
        duration_ms: float,
        user_context: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record a structured Cypher query execution entry.

        Args:
            query_method (str): The query method.
            parameters (Dict[str, Any]): Collection or list of parameters.
            rows_returned (int): The rows returned.
            duration_ms (float): Collection or list of duration ms.
            user_context (Optional[Dict[str, Any]]): The user context.
            error (Optional[str]): The error.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query_method": query_method,
            "parameters": parameters,
            "rows_returned": rows_returned,
            "duration_ms": round(duration_ms, 2),
            "user_context": user_context or {},
            "error": error,
            "success": error is None
        }

        try:
            line = json.dumps(record)
            with self._write_lock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as exc:
            logger.error("Failed to write to cypher audit log: %s", exc)

        return record
