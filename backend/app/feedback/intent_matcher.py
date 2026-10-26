# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
intent_matcher.py
=================
Semantic Query Intent Matcher for Feedback Pending Repair Notifications.
Identifies when incoming user queries match existing user feedback entries
where repairs are still pending (open or diagnosing).

Key Constraints & Edge Cases handled:
- Match query semantic intent (threshold default: 0.88)
- selected_categories is NOT NULL/empty
- feedback_text is NOT NULL/empty
- Repair status is 'pending' (UnifiedEvaluationRecord: repair == 1 and lifecycle_status in ['open', 'diagnosing'])
- Invalidation / suppression on intent cache clear
- Same-user query suppression (actor_id match)
- Cross-domain mismatch filtering
- Privacy protection: original query hidden from non-admin users
- Graceful degradation on DB or embedder error
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.engine.intent_cache import classify_domain_intent
from app.models.feedback import PendingFeedbackNotice
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord

logger = logging.getLogger("app.feedback.intent_matcher")

# Feature flag for instant disable / rollback
ENABLE_PENDING_FEEDBACK_NOTICE = os.getenv("ENABLE_PENDING_FEEDBACK_NOTICE", "true").lower() == "true"

# Global in-memory caches
_pending_feedback_cache: Dict[str, Tuple[float, Optional[PendingFeedbackNotice]]] = {}
_embedding_cache: Dict[str, Tuple[float, np.ndarray]] = {}
_last_cache_clear_time: float = 0.0


def clear_pending_feedback_cache(suppress_prior_feedbacks: bool = True) -> None:
    """Clear in-memory notice cache and optionally record cache-clear timestamp.

    Args:
        suppress_prior_feedbacks (bool): Collection or list of suppress prior feedbacks.
    """
    global _pending_feedback_cache, _last_cache_clear_time
    _pending_feedback_cache.clear()
    if suppress_prior_feedbacks:
        _last_cache_clear_time = time.time()
    logger.info(
        "[PENDING_FEEDBACK] Notice cache cleared (suppress_prior_feedbacks=%s, ts=%.3f)",
        suppress_prior_feedbacks,
        _last_cache_clear_time,
    )


def reset_cache_clear_timestamp() -> None:
    """Reset the cache clear timestamp (useful for testing)."""
    global _last_cache_clear_time
    _last_cache_clear_time = 0.0


def _parse_iso_timestamp(ts_str: Optional[str]) -> Optional[float]:
    """Parse an ISO format timestamp string into epoch seconds.

    Args:
        ts_str (Optional[str]): The ts str.

    Returns:
        Optional[float]: Matching object or record if found, None otherwise.
    """
    if not ts_str:
        return None
    try:
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        return dt.timestamp()
    except Exception:
        return None


def _token_vector_fallback(text: str, dim: int = 384) -> np.ndarray:
    """Lightweight deterministic character 3-gram hashing vector fallback.
    Produces stable embeddings and normalized cosine similarity without heavy neural models.

    Args:
        text (str): Input text content.
        dim (int): The dim.

    Returns:
        np.ndarray: Resulting np.ndarray instance.
    """
    clean = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = clean.split()
    vec = np.zeros(dim, dtype=np.float32)

    # Combine word tokens and character 3-grams
    tokens = list(words)
    for w in words:
        if len(w) >= 3:
            tokens.extend([w[i : i + 3] for i in range(len(w) - 2)])

    counts = Counter(tokens)
    for token, count in counts.items():
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += count

    norm = np.linalg.norm(vec)
    if norm > 1e-9:
        vec /= norm
    return vec


