# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
governance_batch.py
===================
Weekly Governance Batch Processor.
Processes approved review-queue corrections and patches the canonical Neo4j
knowledge graph.
Implements Task 1.2 of the Chief Architect Implementation Plan.

Flow:
  1. Fetch approved review items whose verdict requires a correction
  2. Generate a structured patch per item (PatchGenerator)
  3. Group patches by type
  4. Validate, then deploy each patch to Neo4j via parameterised Cypher
  5. Mark each source item as deployed / failed / skipped
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.review_queue_repository import ReviewQueueRepository, get_review_queue_repo
from app.evaluation.patch_generator import PatchGenerator
from app.schemas.review_queue import ReviewQueueItem, Verdict

logger = logging.getLogger("app.tasks.governance_batch")

# Patch types that this batch is allowed to auto-deploy. Everything else
# (manual_review, ambiguous) stays parked for a human decision.
AUTO_DEPLOYABLE_PATCH_TYPES = {"entity_update", "relationship_correction", "property_update"}


class GovernanceBatch:
    """Executes the scheduled weekly batch that applies approved corrections to the graph."""

    def __init__(
        self,
        review_repo: Optional[ReviewQueueRepository] = None,
        graph_store: Optional[Any] = None,
        patch_generator: Optional[PatchGenerator] = None,
    ):
        self.review_repo = review_repo or get_review_queue_repo()
        self._graph_store = graph_store
        self.patch_generator = patch_generator or PatchGenerator()

    # ── Graph access ──────────────────────────────────────────────────────

    @property
    def graph_store(self) -> Optional[Any]:
        """Resolve the graph store lazily from the DI container when not injected."""
        if self._graph_store is None:
            try:
                from app.api import deps

                container = deps.get_container()
                self._graph_store = getattr(container, "graph", None)
            except Exception as exc:
                logger.debug("Graph store unavailable to governance batch: %s", exc)
        return self._graph_store

    async def _run_cypher(self, cypher: str, params: Dict[str, Any]) -> bool:
        """Execute one parameterised Cypher statement against the graph store.

        Graph clients in this codebase disagree on how parameters are passed:
        Neo4jClient.run() takes **params, while other stores take a dict. Try
        keyword form first and fall back to positional dict.
        """
        store = self.graph_store
        if store is None:
            raise RuntimeError("No graph store available for patch deployment")

        for method in ("run_cypher", "run", "execute_write", "execute"):
            fn = getattr(store, method, None)
            if fn is None:
                continue
            try:
                result = fn(cypher, **params)
            except TypeError:
                result = fn(cypher, params)
            if hasattr(result, "__await__"):
                await result
            return True

        raise RuntimeError(f"Graph store {type(store).__name__} exposes no known Cypher execution method")

    # ── Batch entry point ─────────────────────────────────────────────────

    async def process(self, lookback_days: int = 7) -> Dict[str, Any]:
        """
        Process approved reviews needing corrections from the lookback period.

        Returns a report dict: {"deployed", "failed", "skipped", "considered",
        "by_type", "errors", "started_at", "finished_at"}.
        """
        started_at = datetime.utcnow()
        logger.info("Starting governance batch processing (lookback=%d days)...", lookback_days)

        report: Dict[str, Any] = {
            "considered": 0,
            "deployed": 0,
            "failed": 0,
            "skipped": 0,
            "by_type": {},
            "errors": [],
            "started_at": started_at.isoformat(),
        }

        try:
            items = await self.review_repo.get_resolved_for_governance(lookback_days=lookback_days)
        except Exception as exc:
            logger.error("Could not fetch governance candidates: %s", exc, exc_info=True)
            report["errors"].append(f"fetch_failed: {exc}")
            report["finished_at"] = datetime.utcnow().isoformat()
            return report

        report["considered"] = len(items)
        if not items:
            logger.info("No approved corrections pending deployment this batch")
            report["finished_at"] = datetime.utcnow().isoformat()
            return report

        logger.info("Found %d approved correction(s) for deployment", len(items))

        # Abort before touching anything if the graph is unreachable: otherwise
        # every candidate would burn a retry attempt on the same outage.
        if self.graph_store is None:
            msg = "Graph store unavailable; deferring governance batch to the next run"
            logger.warning(msg)
            report["errors"].append(msg)
            report["deferred"] = len(items)
            report["finished_at"] = datetime.utcnow().isoformat()
            return report

        # 1. Generate patches
        patches: List[Dict[str, Any]] = []
        for item in items:
            patch = await self._generate_patch_for(item)
            if patch is None:
                report["skipped"] += 1
                await self._mark(item, "skipped", None, "No patch required for verdict")
                continue
            patch["_item"] = item
            patches.append(patch)

        # 2. Group by patch type so related graph writes land together
        grouped = self._group_patches(patches)

        # 3. Deploy
        for patch_type, group in grouped.items():
            report["by_type"][patch_type] = len(group)

            if patch_type not in AUTO_DEPLOYABLE_PATCH_TYPES:
                logger.info("Patch type '%s' requires human action; parking %d item(s)", patch_type, len(group))
                for patch in group:
                    report["skipped"] += 1
                    await self._mark(patch["_item"], "pending_human", patch_type, None)
                continue

            for patch in group:
                item = patch["_item"]
                try:
                    deployed = await self._deploy_patch(patch)
                    if deployed:
                        report["deployed"] += 1
                        await self._mark(item, "success", patch_type, None)
                        logger.info("Deployed %s patch for review item %s", patch_type, item.id)
                    else:
                        report["failed"] += 1
                        await self._mark(item, "failed", patch_type, "Deployment returned False")
                except Exception as exc:
                    report["failed"] += 1
                    report["errors"].append(f"{item.id}: {exc}")
                    logger.error("Failed to deploy patch for item %s: %s", item.id, exc, exc_info=True)
                    await self._mark(item, "failed", patch_type, str(exc))

        report["finished_at"] = datetime.utcnow().isoformat()
        logger.info(
            "Governance batch complete: %d deployed, %d failed, %d skipped (of %d considered)",
            report["deployed"], report["failed"], report["skipped"], report["considered"],
        )
        return report

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _generate_patch_for(self, item: ReviewQueueItem) -> Optional[Dict[str, Any]]:
        """Turn one resolved review item into a structured patch."""
        try:
            verdict = Verdict(item.verdict) if item.verdict else Verdict.NEEDS_CORRECTION
        except ValueError:
            logger.warning("Unrecognised verdict '%s' on item %s; treating as needs_correction", item.verdict, item.id)
            verdict = Verdict.NEEDS_CORRECTION

        return await self.patch_generator.generate_patch(
            feedback_id=item.id,
            response_id=item.response_id,
            verdict=verdict,
            query=item.query,
            llm_answer=item.user_answer,
            retrieved_context=(item.metadata or {}).get("context", ""),
            reviewer_id=item.resolved_by or "governance_batch",
            reviewer_notes=item.notes or "",
        )

    def _group_patches(self, patches: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group patches by type for batch processing."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for patch in patches:
            grouped.setdefault(patch.get("patch_type", "unknown"), []).append(patch)
        return grouped

    async def _mark(
        self,
        item: ReviewQueueItem,
        status: str,
        patch_type: Optional[str],
        error: Optional[str],
    ) -> None:
        try:
            await self.review_repo.mark_governance_deployed(
                item_id=item.id,
                deployment_status=status,
                patch_type=patch_type,
                error=error,
            )
        except Exception as exc:
            logger.warning("Could not mark item %s as %s: %s", item.id, status, exc)

    # ── Deployment by patch type ──────────────────────────────────────────

    async def _deploy_patch(self, patch: Dict[str, Any]) -> bool:
        """Dispatch a patch to the handler for its type."""
        patch_type = patch.get("patch_type")
        handlers = {
            "entity_update": self._deploy_entity_patch,
            "property_update": self._deploy_property_patch,
            "relationship_correction": self._deploy_relationship_patch,
        }
        handler = handlers.get(patch_type)
        if handler is None:
            logger.warning("Unknown patch type: %s", patch_type)
            return False
        return await handler(patch)

    async def _deploy_entity_patch(self, patch: Dict[str, Any]) -> bool:
        """Annotate an entity with the approved correction.

        All values travel as Cypher parameters — never string-interpolated — so a
        reviewer note containing quotes or Cypher syntax cannot alter the query.
        """
        target = patch.get("target_entity") or patch.get("target")
        if not target:
            logger.warning("Entity patch %s has no target entity; skipping", patch.get("feedback_id"))
            return False

        cypher = """
        MATCH (n)
        WHERE n.name = $target OR n.id = $target
        SET n.corrected_by = $approved_by,
            n.correction_date = datetime(),
            n.correction_rationale = $rationale,
            n.correction_feedback_id = $feedback_id
        RETURN count(n) AS updated
        """
        return await self._run_cypher(cypher, {
            "target": str(target),
            "approved_by": patch.get("approved_by", "governance_batch"),
            "rationale": patch.get("rationale", ""),
            "feedback_id": patch.get("feedback_id", ""),
        })

    async def _deploy_property_patch(self, patch: Dict[str, Any]) -> bool:
        """Apply a corrected scalar value to an entity."""
        target = patch.get("target_entity") or patch.get("target")
        if not target:
            logger.warning("Property patch %s has no target entity; skipping", patch.get("feedback_id"))
            return False

        operation = patch.get("operation") or {}
        corrected_value = operation.get("corrected_value")
        if corrected_value is None:
            logger.warning("Property patch %s carries no corrected_value; skipping", patch.get("feedback_id"))
            return False

        cypher = """
        MATCH (n)
        WHERE n.name = $target OR n.id = $target
        SET n.corrected_value = $corrected_value,
            n.corrected_by = $approved_by,
            n.correction_date = datetime(),
            n.correction_rationale = $rationale,
            n.correction_feedback_id = $feedback_id
        RETURN count(n) AS updated
        """
        return await self._run_cypher(cypher, {
            "target": str(target),
            "corrected_value": str(corrected_value),
            "approved_by": patch.get("approved_by", "governance_batch"),
            "rationale": patch.get("rationale", ""),
            "feedback_id": patch.get("feedback_id", ""),
        })

    async def _deploy_relationship_patch(self, patch: Dict[str, Any]) -> bool:
        """Record a supersession / link correction between two nodes.

        Relationship type is validated against an allow-list because Cypher does
        not accept a relationship type as a parameter.
        """
        target = patch.get("target") or {}
        if not isinstance(target, dict):
            logger.warning("Relationship patch %s has no structured target; skipping", patch.get("feedback_id"))
            return False

        source_id = target.get("source")
        dest_id = target.get("target")
        rel_type = (target.get("relationship") or "SUPERSEDES").upper()

        allowed_rels = {"SUPERSEDES", "AMENDS", "REFERENCES", "APPLIES_TO", "RELATED_TO"}
        if rel_type not in allowed_rels:
            logger.warning("Relationship type '%s' not in allow-list; skipping patch %s", rel_type, patch.get("feedback_id"))
            return False

        if not source_id or not dest_id:
            logger.warning("Relationship patch %s missing source/target; skipping", patch.get("feedback_id"))
            return False

        cypher = f"""
        MATCH (source) WHERE source.name = $source_id OR source.id = $source_id
        MATCH (dest) WHERE dest.name = $dest_id OR dest.id = $dest_id
        MERGE (source)-[r:{rel_type}]->(dest)
        SET r.corrected_by = $approved_by,
            r.correction_date = datetime(),
            r.rationale = $rationale,
            r.correction_feedback_id = $feedback_id
        RETURN count(r) AS updated
        """
        return await self._run_cypher(cypher, {
            "source_id": str(source_id),
            "dest_id": str(dest_id),
            "approved_by": patch.get("approved_by", "governance_batch"),
            "rationale": patch.get("rationale", ""),
            "feedback_id": patch.get("feedback_id", ""),
        })


_batch_instance: Optional[GovernanceBatch] = None


def get_governance_batch() -> GovernanceBatch:
    global _batch_instance
    if _batch_instance is None:
        _batch_instance = GovernanceBatch()
    return _batch_instance
