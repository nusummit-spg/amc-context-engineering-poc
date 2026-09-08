# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
review_queue_repository.py
==========================
Persistent repository for the Human Review Queue.
Supports SQLite (zero-dependency file/memory mode) and optional MongoDB Motor integration.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.schemas.review_queue import ReviewQueueItem, ReviewReason, ReviewStatus

logger = logging.getLogger("review_queue_repo")

# How many times the governance batch may retry a failing patch before the item
# is retired. Guards against a permanently un-deployable patch being retried
# every week forever.
MAX_GOVERNANCE_ATTEMPTS = 3


class ReviewQueueRepository:
    """Thread-safe Review Queue Repository with SQLite backing and optional MongoDB driver."""

    def __init__(self, db_or_path: Optional[Any] = None):
        self._lock = threading.Lock()
        self._is_mongo = False
        self._mongo_col = None

        # Detect if Mongo client/collection passed
        if db_or_path is not None and hasattr(db_or_path, "review_queue"):
            self._is_mongo = True
            self._mongo_col = db_or_path.review_queue
        elif db_or_path is not None and hasattr(db_or_path, "insert_one"):
            self._is_mongo = True
            self._mongo_col = db_or_path
        else:
            # SQLite path setup
            if isinstance(db_or_path, str):
                self._db_path = db_or_path
            else:
                db_dir = Path(__file__).resolve().parent.parent / "data"
                db_dir.mkdir(parents=True, exist_ok=True)
                self._db_path = str(db_dir / "review_queue.db")

            self._init_sqlite()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self):
        """Initialize schema in SQLite."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS review_queue (
                        id TEXT PRIMARY KEY,
                        response_id TEXT NOT NULL,
                        query TEXT NOT NULL,
                        user_answer TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        confidence_score REAL NOT NULL,
                        priority INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        assigned_to TEXT,
                        verdict TEXT,
                        notes TEXT,
                        rejection_reason TEXT,
                        rejected_by TEXT,
                        rejected_at TEXT,
                        resolved_by TEXT,
                        resolved_at TEXT,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_rq_assigned ON review_queue(assigned_to);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_rq_resp_id ON review_queue(response_id);")
                conn.commit()
            finally:
                conn.close()

    def _calculate_priority(self, reason: str, confidence_score: float) -> int:
        """Lower number = higher priority."""
        if reason in (ReviewReason.HALLUCINATION_DETECTED.value, ReviewReason.COMPLIANCE_VIOLATION.value):
            return 1
        if confidence_score < 0.25:
            return 2
        if confidence_score < 0.45:
            return 4
        if reason == ReviewReason.CONFIDENCE_LOW.value:
            return 5
        return 6

    async def enqueue(self, item: ReviewQueueItem, auto_priority: bool = True) -> str:
        """Add item to review queue.

        By default the priority is derived from reason + confidence. Callers that
        have already set an explicit, non-default priority should pass
        auto_priority=False to keep it.
        """
        # ReviewQueueItem.priority defaults to 5, so "falsy" is never true here —
        # treat the schema default as "unset" and let the heuristic decide.
        if auto_priority and item.priority in (None, 0, 5):
            item.priority = self._calculate_priority(item.reason, item.confidence_score)

        if self._is_mongo:
            doc = item.model_dump()
            doc["_id"] = item.id
            await self._mongo_col.insert_one(doc)
            return item.id

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO review_queue (
                        id, response_id, query, user_answer, reason, confidence_score,
                        priority, status, assigned_to, verdict, notes, rejection_reason,
                        rejected_by, rejected_at, resolved_by, resolved_at, created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.id,
                    item.response_id,
                    item.query,
                    item.user_answer,
                    item.reason if isinstance(item.reason, str) else item.reason.value,
                    item.confidence_score,
                    item.priority,
                    item.status if isinstance(item.status, str) else item.status.value,
                    item.assigned_to,
                    item.verdict,
                    item.notes,
                    item.rejection_reason,
                    item.rejected_by,
                    item.rejected_at.isoformat() if item.rejected_at else None,
                    item.resolved_by,
                    item.resolved_at.isoformat() if item.resolved_at else None,
                    item.created_at.isoformat() if item.created_at else datetime.utcnow().isoformat(),
                    json.dumps(item.metadata or {})
                ))
                conn.commit()
                return item.id
            finally:
                conn.close()

    def _row_to_item(self, row: sqlite3.Row) -> ReviewQueueItem:
        meta = {}
        if row["metadata_json"]:
            try:
                meta = json.loads(row["metadata_json"])
            except Exception:
                meta = {}

        return ReviewQueueItem(
            id=row["id"],
            response_id=row["response_id"],
            query=row["query"],
            user_answer=row["user_answer"],
            reason=ReviewReason(row["reason"]),
            confidence_score=float(row["confidence_score"]),
            priority=int(row["priority"]),
            status=ReviewStatus(row["status"]),
            assigned_to=row["assigned_to"],
            verdict=row["verdict"],
            notes=row["notes"],
            rejection_reason=row["rejection_reason"],
            rejected_by=row["rejected_by"],
            rejected_at=datetime.fromisoformat(row["rejected_at"]) if row["rejected_at"] else None,
            resolved_by=row["resolved_by"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            metadata=meta
        )

    async def get_by_id(self, item_id: str) -> Optional[ReviewQueueItem]:
        """Look up review item by ID."""
        if self._is_mongo:
            doc = await self._mongo_col.find_one({"$or": [{"_id": item_id}, {"id": item_id}]})
            return ReviewQueueItem(**doc) if doc else None

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM review_queue WHERE id = ?", (item_id,))
                row = cur.fetchone()
                return self._row_to_item(row) if row else None
            finally:
                conn.close()

    async def get_by_response_id(self, response_id: str) -> Optional[ReviewQueueItem]:
        """Look up review by response ID."""
        if self._is_mongo:
            doc = await self._mongo_col.find_one({"response_id": response_id})
            return ReviewQueueItem(**doc) if doc else None

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM review_queue WHERE response_id = ?", (response_id,))
                row = cur.fetchone()
                return self._row_to_item(row) if row else None
            finally:
                conn.close()

    async def get_pending_for_user(self, user_id: str, limit: int = 20) -> List[ReviewQueueItem]:
        """Get pending/in_review items assigned to specific user ordered by priority."""
        if self._is_mongo:
            cursor = self._mongo_col.find({
                "assigned_to": user_id,
                "status": {"$in": [ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]}
            }).sort("priority", 1).limit(limit)
            return [ReviewQueueItem(**d) async for d in cursor]

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("""
                    SELECT * FROM review_queue
                    WHERE assigned_to = ? AND status IN (?, ?)
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                """, (user_id, ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value, limit))
                return [self._row_to_item(r) for r in cur.fetchall()]
            finally:
                conn.close()

    async def get_unassigned(self, limit: int = 20) -> List[ReviewQueueItem]:
        """Get pending items that are unassigned."""
        if self._is_mongo:
            cursor = self._mongo_col.find({
                "assigned_to": None,
                "status": ReviewStatus.PENDING.value
            }).sort("priority", 1).limit(limit)
            return [ReviewQueueItem(**d) async for d in cursor]

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("""
                    SELECT * FROM review_queue
                    WHERE (assigned_to IS NULL OR assigned_to = '') AND status = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                """, (ReviewStatus.PENDING.value, limit))
                return [self._row_to_item(r) for r in cur.fetchall()]
            finally:
                conn.close()

    async def assign_to_user(self, item_id: str, user_id: str) -> bool:
        """Assign item to reviewer."""
        if self._is_mongo:
            res = await self._mongo_col.update_one(
                {"$or": [{"_id": item_id}, {"id": item_id}]},
                {"$set": {
                    "assigned_to": user_id,
                    "status": ReviewStatus.IN_REVIEW.value
                }}
            )
            return res.modified_count > 0

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("""
                    UPDATE review_queue
                    SET assigned_to = ?, status = ?
                    WHERE id = ?
                """, (user_id, ReviewStatus.IN_REVIEW.value, item_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def approve(self, item_id: str, verdict: str, notes: str, reviewer_id: str) -> bool:
        """Approve and resolve review item."""
        now = datetime.utcnow()
        if self._is_mongo:
            res = await self._mongo_col.update_one(
                {"$or": [{"_id": item_id}, {"id": item_id}]},
                {"$set": {
                    "status": ReviewStatus.APPROVED.value,
                    "verdict": verdict,
                    "notes": notes,
                    "resolved_by": reviewer_id,
                    "resolved_at": now
                }}
            )
            return res.modified_count > 0

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("""
                    UPDATE review_queue
                    SET status = ?, verdict = ?, notes = ?, resolved_by = ?, resolved_at = ?
                    WHERE id = ?
                """, (ReviewStatus.APPROVED.value, verdict, notes, reviewer_id, now.isoformat(), item_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def reject(self, item_id: str, reason: str, reviewer_id: str) -> bool:
        """Reject and return review to pending queue unassigned."""
        now = datetime.utcnow()
        if self._is_mongo:
            res = await self._mongo_col.update_one(
                {"$or": [{"_id": item_id}, {"id": item_id}]},
                {"$set": {
                    "status": ReviewStatus.PENDING.value,
                    "assigned_to": None,
                    "rejection_reason": reason,
                    "rejected_by": reviewer_id,
                    "rejected_at": now
                }}
            )
            return res.modified_count > 0

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("""
                    UPDATE review_queue
                    SET status = ?, assigned_to = NULL, rejection_reason = ?, rejected_by = ?, rejected_at = ?
                    WHERE id = ?
                """, (ReviewStatus.PENDING.value, reason, reviewer_id, now.isoformat(), item_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def get_resolved_for_governance(
        self,
        lookback_days: int = 7,
        verdicts: Optional[List[str]] = None,
        limit: int = 500,
    ) -> List[ReviewQueueItem]:
        """
        Fetch approved items whose verdict calls for a knowledge-graph correction
        and that have not yet been deployed by a governance batch.

        Used by the weekly governance batch (Task 1.2).
        """
        verdicts = verdicts or ["needs_correction", "partially_correct"]
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        cutoff_iso = cutoff.isoformat()

        if self._is_mongo:
            cursor = self._mongo_col.find({
                "status": ReviewStatus.APPROVED.value,
                "verdict": {"$in": verdicts},
                "resolved_at": {"$gte": cutoff},
                "metadata.governance_deployed_at": {"$exists": False},
            }).sort("priority", 1).limit(limit)
            return [ReviewQueueItem(**d) async for d in cursor]

        placeholders = ",".join("?" for _ in verdicts)
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(f"""
                    SELECT * FROM review_queue
                    WHERE status = ?
                      AND verdict IN ({placeholders})
                      AND resolved_at IS NOT NULL
                      AND resolved_at >= ?
                    ORDER BY priority ASC, resolved_at ASC
                    LIMIT ?
                """, (ReviewStatus.APPROVED.value, *verdicts, cutoff_iso, limit))
                items = [self._row_to_item(r) for r in cur.fetchall()]
            finally:
                conn.close()

        # Deployment marker lives in metadata JSON, so filter in Python.
        return [i for i in items if not (i.metadata or {}).get("governance_deployed_at")]

    async def mark_governance_deployed(
        self,
        item_id: str,
        deployment_status: str,
        patch_type: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Record the outcome of a governance-batch deployment on the item's metadata.

        A terminal outcome (success / skipped / pending_human) stamps
        governance_deployed_at, which retires the item from future batches. A
        failure only increments the attempt counter, so a transient outage
        (e.g. Neo4j down) leaves the correction eligible for the next run until
        MAX_GOVERNANCE_ATTEMPTS is reached.
        """
        item = await self.get_by_id(item_id)
        if item is None:
            return False

        metadata = dict(item.metadata or {})
        metadata["governance_deployment_status"] = deployment_status
        metadata["governance_last_attempt_at"] = datetime.utcnow().isoformat()
        if patch_type:
            metadata["governance_patch_type"] = patch_type

        if deployment_status == "failed":
            attempts = int(metadata.get("governance_attempts", 0)) + 1
            metadata["governance_attempts"] = attempts
            metadata["governance_deployment_error"] = error
            if attempts >= MAX_GOVERNANCE_ATTEMPTS:
                # Give up and retire the item so the batch stops retrying forever.
                metadata["governance_deployed_at"] = datetime.utcnow().isoformat()
                logger.warning(
                    "Review item %s exhausted %d governance deployment attempts; retiring",
                    item_id, attempts,
                )
        else:
            metadata["governance_deployed_at"] = datetime.utcnow().isoformat()
            if error:
                metadata["governance_deployment_error"] = error

        if self._is_mongo:
            res = await self._mongo_col.update_one(
                {"$or": [{"_id": item_id}, {"id": item_id}]},
                {"$set": {"metadata": metadata}},
            )
            return res.modified_count > 0

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "UPDATE review_queue SET metadata_json = ? WHERE id = ?",
                    (json.dumps(metadata), item_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def get_stats(self, time_range_days: int = 7) -> Dict[str, Any]:
        """Aggregate statistics over given time range."""
        cutoff = datetime.utcnow() - timedelta(days=time_range_days)
        cutoff_iso = cutoff.isoformat()

        if self._is_mongo:
            return await self._get_stats_mongo(cutoff)

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM review_queue WHERE created_at >= ?", (cutoff_iso,))
                rows = cur.fetchall()

                stats: Dict[str, Any] = {
                    "pending": {"count": 0},
                    "in_review": {"count": 0},
                    "approved": {"count": 0},
                    "rejected": {"count": 0},
                    "total": len(rows),
                    "by_reason": {},
                    "average_resolution_time_seconds": 0.0
                }

                resolution_times = []
                for r in rows:
                    status = r["status"]
                    if status in stats:
                        stats[status]["count"] += 1
                    else:
                        stats[status] = {"count": 1}

                    reason = r["reason"]
                    stats["by_reason"][reason] = stats["by_reason"].get(reason, 0) + 1

                    if r["resolved_at"] and r["created_at"]:
                        try:
                            t_start = datetime.fromisoformat(r["created_at"])
                            t_end = datetime.fromisoformat(r["resolved_at"])
                            diff = (t_end - t_start).total_seconds()
                            if diff >= 0:
                                resolution_times.append(diff)
                        except Exception:
                            pass

                if resolution_times:
                    avg_time = sum(resolution_times) / len(resolution_times)
                    stats["average_resolution_time_seconds"] = round(avg_time, 1)
                    stats["approved"]["avg_resolution_time"] = int(avg_time * 1000)

                return stats
            finally:
                conn.close()

    async def _get_stats_mongo(self, cutoff: datetime) -> Dict[str, Any]:
        """Aggregate statistics when backed by MongoDB.

        Previously get_stats() always took the SQLite path, which raised
        AttributeError (_db_path is never set in Mongo mode).
        """
        stats: Dict[str, Any] = {
            "pending": {"count": 0},
            "in_review": {"count": 0},
            "approved": {"count": 0},
            "rejected": {"count": 0},
            "total": 0,
            "by_reason": {},
            "average_resolution_time_seconds": 0.0,
        }

        resolution_times: List[float] = []
        cursor = self._mongo_col.find({"created_at": {"$gte": cutoff}})
        async for doc in cursor:
            stats["total"] += 1

            status = doc.get("status")
            if status in stats and isinstance(stats[status], dict):
                stats[status]["count"] += 1
            elif status:
                stats[status] = {"count": 1}

            reason = doc.get("reason")
            if reason:
                stats["by_reason"][reason] = stats["by_reason"].get(reason, 0) + 1

            created_at, resolved_at = doc.get("created_at"), doc.get("resolved_at")
            if created_at and resolved_at:
                try:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at)
                    if isinstance(resolved_at, str):
                        resolved_at = datetime.fromisoformat(resolved_at)
                    diff = (resolved_at - created_at).total_seconds()
                    if diff >= 0:
                        resolution_times.append(diff)
                except Exception:
                    pass

        if resolution_times:
            avg_time = sum(resolution_times) / len(resolution_times)
            stats["average_resolution_time_seconds"] = round(avg_time, 1)
            stats["approved"]["avg_resolution_time"] = int(avg_time * 1000)

        return stats


# Global default instance
_default_repo: Optional[ReviewQueueRepository] = None


def get_review_queue_repo(db=None) -> ReviewQueueRepository:
    global _default_repo
    if db is not None:
        return ReviewQueueRepository(db)
    if _default_repo is None:
        _default_repo = ReviewQueueRepository()
    return _default_repo
