# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
issue_matcher.py
================
Two-stage (exact + semantic) Issue Matcher with Entity & Taxonomy Cross-Checks
for the Contextual Feedback Status Awareness Feature.

Matches incoming queries against open FeedbackIssue records in three stages:
1. Stage 1 (<1ms): Exact query hash matching against open issues.
2. Stage 2 (~20-30ms): FAISS vector cosine similarity matching against open issues.
3. Stage 3 (Guard): Canonical entity and taxonomy overlap verification to prevent
   false positives across different subjects/domains.
"""

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import faiss
import numpy as np
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.engine.intent_cache import classify_domain_intent
from app.feedback import issue_store
from app.schemas.feedback_issues_table import (
    CLOSED_ISSUE_STATUSES,
    OPEN_ISSUE_STATUSES,
    FeedbackIssue,
    IssueStatus,
)

logger = logging.getLogger("app.feedback.issue_matcher")

DEFAULT_BANNER_MESSAGE = (
    "A similar query has already been reported. The issue is pending review or repair."
)


@dataclass
class IssueMatchResult:
    """Result of an IssueMatcher lookup probe."""
    matched: bool
    issue_id: Optional[str] = None
    status: Optional[str] = None
    match_type: Optional[str] = None  # "exact" | "semantic"
    similarity_score: Optional[float] = None
    message: Optional[str] = None
    contributor_count: Optional[int] = None


def _token_vector_fallback(text: str, dim: int = 384) -> np.ndarray:
    """Deterministic token/3-gram hashing vector fallback.

    Args:
        text (str): Input text content.
        dim (int): The dim.

    Returns:
        np.ndarray: Resulting np.ndarray instance.
    """
    clean = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = clean.split()
    vec = np.zeros(dim, dtype=np.float32)

    tokens = list(words)
    for w in words:
        if len(w) >= 3:
            tokens.extend([w[i : i + 3] for i in range(len(w) - 2)])

    from collections import Counter
    counts = Counter(tokens)
    for token, count in counts.items():
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += count

    norm = np.linalg.norm(vec)
    if norm > 1e-9:
        vec /= norm
    return vec


class IssueMatcher:
    """Matches queries against open feedback issues using exact + FAISS semantic + entity/taxonomy checks."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        dim: int = 384,
    ):
        """Initialize a new instance of IssueMatcher.

        Args:
            similarity_threshold (float): The similarity threshold.
            dim (int): The dim.
        """
        env_thresh = os.getenv("FEEDBACK_MATCH_THRESHOLD")
        self.similarity_threshold = (
            float(env_thresh) if env_thresh is not None else similarity_threshold
        )
        self.dim = dim
        self._lock = threading.Lock()

        # Dedicated FAISS index for open issues
        self._index = faiss.IndexFlatIP(dim)
        self._issue_ids: List[str] = []
        self._issue_metadata: Dict[str, Dict[str, Any]] = {}
        self._embedding_cache: Dict[str, np.ndarray] = {}

        # Canonical entity resolution seed map
        self._alias_map: Dict[str, str] = {}
        self._load_alias_seed()

        # FastEmbed / SentenceTransformer lazy embedder
        self._embedder = None
        self._embedder_type = None

    def _load_alias_seed(self) -> None:
        """Load entity alias dictionary from backend/seeds/entity_aliases.json."""
        seed_path = Path(__file__).resolve().parents[2] / "seeds" / "entity_aliases.json"
        if not seed_path.exists():
            # Try alternate path
            seed_path = Path(__file__).resolve().parents[3] / "seeds" / "entity_aliases.json"
        if not seed_path.exists():
            logger.debug("Alias seed path not found: %s", seed_path)
            return

        try:
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            for item in data.get("entities", []):
                canon = item.get("canonical_name")
                if not canon:
                    continue
                self._alias_map[canon.lower()] = canon
                for alias in item.get("aliases", []):
                    self._alias_map[alias.lower()] = canon
        except Exception as exc:
            logger.debug("Failed to load entity aliases in IssueMatcher: %s", exc)

    def _init_embedder(self) -> None:
        """Attempt to initialize embedding provider with fallbacks."""
        if self._embedder is not None:
            return

        # 1. Try FastEmbed
        try:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            self._embedder_type = "fastembed"
            return
        except Exception:
            pass

        # 2. Try SentenceTransformer
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self._embedder_type = "sentence_transformer"
            return
        except Exception:
            pass

        self._embedder_type = "fallback"

    def _get_embedding(self, text: str) -> np.ndarray:
        """Compute unit-normalized embedding vector for text.

        Args:
            text (str): Input text content.

        Returns:
            np.ndarray: Resulting np.ndarray instance.
        """
        clean = text.strip().lower()
        cache_key = hashlib.md5(clean.encode("utf-8")).hexdigest()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        self._init_embedder()
        vec = None

        if self._embedder_type == "fastembed":
            try:
                raw_gen = list(self._embedder.embed([clean]))
                if raw_gen:
                    vec = np.array(raw_gen[0], dtype=np.float32)
            except Exception as exc:
                logger.debug("FastEmbed error in IssueMatcher: %s", exc)

        elif self._embedder_type == "sentence_transformer":
            try:
                raw = self._embedder.encode(clean)
                vec = np.array(raw, dtype=np.float32)
            except Exception as exc:
                logger.debug("SentenceTransformer error in IssueMatcher: %s", exc)

        if vec is None:
            vec = _token_vector_fallback(clean, self.dim)

        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        else:
            vec = np.zeros(self.dim, dtype=np.float32)

        self._embedding_cache[cache_key] = vec
        return vec

    def extract_canonical_entities(self, text: str) -> List[str]:
        """Extract canonical entities mentioned in text using alias map and surface matching.

        Args:
            text (str): Input text content.

        Returns:
            List[str]: List of resulting items or records.
        """
        if not text:
            return []
        lower_text = text.lower()
        found: Set[str] = set()

        # Check longest aliases first to avoid substring false positives
        sorted_aliases = sorted(self._alias_map.keys(), key=lambda a: len(a), reverse=True)
        for alias in sorted_aliases:
            # Word-boundary or punctuation matching
            pattern = r"(?:\b|^)" + re.escape(alias) + r"(?:\b|$)"
            if re.search(pattern, lower_text):
                found.add(self._alias_map[alias])

        return sorted(list(found))

    def extract_taxonomy_paths(self, text: str) -> List[str]:
        """Extract taxonomy paths / domain classifications for query.

        Args:
            text (str): Input text content.

        Returns:
            List[str]: List of resulting items or records.
        """
        if not text:
            return []
        domain = classify_domain_intent(text)
        return [domain] if domain else []

    def sync_open_issues(self, db: Session, tenant_id: Optional[str] = None) -> None:
        """Rebuild in-memory FAISS index from open FeedbackIssue records in the database.

        Args:
            db (Session): Database session instance.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
        with self._lock:
            open_issues = issue_store.get_open_issues(db, tenant_id=tenant_id)
            new_index = faiss.IndexFlatIP(self.dim)
            new_issue_ids: List[str] = []
            new_metadata: Dict[str, Dict[str, Any]] = {}

            if open_issues:
                vectors = []
                for issue in open_issues:
                    vec = self._get_embedding(issue.canonical_query_text)
                    vectors.append(vec)
                    new_issue_ids.append(issue.issue_id)
                    new_metadata[issue.issue_id] = {
                        "canonical_query_text": issue.canonical_query_text,
                        "query_hash": issue.query_hash,
                        "primary_entities": issue.primary_entities or [],
                        "taxonomy_paths": issue.taxonomy_paths or [],
                        "status": issue.status,
                        "contributor_count": issue.contributor_count,
                        "tenant_id": issue.tenant_id,
                    }
                stacked = np.vstack(vectors).astype(np.float32)
                new_index.add(stacked)

            self._index = new_index
            self._issue_ids = new_issue_ids
            self._issue_metadata = new_metadata
            logger.info("[ISSUE_MATCHER_SYNCED] Synced %d open issues into FAISS index", len(new_issue_ids))

    def _index_open_issue(self, issue: FeedbackIssue) -> None:
        """Add a single newly created open issue into the FAISS index.

        Args:
            issue (FeedbackIssue): The issue.
        """
        with self._lock:
            vec = self._get_embedding(issue.canonical_query_text)
            self._index.add(vec.reshape(1, -1).astype(np.float32))
            self._issue_ids.append(issue.issue_id)
            self._issue_metadata[issue.issue_id] = {
                "canonical_query_text": issue.canonical_query_text,
                "query_hash": issue.query_hash,
                "primary_entities": issue.primary_entities or [],
                "taxonomy_paths": issue.taxonomy_paths or [],
                "status": issue.status,
                "contributor_count": issue.contributor_count,
                "tenant_id": issue.tenant_id,
            }

    def _verify_entity_and_taxonomy_overlap(
        self,
        query_entities: List[str],
        cand_entities: List[str],
        query_taxonomy: List[str],
        cand_taxonomy: List[str],
    ) -> bool:
        """Stage 3 Guard:
        Confirms Stage 2 semantic match candidates against entity and taxonomy overlap.
        Prevents matching queries with identical phrasing but different subject entities
        (e.g., 'What is the ESG score of Adani Enterprises?' vs. 'What is the ESG score of Ambuja?').

        Args:
            query_entities (List[str]): Collection or list of query entities.
            cand_entities (List[str]): Collection or list of cand entities.
            query_taxonomy (List[str]): The query taxonomy.
            cand_taxonomy (List[str]): The cand taxonomy.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        q_ent = {e.lower().strip() for e in query_entities if e}
        c_ent = {e.lower().strip() for e in cand_entities if e}

        # If both mention entities, they MUST overlap
        if q_ent and c_ent:
            if not (q_ent & c_ent):
                return False

        # If one mentions an entity and the other mentions a different entity or none,
        # reject if one has a concrete entity while the other does not
        if (q_ent and not c_ent) or (c_ent and not q_ent):
            return False

        # Taxonomy overlap check
        q_tax = {t.lower().strip() for t in query_taxonomy if t}
        c_tax = {t.lower().strip() for t in cand_taxonomy if t}
        if q_tax and c_tax:
            overlap = any(
                qt == ct or qt.startswith(ct) or ct.startswith(qt)
                for qt in q_tax
                for ct in c_tax
            )
            if not overlap:
                return False

        return True

    def lookup(
        self,
        query: str,
        db: Session,
        tenant_id: Optional[str] = None,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
    ) -> Optional[IssueMatchResult]:
        """Read-only lookup probe called when feedback modal opens (GET /api/feedback/status).
        Returns IssueMatchResult if an open matching issue is found, else None.

        Args:
            query (str): Search query or input text.
            db (Session): Database session instance.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            primary_entities (Optional[List[str]]): Collection or list of primary entities.
            taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.

        Returns:
            Optional[IssueMatchResult]: Matching object or record if found, None otherwise.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            return None

        # --- Stage 1: Exact Hash Match (<1ms) ---
        query_hash = hashlib.md5(clean_query.lower().encode("utf-8")).hexdigest()
        exact_issue = issue_store.get_open_issue_by_hash(db, query_hash, tenant_id=tenant_id)

        if exact_issue:
            logger.info(
                "[ISSUE_MATCH_EXACT] Exact query match found issue_id=%s status=%s",
                exact_issue.issue_id,
                exact_issue.status,
            )
            return IssueMatchResult(
                matched=True,
                issue_id=exact_issue.issue_id,
                status=exact_issue.status,
                match_type="exact",
                similarity_score=1.0,
                message=DEFAULT_BANNER_MESSAGE,
                contributor_count=exact_issue.contributor_count,
            )

        # --- Stage 2: Semantic (FAISS) Match (~20-30ms) ---
        # Ensure FAISS index is populated
        if self._index.ntotal == 0:
            self.sync_open_issues(db, tenant_id=tenant_id)

        if self._index.ntotal == 0:
            return None

        query_vec = self._get_embedding(clean_query)
        k = min(5, self._index.ntotal)
        distances, indices = self._index.search(
            query_vec.reshape(1, -1).astype(np.float32), k=k
        )

        resolved_query_entities = (
            primary_entities
            if primary_entities is not None
            else self.extract_canonical_entities(clean_query)
        )
        resolved_query_taxonomy = (
            taxonomy_paths
            if taxonomy_paths is not None
            else self.extract_taxonomy_paths(clean_query)
        )

        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._issue_ids):
                continue

            similarity = float(score)
            if similarity < self.similarity_threshold:
                continue

            cand_issue_id = self._issue_ids[idx]
            cand_meta = self._issue_metadata.get(cand_issue_id)
            if not cand_meta:
                cand_db = issue_store.get_issue_by_id(db, cand_issue_id)
                if not cand_db or cand_db.status not in OPEN_ISSUE_STATUSES:
                    continue
                cand_meta = {
                    "canonical_query_text": cand_db.canonical_query_text,
                    "primary_entities": cand_db.primary_entities or [],
                    "taxonomy_paths": cand_db.taxonomy_paths or [],
                    "status": cand_db.status,
                    "contributor_count": cand_db.contributor_count,
                    "tenant_id": cand_db.tenant_id,
                }

            # Tenant isolation check
            if tenant_id and cand_meta.get("tenant_id") and cand_meta["tenant_id"] != tenant_id:
                continue

            # --- Stage 3: Entity/Taxonomy Cross-Check ---
            cand_entities = cand_meta.get("primary_entities", [])
            cand_taxonomy = cand_meta.get("taxonomy_paths", [])

            is_valid = self._verify_entity_and_taxonomy_overlap(
                query_entities=resolved_query_entities,
                cand_entities=cand_entities,
                query_taxonomy=resolved_query_taxonomy,
                cand_taxonomy=cand_taxonomy,
            )

            if not is_valid:
                logger.info(
                    "[ISSUE_MATCH_REJECTED] Rejected semantic candidate issue_id=%s (sim=%.3f) due to entity/taxonomy mismatch",
                    cand_issue_id,
                    similarity,
                )
                continue

            logger.info(
                "[ISSUE_MATCH_SEMANTIC] Semantic match found issue_id=%s sim=%.3f",
                cand_issue_id,
                similarity,
            )
            # Fetch latest status and contributor count from DB
            live_issue = issue_store.get_issue_by_id(db, cand_issue_id)
            if not live_issue or live_issue.status not in OPEN_ISSUE_STATUSES:
                logger.info("[ISSUE_MATCH_SKIPPED] Matched issue %s is no longer open in DB", cand_issue_id)
                continue

            live_status = live_issue.status
            live_contributors = live_issue.contributor_count

            # Keep in-memory cache aligned
            if cand_issue_id in self._issue_metadata:
                self._issue_metadata[cand_issue_id]["status"] = live_status
                self._issue_metadata[cand_issue_id]["contributor_count"] = live_contributors

            return IssueMatchResult(
                matched=True,
                issue_id=cand_issue_id,
                status=live_status,
                match_type="semantic",
                similarity_score=round(similarity, 4),
                message=DEFAULT_BANNER_MESSAGE,
                contributor_count=live_contributors,
            )

        return None

    def find_or_create(
        self,
        query: str,
        db: Session,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
    ) -> Tuple[FeedbackIssue, str, bool]:
        """Finds matching open issue or creates a new FeedbackIssue.
        Returns:
            (issue, match_type, was_matched_to_existing_issue)
            where match_type in ("exact", "semantic", "new")

        Args:
            query (str): Search query or input text.
            db (Session): Database session instance.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            actor_id (Optional[str]): Unique identifier of the actor.
            primary_entities (Optional[List[str]]): Collection or list of primary entities.
            taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            clean_query = "unspecified query"

        match = self.lookup(
            query=clean_query,
            db=db,
            tenant_id=tenant_id,
            primary_entities=primary_entities,
            taxonomy_paths=taxonomy_paths,
        )

        if match and match.issue_id:
            existing_issue = issue_store.get_issue_by_id(db, match.issue_id)
            if existing_issue:
                # Update contributor count if new contributor
                if actor_id:
                    issue_store.record_contributor(db, existing_issue, actor_id)
                # Reopen if needed
                existing_issue = issue_store.reopen_issue_if_resolved(db, existing_issue)
                return existing_issue, match.match_type or "exact", True

        # No open match found -> Check if an existing resolved/closed issue should be reopened
        query_hash = hashlib.md5(clean_query.lower().encode("utf-8")).hexdigest()
        closed_issue = issue_store.get_closed_issue_by_hash(db, query_hash, tenant_id=tenant_id)
        if closed_issue:
            reopened = issue_store.reopen_issue_if_resolved(db, closed_issue)
            if actor_id:
                issue_store.record_contributor(db, reopened, actor_id)
            self._index_open_issue(reopened)
            logger.info(
                "[ISSUE_REOPENED_ON_SUBMIT] Reopened closed issue issue_id=%s for incoming feedback",
                reopened.issue_id,
            )
            return reopened, "exact", True

        # No existing open or closed issue -> CREATE new FeedbackIssue
        resolved_entities = (
            primary_entities
            if primary_entities is not None
            else self.extract_canonical_entities(clean_query)
        )
        resolved_taxonomy = (
            taxonomy_paths
            if taxonomy_paths is not None
            else self.extract_taxonomy_paths(clean_query)
        )

        try:
            new_issue = issue_store.create_issue(
                db=db,
                canonical_query_text=clean_query,
                query_hash=query_hash,
                primary_entities=resolved_entities,
                taxonomy_paths=resolved_taxonomy,
                tenant_id=tenant_id,
                status=IssueStatus.REPORTED.value,
                contributor_count=1,
            )
            # Add to FAISS index
            self._index_open_issue(new_issue)
            return new_issue, "new", False
        except IntegrityError:
            db.rollback()
            # Concurrency race handling: another process inserted an issue with the same query_hash
            winner = issue_store.get_open_issue_by_hash(db, query_hash, tenant_id=tenant_id)
            if winner:
                if actor_id:
                    issue_store.record_contributor(db, winner, actor_id)
                return winner, "exact", True
            raise


_matcher_instance: Optional[IssueMatcher] = None


def get_issue_matcher() -> IssueMatcher:
    """Singleton accessor for IssueMatcher.

    Returns:
        IssueMatcher: Resulting IssueMatcher instance.
    """
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = IssueMatcher()
    return _matcher_instance


def reset_issue_matcher() -> None:
    """Reset singleton instance (useful for test isolation)."""
    global _matcher_instance
    _matcher_instance = None
