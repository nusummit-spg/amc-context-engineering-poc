# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_review_queue.py
====================
Focused test suite for the Human Review Queue subsystem (Task 0.1.6) plus the
governance-batch consumers added for Task 1.2.

Complements test_phase0_e2e.py, which covers the happy-path lifecycle; this
module targets priority derivation, governance selection, deployment marking,
statistics, and the API contract.
"""
import pytest

from app.db.review_queue_repository import ReviewQueueRepository
from app.evaluation.patch_generator import PatchGenerator
from app.schemas.review_queue import ReviewQueueItem, ReviewReason, ReviewStatus, Verdict
from app.tasks.governance_batch import GovernanceBatch


@pytest.fixture
def repo(tmp_path):
    """Isolated SQLite-backed repository."""
    return ReviewQueueRepository(str(tmp_path / "review_queue_test.db"))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


def _item(**overrides) -> ReviewQueueItem:
    defaults = dict(
        response_id="resp_001",
        query="What is the minimum AUM for an equity fund launch?",
        user_answer="The minimum AUM is Rs. 50 crore.",
        reason=ReviewReason.CONFIDENCE_LOW,
        confidence_score=0.45,
    )
    defaults.update(overrides)
    return ReviewQueueItem(**defaults)


# ── Enqueue & priority derivation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_returns_id_and_persists(repo):
    item = _item()
    item_id = await repo.enqueue(item)
    assert item_id

    fetched = await repo.get_by_id(item_id)
    assert fetched is not None
    assert fetched.query == item.query
    assert fetched.status == ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_hallucination_gets_top_priority(repo):
    """Reason-based priority must actually be applied, not silently skipped."""
    item = _item(reason=ReviewReason.HALLUCINATION_DETECTED, confidence_score=0.8)
    item_id = await repo.enqueue(item)

    fetched = await repo.get_by_id(item_id)
    assert fetched.priority == 1


@pytest.mark.asyncio
async def test_compliance_violation_gets_top_priority(repo):
    item_id = await repo.enqueue(_item(reason=ReviewReason.COMPLIANCE_VIOLATION))
    assert (await repo.get_by_id(item_id)).priority == 1


@pytest.mark.asyncio
async def test_very_low_confidence_raises_priority(repo):
    item_id = await repo.enqueue(_item(confidence_score=0.10))
    assert (await repo.get_by_id(item_id)).priority == 2


@pytest.mark.asyncio
async def test_explicit_priority_is_respected(repo):
    item_id = await repo.enqueue(_item(priority=9), auto_priority=False)
    assert (await repo.get_by_id(item_id)).priority == 9


@pytest.mark.asyncio
async def test_unassigned_ordered_by_priority(repo):
    await repo.enqueue(_item(response_id="low", confidence_score=0.60))
    await repo.enqueue(_item(response_id="urgent", reason=ReviewReason.HALLUCINATION_DETECTED))

    unassigned = await repo.get_unassigned(limit=10)
    assert [i.response_id for i in unassigned][0] == "urgent"


# ── Assignment / resolution ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_moves_item_to_in_review(repo):
    item_id = await repo.enqueue(_item())
    assert await repo.assign_to_user(item_id, "reviewer_1")

    fetched = await repo.get_by_id(item_id)
    assert fetched.assigned_to == "reviewer_1"
    assert fetched.status == ReviewStatus.IN_REVIEW

    assert item_id in [i.id for i in await repo.get_pending_for_user("reviewer_1")]
    assert item_id not in [i.id for i in await repo.get_unassigned()]


@pytest.mark.asyncio
async def test_reject_returns_item_to_unassigned_queue(repo):
    item_id = await repo.enqueue(_item())
    await repo.assign_to_user(item_id, "reviewer_1")
    assert await repo.reject(item_id, "Needs a domain specialist", "reviewer_1")

    fetched = await repo.get_by_id(item_id)
    assert fetched.status == ReviewStatus.PENDING
    assert fetched.assigned_to is None
    assert fetched.rejection_reason == "Needs a domain specialist"
    assert item_id in [i.id for i in await repo.get_unassigned()]


@pytest.mark.asyncio
async def test_approve_records_verdict_and_reviewer(repo):
    item_id = await repo.enqueue(_item())
    assert await repo.approve(item_id, "needs_correction", "AUM figure is wrong", "reviewer_2")

    fetched = await repo.get_by_id(item_id)
    assert fetched.status == ReviewStatus.APPROVED
    assert fetched.verdict == "needs_correction"
    assert fetched.resolved_by == "reviewer_2"
    assert fetched.resolved_at is not None


@pytest.mark.asyncio
async def test_operations_on_missing_item_return_false(repo):
    assert await repo.get_by_id("does-not-exist") is None
    assert await repo.assign_to_user("does-not-exist", "reviewer_1") is False
    assert await repo.approve("does-not-exist", "confirmed", "", "reviewer_1") is False
    assert await repo.reject("does-not-exist", "reason", "reviewer_1") is False


@pytest.mark.asyncio
async def test_lookup_by_response_id(repo):
    await repo.enqueue(_item(response_id="resp_lookup"))
    found = await repo.get_by_response_id("resp_lookup")
    assert found is not None and found.response_id == "resp_lookup"


# ── Statistics ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_counts_by_status_and_reason(repo):
    await repo.enqueue(_item(response_id="a"))
    approved_id = await repo.enqueue(_item(response_id="b", reason=ReviewReason.FACTUAL_ERROR))
    await repo.approve(approved_id, "confirmed", "ok", "reviewer_1")

    stats = await repo.get_stats(time_range_days=7)
    assert stats["total"] == 2
    assert stats["pending"]["count"] == 1
    assert stats["approved"]["count"] == 1
    assert stats["by_reason"][ReviewReason.FACTUAL_ERROR.value] == 1
    assert stats["average_resolution_time_seconds"] >= 0.0


# ── Governance batch selection & marking ─────────────────────────────────────

@pytest.mark.asyncio
async def test_governance_selects_only_approved_corrections(repo):
    correction_id = await repo.enqueue(_item(response_id="needs_fix"))
    await repo.approve(correction_id, "needs_correction", "Value should be 100 crore", "reviewer_1")

    confirmed_id = await repo.enqueue(_item(response_id="fine"))
    await repo.approve(confirmed_id, "confirmed", "Accurate", "reviewer_1")

    await repo.enqueue(_item(response_id="still_pending"))

    candidates = await repo.get_resolved_for_governance(lookback_days=7)
    ids = {c.id for c in candidates}
    assert correction_id in ids
    assert confirmed_id not in ids


@pytest.mark.asyncio
async def test_deployed_items_are_not_reprocessed(repo):
    item_id = await repo.enqueue(_item(response_id="fix_me"))
    await repo.approve(item_id, "needs_correction", "AUM should be 100 crore", "reviewer_1")

    assert len(await repo.get_resolved_for_governance()) == 1

    assert await repo.mark_governance_deployed(item_id, "success", patch_type="property_update")

    assert await repo.get_resolved_for_governance() == []
    meta = (await repo.get_by_id(item_id)).metadata
    assert meta["governance_deployment_status"] == "success"
    assert meta["governance_patch_type"] == "property_update"


@pytest.mark.asyncio
async def test_mark_governance_deployed_records_error(repo):
    item_id = await repo.enqueue(_item())
    await repo.approve(item_id, "needs_correction", "wrong figure", "reviewer_1")
    await repo.mark_governance_deployed(item_id, "failed", patch_type="entity_update", error="Neo4j down")

    meta = (await repo.get_by_id(item_id)).metadata
    assert meta["governance_deployment_status"] == "failed"
    assert meta["governance_deployment_error"] == "Neo4j down"


@pytest.mark.asyncio
async def test_failed_deployment_stays_eligible_for_retry(repo):
    """A transient outage must not permanently consume an approved correction."""
    item_id = await repo.enqueue(_item())
    await repo.approve(item_id, "needs_correction", "wrong figure", "reviewer_1")

    await repo.mark_governance_deployed(item_id, "failed", error="Neo4j down")
    assert [i.id for i in await repo.get_resolved_for_governance()] == [item_id]
    assert (await repo.get_by_id(item_id)).metadata["governance_attempts"] == 1


@pytest.mark.asyncio
async def test_repeated_failures_eventually_retire_the_item(repo):
    from app.db.review_queue_repository import MAX_GOVERNANCE_ATTEMPTS

    item_id = await repo.enqueue(_item())
    await repo.approve(item_id, "needs_correction", "wrong figure", "reviewer_1")

    for _ in range(MAX_GOVERNANCE_ATTEMPTS):
        await repo.mark_governance_deployed(item_id, "failed", error="Neo4j down")

    assert await repo.get_resolved_for_governance() == []
    meta = (await repo.get_by_id(item_id)).metadata
    assert meta["governance_attempts"] == MAX_GOVERNANCE_ATTEMPTS
    assert "governance_deployed_at" in meta


class _FakeGraphStore:
    """Records the Cypher and parameters a patch deployment would send."""

    def __init__(self):
        self.calls = []

    async def run(self, cypher, **params):
        self.calls.append((cypher, params))
        return []


@pytest.mark.asyncio
async def test_governance_batch_deploys_property_patch(repo):
    item_id = await repo.enqueue(_item(
        response_id="resp_numeric",
        query="What is the minimum AUM for Kotak Equity Fund?",
        user_answer="The minimum AUM is Rs. 10 crore.",
    ))
    await repo.approve(item_id, "needs_correction", "The AUM value should be 50 crore.", "reviewer_1")

    graph = _FakeGraphStore()
    batch = GovernanceBatch(review_repo=repo, graph_store=graph, patch_generator=PatchGenerator())
    report = await batch.process(lookback_days=7)

    assert report["considered"] == 1
    assert report["deployed"] == 1
    assert report["failed"] == 0
    assert len(graph.calls) == 1

    cypher, params = graph.calls[0]
    # Reviewer-supplied text must travel as a parameter, never interpolated.
    assert "$corrected_value" in cypher
    assert "50 crore" in params["corrected_value"]

    # And the item must not be picked up by the next batch.
    assert await repo.get_resolved_for_governance() == []


@pytest.mark.asyncio
async def test_governance_batch_parks_ambiguous_verdicts(repo):
    item_id = await repo.enqueue(_item(response_id="resp_ambiguous"))
    await repo.approve(item_id, Verdict.AMBIGUOUS.value, "Unclear which circular applies", "reviewer_1")

    graph = _FakeGraphStore()
    batch = GovernanceBatch(review_repo=repo, graph_store=graph)
    report = await batch.process()

    # Ambiguous work is human-only: nothing should reach the graph.
    assert report["deployed"] == 0
    assert graph.calls == []


@pytest.mark.asyncio
async def test_governance_batch_defers_when_graph_is_unavailable(repo):
    """With no graph store, the batch must defer rather than fail every item."""
    item_id = await repo.enqueue(_item())
    await repo.approve(item_id, "needs_correction", "The AUM value should be 50 crore.", "reviewer_1")

    batch = GovernanceBatch(review_repo=repo, graph_store=None)
    # Force the lazy container lookup to resolve to nothing.
    batch._graph_store = None
    report = await batch.process()

    assert report.get("deferred") == 1
    assert report["deployed"] == 0
    assert report["failed"] == 0
    # Item must still be queued for the next run, with no attempt burned.
    assert [i.id for i in await repo.get_resolved_for_governance()] == [item_id]
    assert "governance_attempts" not in ((await repo.get_by_id(item_id)).metadata or {})


@pytest.mark.asyncio
async def test_governance_batch_empty_queue_is_a_no_op(repo):
    batch = GovernanceBatch(review_repo=repo, graph_store=_FakeGraphStore())
    report = await batch.process()
    assert report["considered"] == 0
    assert report["deployed"] == 0
    assert report["errors"] == []


@pytest.mark.asyncio
async def test_governance_batch_records_deployment_failure(repo):
    item_id = await repo.enqueue(_item(query="Kotak AUM limit", user_answer="Rs. 10 crore"))
    await repo.approve(item_id, "needs_correction", "The AUM value should be 50 crore.", "reviewer_1")

    class _BrokenGraph:
        async def run(self, cypher, **params):
            raise RuntimeError("Neo4j unavailable")

    batch = GovernanceBatch(review_repo=repo, graph_store=_BrokenGraph())
    report = await batch.process()

    assert report["failed"] == 1
    assert report["deployed"] == 0
    assert report["errors"]
    meta = (await repo.get_by_id(item_id)).metadata
    assert meta["governance_deployment_status"] == "failed"


# ── API authorization (Task 0.1.3) ───────────────────────────────────────────

_ESCALATE_BODY = {
    "response_id": "resp_rbac",
    "query": "Is capital guaranteed in equity funds?",
    "user_answer": "Yes, equity funds guarantee 12% returns.",
    "reason": "compliance_violation",
    "confidence_score": 0.15,
}


def test_viewer_cannot_escalate(client):
    resp = client.post(
        "/api/review-queue/escalate",
        json=_ESCALATE_BODY,
        headers={"X-User-Role": "viewer", "X-User-ID": "viewer_1"},
    )
    assert resp.status_code == 403


def test_reviewer_can_escalate(client):
    resp = client.post(
        "/api/review-queue/escalate",
        json=_ESCALATE_BODY,
        headers={"X-User-Role": "reviewer", "X-User-ID": "reviewer_1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_reviewer_cannot_read_queue_wide_endpoints(client):
    """Queue-wide visibility and assignment are management-only."""
    headers = {"X-User-Role": "reviewer", "X-User-ID": "reviewer_1"}
    assert client.get("/api/review-queue/stats", headers=headers).status_code == 403
    assert client.get("/api/review-queue/unassigned", headers=headers).status_code == 403
    assert client.post(
        "/api/review-queue/some-id/assign",
        json={"user_id": "reviewer_2"},
        headers=headers,
    ).status_code == 403


def test_compliance_officer_can_manage_queue(client):
    headers = {"X-User-Role": "compliance_officer", "X-User-ID": "officer_1"}
    assert client.get("/api/review-queue/stats", headers=headers).status_code == 200
    assert client.get("/api/review-queue/unassigned", headers=headers).status_code == 200


def test_review_queue_endpoints_expose_no_db_parameter(client):
    """Regression: the repo dependency used to leak a `db` query parameter."""
    spec = client.get("/openapi.json").json()
    for path, ops in spec["paths"].items():
        if "review-queue" not in path:
            continue
        for op in ops.values():
            names = [p["name"] for p in op.get("parameters", [])]
            assert "db" not in names, f"{path} still exposes a 'db' parameter"