class FeedbackIntentMatcher:
    """Matches query intent against existing feedback database to detect pending repairs."""

    def __init__(
        self,
        similarity_threshold: float = 0.88,
        embedder_model: str = "all-MiniLM-L6-v2",
        cache_ttl_seconds: int = 300,
    ):
        """Initialize a new instance of FeedbackIntentMatcher.

        Args:
            similarity_threshold (float): The similarity threshold.
            embedder_model (str): The embedder model.
            cache_ttl_seconds (int): Collection or list of cache ttl seconds.
        """
        env_thresh = os.getenv("FEEDBACK_SIMILARITY_THRESHOLD")
        self.similarity_threshold = float(env_thresh) if env_thresh is not None else similarity_threshold
        self.embedder_model = embedder_model
        self.cache_ttl_seconds = cache_ttl_seconds
        self._semaphore = asyncio.Semaphore(20)

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get or compute normalized text embedding with caching and fallbacks.

        Args:
            text (str): Input text content.

        Returns:
            np.ndarray: Resulting np.ndarray instance.
        """
        text_clean = text.strip()
        cache_key = hashlib.md5(text_clean.lower().encode("utf-8")).hexdigest()

        now = time.time()
        if cache_key in _embedding_cache:
            ts, vec = _embedding_cache[cache_key]
            if now - ts < 3600:  # 1 hr TTL for embeddings
                return vec

        # 1. Try SentenceTransformer embedder
        try:
            from app.feedback.dissatisfaction_detector import get_embedder
            embedder = get_embedder(self.embedder_model)
            if embedder is not None:
                raw_emb = embedder.encode(text_clean)
                vec = np.array(raw_emb, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 1e-9:
                    vec /= norm
                _embedding_cache[cache_key] = (now, vec)
                return vec
        except Exception as exc:
            logger.debug("SentenceTransformer embedding failed in intent_matcher: %s", exc)

        # 2. Try fastembed if available
        try:
            from fastembed import TextEmbedding
            fe = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            raw_gen = list(fe.embed([text_clean]))
            if raw_gen:
                vec = np.array(raw_gen[0], dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 1e-9:
                    vec /= norm
                _embedding_cache[cache_key] = (now, vec)
                return vec
        except Exception:
            pass

        # 3. Fallback deterministic character/token vector
        vec = _token_vector_fallback(text_clean)
        _embedding_cache[cache_key] = (now, vec)
        return vec

    def _is_cache_valid(self, query_hash: str) -> Tuple[bool, Optional[PendingFeedbackNotice]]:
        """Check if query result is cached and not expired.

        Args:
            query_hash (str): The query hash.

        Returns:
            Tuple[bool, Optional[PendingFeedbackNotice]]: Matching object or record if found, None otherwise.
        """
        now = time.time()
        if query_hash in _pending_feedback_cache:
            cached_at, notice = _pending_feedback_cache[query_hash]
            if now - cached_at < self.cache_ttl_seconds:
                return True, notice
            else:
                del _pending_feedback_cache[query_hash]
        return False, None

    async def check_pending_feedback(
        self,
        query: str,
        session_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        db: Optional[Session] = None,
        role: Optional[str] = None,
    ) -> Optional[PendingFeedbackNotice]:
        """Main entry point to check if similar query has pending feedback.

        Returns:
            PendingFeedbackNotice if a match is found and pending repair, else None.

        Args:
            query (str): Search query or input text.
            session_id (Optional[str]): Unique identifier of the session.
            actor_id (Optional[str]): Unique identifier of the actor.
            db (Optional[Session]): Database session instance.
            role (Optional[str]): Role assigned to the user or entity.
        """
        if not ENABLE_PENDING_FEEDBACK_NOTICE:
            return None

        clean_query = (query or "").strip()
        if not clean_query:
            return None

        # Build query cache key
        query_hash = hashlib.md5(
            f"{clean_query.lower()}|{actor_id or ''}|{session_id or ''}|{role or ''}".encode("utf-8")
        ).hexdigest()

        hit, cached_notice = self._is_cache_valid(query_hash)
        if hit:
            return cached_notice

        async with self._semaphore:
            # Check cache again inside semaphore
            hit, cached_notice = self._is_cache_valid(query_hash)
            if hit:
                return cached_notice

            # Use passed DB session or create local one
            owns_db = False
            active_db = db
            if active_db is None:
                active_db = SessionLocal()
                owns_db = True

            try:
                notice = await asyncio.to_thread(
                    self._check_pending_feedback_sync,
                    clean_query,
                    session_id,
                    actor_id,
                    active_db,
                    role,
                )
                _pending_feedback_cache[query_hash] = (time.time(), notice)
                return notice
            except Exception as exc:
                logger.warning("Error checking pending feedback: %s", exc)
                return None
            finally:
                if owns_db and active_db is not None:
                    try:
                        active_db.close()
                    except Exception:
                        pass

    def _check_pending_feedback_sync(
        self,
        query: str,
        session_id: Optional[str],
        actor_id: Optional[str],
        db: Session,
        role: Optional[str],
    ) -> Optional[PendingFeedbackNotice]:
        """Synchronous implementation executed off event loop.

        Args:
            query (str): Search query or input text.
            session_id (Optional[str]): Unique identifier of the session.
            actor_id (Optional[str]): Unique identifier of the actor.
            db (Session): Database session instance.
            role (Optional[str]): Role assigned to the user or entity.

        Returns:
            Optional[PendingFeedbackNotice]: Matching object or record if found, None otherwise.
        """
        # Step 1: Fetch candidate feedback entries
        candidates = (
            db.query(ResponseFeedback)
            .filter(
                ResponseFeedback.selected_categories.isnot(None),
                ResponseFeedback.feedback_text.isnot(None),
                ResponseFeedback.feedback_text != "",
                ResponseFeedback.query_text.isnot(None),
                ResponseFeedback.query_text != "",
            )
            .all()
        )

        if not candidates:
            return None

        query_domain = classify_domain_intent(query)
        query_embedding = self._get_embedding(query)

        valid_matches = []

        for cand in candidates:
            # Constraint 2 & 3: selected_categories and feedback_text not empty
            categories = cand.selected_categories
            if not categories or (isinstance(categories, list) and len(categories) == 0):
                continue

            fb_text = (cand.feedback_text or "").strip()
            if not fb_text:
                continue

            cand_q = (cand.query_text or "").strip()
            if not cand_q:
                continue

            # Constraint 5: Cache clear suppression
            if _last_cache_clear_time > 0:
                cand_created_ts = _parse_iso_timestamp(cand.created_at)
                if cand_created_ts and cand_created_ts <= _last_cache_clear_time:
                    continue

            # Edge Case 4: Same user re-querying
            if actor_id and cand.actor_id and cand.actor_id == actor_id:
                continue
            if session_id and cand.session_id and cand.session_id == session_id:
                if not actor_id or cand.actor_id == actor_id:
                    continue

            # Edge Case 8: Domain mismatch prevention
            cand_domain = classify_domain_intent(cand_q)
            if query_domain != cand_domain:
                # Different functional domain — skip to prevent false positives
                continue

            # Step 2: Compute semantic similarity
            cand_embedding = self._get_embedding(cand_q)
            similarity = float(np.dot(query_embedding, cand_embedding))

            # Exact string match override
            if query.lower() == cand_q.lower():
                similarity = max(similarity, 1.0)

            if similarity >= self.similarity_threshold:
                # Step 3: Check repair status in UnifiedEvaluationRecord
                uer = (
                    db.query(UnifiedEvaluationRecord)
                    .filter(UnifiedEvaluationRecord.response_id == cand.response_id)
                    .first()
                )
                if not uer and cand.unified_record_ref:
                    uer = (
                        db.query(UnifiedEvaluationRecord)
                        .filter(UnifiedEvaluationRecord.response_id == cand.unified_record_ref)
                        .first()
                    )
                if not uer and cand.feedback_id:
                    uer = (
                        db.query(UnifiedEvaluationRecord)
                        .filter(UnifiedEvaluationRecord.feedback_ref == cand.feedback_id)
                        .first()
                    )

                # Edge Case 2 & 3: Repair status check
                if not uer:
                    continue

                lifecycle_status_val = (
                    uer.lifecycle_status.value
                    if hasattr(uer.lifecycle_status, "value")
                    else str(uer.lifecycle_status).lower()
                )

                is_repair_pending = (
                    bool(uer.repair) and lifecycle_status_val in ("open", "diagnosing")
                )

                if is_repair_pending:
                    valid_matches.append(
                        {
                            "candidate": cand,
                            "uer": uer,
                            "similarity": similarity,
                            "lifecycle_status": lifecycle_status_val,
                        }
                    )

        if not valid_matches:
            return None

        # Edge Case 1: Multiple pending feedbacks -> pick highest similarity score
        valid_matches.sort(key=lambda m: m["similarity"], reverse=True)
        top = valid_matches[0]
        top_cand: ResponseFeedback = top["candidate"]

        is_admin = role and "admin" in role.lower()

        return PendingFeedbackNotice(
            has_pending_feedback=True,
            similarity_score=round(top["similarity"], 4),
            original_query_text=top_cand.query_text if is_admin else None,
            feedback_submitted_at=top_cand.created_at,
            feedback_categories=top_cand.selected_categories or [],
            repair_lifecycle_status=top["lifecycle_status"],
            match_count=len(valid_matches),
            suppressed_by_cache_clear=False,
        )


_matcher_instance: Optional[FeedbackIntentMatcher] = None


def get_intent_matcher() -> FeedbackIntentMatcher:
    """Singleton accessor for FeedbackIntentMatcher.

    Returns:
        FeedbackIntentMatcher: Resulting FeedbackIntentMatcher instance.
    """
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = FeedbackIntentMatcher()
    return _matcher_instance
