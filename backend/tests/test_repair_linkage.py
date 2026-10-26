# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_repair_linkage.py
======================
Unit and integration tests for Phase 3: Repair Engine Linkage & Duplicate Task Prevention.
Validates:
1. When an issue transitions to in_repair, exactly one repair task is created.
2. If an issue already has a repair_task_id, subsequent repair calls reuse the task (no duplicates).
3. Subsequent matching feedbacks attach to the existing issue without generating new repair tasks.
4. Issue resolution preserves repair_task_id for audit.
5. Issue reopen clears repair_task_id to allow fresh triage determination.
6. Subsequent triage of reopened issue to in_repair creates a fresh repair task.
7. REST API endpoints:
   - POST /api/feedback/issues/{issue_id}/repair
   - POST /api/feedback/issues/{issue_id}/status
   - GET /api/feedback/issues/{issue_id}
   - GET /api/feedback/issues
"""

import hashlib
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.feedback.issue_matcher import get_issue_matcher, reset_issue_matcher
from app.feedback.repair_linkage import get_repair_linkage_service
from app.main import create_app
from app.schemas.feedback_issues_table import FeedbackIssue, IssueStatus
from app.schemas.response_feedback_table import ResponseFeedback


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_database():
    session = SessionLocal()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()
    yield
    session = SessionLocal()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()


def test_single_repair_task_creation():
    """Verify exactly one repair task is generated when transitioning to in_repair."""
    db = SessionLocal()
    try:
        linkage = get_repair_linkage_service()
        issue = FeedbackIssue(
            issue_id="iss_test_01",
            canonical_query_text="What is the TER of Axis Bluechip Fund?",
            query_hash=hashlib.md5("what is the ter of axis bluechip fund?".encode("utf-8")).hexdigest(),
            status=IssueStatus.REPORTED.value,
            primary_entities=["Axis Bluechip Fund"],
            taxonomy_paths=["Fund Facts/TER"],
            contributor_count=1,
        )
        db.add(issue)
        db.commit()

        # Transition to in_repair
        res = linkage.get_or_create_repair_task(db, "iss_test_01", actor_id="triage_user_1")
        assert res["task_created"] is True
        assert res["reused"] is False
        assert res["repair_task_id"] is not None
        assert res["status"] == "in_repair"

        # Check DB
        db.refresh(issue)
        assert issue.status == "in_repair"
        assert issue.repair_task_id == res["repair_task_id"]
    finally:
        db.close()


def test_repair_task_idempotency_prevents_duplicate():
    """Verify calling repair initiation on an issue that already has a repair task reuses it."""
    db = SessionLocal()
    try:
        linkage = get_repair_linkage_service()
        issue = FeedbackIssue(
            issue_id="iss_test_02",
            canonical_query_text="What is the exit load of HDFC Top 100?",
            query_hash=hashlib.md5("what is the exit load of hdfc top 100?".encode("utf-8")).hexdigest(),
            status=IssueStatus.IN_REPAIR.value,
            repair_task_id="task_existing_999",
            contributor_count=1,
        )
        db.add(issue)
        db.commit()

        # Second call to get_or_create_repair_task
        res = linkage.get_or_create_repair_task(db, "iss_test_02", actor_id="triage_user_2")
        assert res["task_created"] is False
        assert res["reused"] is True
        assert res["repair_task_id"] == "task_existing_999"

        # Check DB didn't change repair_task_id
        db.refresh(issue)
        assert issue.repair_task_id == "task_existing_999"
    finally:
        db.close()


def test_subsequent_feedbacks_do_not_create_duplicate_repair_tasks(client: TestClient):
    """
    Verify Alice's feedback -> issue in_repair (stamped with repair_task_id).
    Subsequent Bob & Carol feedbacks attach to the same issue, incrementing contributors,
    without changing or duplicating the repair_task_id.
    """
    db = SessionLocal()
    query_text = "What is the NAV of Nippon India Small Cap Fund?"
    try:
        # Step 1: Alice submits feedback
        alice_resp = client.post(
            "/api/feedback",
            json={
                "response_id": "resp_alice_nav",
                "interaction_id": "int_alice",
                "session_id": "sess_alice",
                "turn_number": 1,
                "query_text": query_text,
                "actor_id": "alice_analyst",
                "selected_categories": ["F01"],
                "feedback_text": "NAV value is outdated",
            },
        )
        assert alice_resp.status_code == 201
        alice_data = alice_resp.json()
        issue_id = alice_data["issue_id"]
        assert issue_id is not None

        # Step 2: Issue is triaged and transitions to in_repair
        linkage = get_repair_linkage_service()
        repair_res = linkage.get_or_create_repair_task(db, issue_id, actor_id="triage_officer")
        assert repair_res["task_created"] is True
        original_repair_task_id = repair_res["repair_task_id"]

        # Step 3: Bob submits feedback on the same query
        bob_resp = client.post(
            "/api/feedback",
            json={
                "response_id": "resp_bob_nav",
                "interaction_id": "int_bob",
                "session_id": "sess_bob",
                "turn_number": 1,
                "query_text": query_text,
                "actor_id": "bob_reviewer",
                "selected_categories": ["F01"],
                "feedback_text": "I noticed the wrong NAV too",
            },
        )
        assert bob_resp.status_code == 201
        bob_data = bob_resp.json()
        assert bob_data["issue_id"] == issue_id
        assert bob_data["was_matched_to_existing_issue"] is True

        # Step 4: Carol submits feedback on the same query
        carol_resp = client.post(
            "/api/feedback",
            json={
                "response_id": "resp_carol_nav",
                "interaction_id": "int_carol",
                "session_id": "sess_carol",
                "turn_number": 1,
                "query_text": query_text,
                "actor_id": "carol_auditor",
                "selected_categories": ["F02"],
                "feedback_text": "Confirming NAV issue",
            },
        )
        assert carol_resp.status_code == 201
        carol_data = carol_resp.json()
        assert carol_data["issue_id"] == issue_id
        assert carol_data["was_matched_to_existing_issue"] is True

        # Step 5: Verify the issue still has original repair_task_id and contributor_count == 3
        db.expire_all()
        issue = db.query(FeedbackIssue).filter(FeedbackIssue.issue_id == issue_id).first()
        assert issue.repair_task_id == original_repair_task_id
        assert issue.contributor_count == 3
        assert issue.status == "in_repair"
    finally:
        db.close()


def test_issue_resolution_and_reopen_lifecycle(client: TestClient):
    """
    Verify lifecycle transitions:
    - in_repair issue is resolved -> repair_task_id preserved for audit trail.
    - New matching feedback reopens the issue -> repair_task_id cleared to None (Section 9).
    - Fresh triage to in_repair creates a NEW repair task ID.
    """
    db = SessionLocal()
    query_text = "What is the fund manager of SBI Bluechip Fund?"
    try:
        linkage = get_repair_linkage_service()
        issue = FeedbackIssue(
            issue_id="iss_sbi_fm",
            canonical_query_text=query_text,
            query_hash=hashlib.md5(query_text.lower().strip().encode("utf-8")).hexdigest(),
            status=IssueStatus.REPORTED.value,
            primary_entities=["SBI Bluechip Fund"],
            contributor_count=1,
        )
        db.add(issue)
        db.commit()

        # 1. Put in repair
        rep_1 = linkage.get_or_create_repair_task(db, "iss_sbi_fm")
        first_task_id = rep_1["repair_task_id"]
        assert first_task_id is not None

        # 2. Resolve issue
        res_transition = linkage.transition_issue_status(
            db=db,
            issue_id="iss_sbi_fm",
            new_status="resolved",
            resolution_notes="Updated factsheet metadata and corrected manager to Saurabh Pant",
        )
        assert res_transition["status"] == "resolved"
        db.refresh(issue)
        assert issue.status == "resolved"
        assert issue.repair_task_id == first_task_id  # preserved for audit

        # 3. New feedback arrives -> automatically reopens issue and clears repair_task_id
        new_fb = client.post(
            "/api/feedback",
            json={
                "response_id": "resp_sbi_after_resolve",
                "interaction_id": "int_late",
                "session_id": "sess_late",
                "turn_number": 1,
                "query_text": query_text,
                "actor_id": "late_user",
                "selected_categories": ["F04"],
                "feedback_text": "Still shows old manager in one section",
            },
        )
        assert new_fb.status_code == 201
        db.refresh(issue)
        assert issue.status == "reopened"
        assert issue.repair_task_id is None  # Section 9 requirement: cleared on reopen!

        # 4. Next triage cycle puts reopened issue back to in_repair -> creates fresh repair task!
        rep_2 = linkage.get_or_create_repair_task(db, "iss_sbi_fm", actor_id="senior_triage")
        assert rep_2["task_created"] is True
        second_task_id = rep_2["repair_task_id"]
        assert second_task_id is not None
        assert second_task_id != first_task_id  # Brand new task created!
    finally:
        db.close()


def test_api_endpoints_repair_linkage(client: TestClient):
    """Test REST API endpoints for issue repair and lifecycle management."""
    db = SessionLocal()
    try:
        issue = FeedbackIssue(
            issue_id="iss_api_test_01",
            canonical_query_text="What are the top holdings of Parag Parikh Flexi Cap?",
            query_hash=hashlib.md5("what are the top holdings of parag parikh flexi cap?".encode("utf-8")).hexdigest(),
            status=IssueStatus.REPORTED.value,
            primary_entities=["Parag Parikh Flexi Cap Fund"],
            contributor_count=1,
        )
        db.add(issue)
        db.commit()

        # 1. GET /api/feedback/issues/{issue_id}
        get_res = client.get("/api/feedback/issues/iss_api_test_01")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["issue_id"] == "iss_api_test_01"
        assert get_data["status"] == "reported"
        assert get_data["repair_task_id"] is None

        # 2. POST /api/feedback/issues/{issue_id}/repair
        repair_res = client.post(
            "/api/feedback/issues/iss_api_test_01/repair",
            json={"actor_id": "lead_compliance", "metadata": {"priority": "P1"}},
        )
        assert repair_res.status_code == 200
        repair_data = repair_res.json()
        assert repair_data["task_created"] is True
        assert repair_data["reused"] is False
        assert repair_data["repair_task_id"] is not None
        assert repair_data["status"] == "in_repair"

        # 3. Repeat POST /repair -> Idempotent reuse
        repeat_repair = client.post(
            "/api/feedback/issues/iss_api_test_01/repair",
            json={"actor_id": "another_user"},
        )
        assert repeat_repair.status_code == 200
        repeat_data = repeat_repair.json()
        assert repeat_data["task_created"] is False
        assert repeat_data["reused"] is True
        assert repeat_data["repair_task_id"] == repair_data["repair_task_id"]

        # 4. POST /api/feedback/issues/{issue_id}/status -> resolve
        status_res = client.post(
            "/api/feedback/issues/iss_api_test_01/status",
            json={
                "status": "resolved",
                "resolution_notes": "Holding weights updated to latest portfolio disclosure.",
                "actor_id": "admin_user",
            },
        )
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] == "resolved"

        # 5. GET /api/feedback/issues with status filter
        list_res = client.get("/api/feedback/issues?status=resolved")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["total"] >= 1
        assert any(item["issue_id"] == "iss_api_test_01" for item in list_data["items"])

        # 6. Test 404 on nonexistent issue
        not_found = client.post("/api/feedback/issues/iss_nonexistent/repair")
        assert not_found.status_code == 404
    finally:
        db.close()
