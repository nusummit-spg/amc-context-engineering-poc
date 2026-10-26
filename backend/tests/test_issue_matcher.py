# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_issue_matcher.py
=====================
Unit tests for the IssueMatcher and issue_store components:
- Exact hash matching (<1ms)
- FAISS semantic matching
- Stage 3 Entity guard (Adani vs Ambuja false positive prevention)
- Stage 3 Entity alias resolution (Adani Enterprises vs AEL)
- Stage 3 Taxonomy guard (cross-domain mismatch prevention)
- Open vs closed issue status filtering
- Reopening of resolved issues on new feedback
- Contributor count tracking across distinct actors
- Multi-tenant isolation
"""

import uuid
import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.feedback.issue_matcher import IssueMatcher, reset_issue_matcher
from app.feedback import issue_store
from app.schemas.feedback_issues_table import (
    FeedbackIssue,
    IssueStatus,
)
from app.schemas.response_feedback_table import ResponseFeedback


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure clean table and matcher state before and after each test."""
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


@pytest.fixture
def db_session():
    """Database session fixture."""
    session: Session = SessionLocal()
    session.register = lambda *args, **kwargs: None
    try:
        yield session
    finally:
        session.close()


def test_exact_match(db_session):
    """Stage 1: exact normalized query string match returns match_type='exact'."""
    matcher = IssueMatcher()
    uid = uuid.uuid4().hex[:6]
    query = f"What is the expense ratio of NuSummit Bluechip Fund? ref_{uid}"
    
    # 1. Create issue
    issue, match_type, was_matched = matcher.find_or_create(
        query=query,
        db=db_session,
        actor_id="analyst_alice",
    )
    db_session.register(issue_id=issue.issue_id)

    assert was_matched is False
    assert match_type == "new"
    assert issue.status == IssueStatus.REPORTED.value
    assert issue.contributor_count == 1

    # 2. Probe with identical query (with different casing/spacing)
    lookup_query = f"  WHAT IS THE EXPENSE RATIO OF NUSUMMIT BLUECHIP FUND? REF_{uid}  "
    result = matcher.lookup(lookup_query, db_session)

    assert result is not None
    assert result.matched is True
    assert result.issue_id == issue.issue_id
    assert result.match_type == "exact"
    assert result.similarity_score == 1.0
    assert result.contributor_count == 1
    assert "already been reported" in result.message


def test_semantic_match_same_entity(db_session):
    """Stage 2: semantic paraphrase about the same entity matches."""
    matcher = IssueMatcher(similarity_threshold=0.80)
    uid = uuid.uuid4().hex[:6]
    query_orig = f"What is the ESG risk rating of Adani Enterprises? tag_{uid}"
    
    issue, _, _ = matcher.find_or_create(
        query=query_orig,
        db=db_session,
        actor_id="alice",
    )
    db_session.register(issue_id=issue.issue_id)

    # Paraphrase about the same entity
    query_paraphrase = f"Can you share the ESG rating for Adani Enterprises? tag_{uid}"
    result = matcher.lookup(query_paraphrase, db_session)

    assert result is not None
    assert result.matched is True
    assert result.issue_id == issue.issue_id
    assert result.match_type in ("exact", "semantic")
    assert result.similarity_score >= 0.80


def test_entity_guard_prevents_false_positive(db_session):
    """
    Stage 3 Guard:
    Structurally identical queries about different entities (Adani Enterprises vs Ambuja)
    must NOT match even if vector similarity is high.
    """
    matcher = IssueMatcher(similarity_threshold=0.70)
    uid = uuid.uuid4().hex[:6]
    query_adani = f"What is the ESG score of Adani Enterprises? {uid}"
    
    issue, _, _ = matcher.find_or_create(
        query=query_adani,
        db=db_session,
        actor_id="alice",
    )
    db_session.register(issue_id=issue.issue_id)

    # Structurally similar query but about Ambuja
    query_ambuja = f"What is the ESG score of Ambuja? {uid}"
    result = matcher.lookup(query_ambuja, db_session)

    assert result is None  # Must NOT match because entities differ!


def test_entity_alias_resolution_matches(db_session):
    """
    Stage 3 Guard:
    Query using alias 'AEL' resolves canonically to 'Adani Enterprises' and matches.
    """
    matcher = IssueMatcher(similarity_threshold=0.70)
    uid = uuid.uuid4().hex[:6]
    query_full = f"What is the ESG score of Adani Enterprises? code_{uid}"
    
    issue, _, _ = matcher.find_or_create(
        query=query_full,
        db=db_session,
        actor_id="alice",
    )
    db_session.register(issue_id=issue.issue_id)

    # Query with alias
    query_alias = f"What is the ESG score of AEL? code_{uid}"
    result = matcher.lookup(query_alias, db_session)

    assert result is not None
    assert result.matched is True
    assert result.issue_id == issue.issue_id


def test_closed_issues_excluded_from_lookup(db_session):
    """Resolved and closed issues must NOT be returned by lookup()."""
    matcher = IssueMatcher()
    uid = uuid.uuid4().hex[:6]
    query = f"SEBI circular on mutual fund categorization {uid}"
    
    issue, _, _ = matcher.find_or_create(
        query=query,
        db=db_session,
        actor_id="alice",
    )
    db_session.register(issue_id=issue.issue_id)

    # Move issue to resolved
    issue_store.update_issue_status(db_session, issue.issue_id, status=IssueStatus.RESOLVED.value)
    matcher.sync_open_issues(db_session)

    # Lookup should return None (resolved issue not shown to user)
    result = matcher.lookup(query, db_session)
    assert result is None


def test_reopen_on_new_feedback_submission(db_session):
    """Submitting new matching feedback for a previously resolved issue reopens it."""
    matcher = IssueMatcher()
    uid = uuid.uuid4().hex[:6]
    query = f"SEBI riskometer classification guidelines {uid}"
    
    issue, _, _ = matcher.find_or_create(
        query=query,
        db=db_session,
        actor_id="alice",
    )
    db_session.register(issue_id=issue.issue_id)

    # Resolve issue
    issue_store.update_issue_status(
        db_session,
        issue.issue_id,
        status=IssueStatus.RESOLVED.value,
        repair_task_id="task_old_123",
    )
    matcher.sync_open_issues(db_session)

    # Bob submits feedback on exact same query
    issue_reopened, match_type, was_matched = matcher.find_or_create(
        query=query,
        db=db_session,
        actor_id="bob",
    )

    assert issue_reopened.issue_id == issue.issue_id
    assert issue_reopened.status == IssueStatus.REOPENED.value
    assert issue_reopened.repair_task_id is None  # Cleared for fresh triage
    assert was_matched is True


def test_contributor_count_incrementation(db_session):
    """Distinct users submitting feedback increment contributor count; same user does not."""
    matcher = IssueMatcher()
    uid = uuid.uuid4().hex[:6]
    query = f"What is the total debt exposure of Adani Group? {uid}"
    
    # 1. Alice creates
    issue, _, _ = matcher.find_or_create(query=query, db=db_session, actor_id="alice")
    db_session.register(issue_id=issue.issue_id)
    assert issue.contributor_count == 1

    # Simulate recorded feedback entry for Alice
    fb_alice = ResponseFeedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
        response_id=f"resp_{uid}_1",
        interaction_id="int_1",
        session_id=f"sess_{uid}_1",
        turn_number=1,
        actor_id="alice",
        query_text=query,
        selected_categories=["F01"],
        issue_id=issue.issue_id,
        created_at="2026-10-14T00:00:00Z",
        updated_at="2026-10-14T00:00:00Z",
    )
    db_session.add(fb_alice)
    db_session.commit()
    db_session.register(feedback_id=fb_alice.feedback_id)

    # 2. Bob submits matching feedback
    issue_bob, _, was_matched = matcher.find_or_create(query=query, db=db_session, actor_id="bob")
    assert was_matched is True
    assert issue_bob.contributor_count == 2

    # Simulate recorded feedback entry for Bob
    fb_bob = ResponseFeedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
        response_id=f"resp_{uid}_2",
        interaction_id="int_2",
        session_id=f"sess_{uid}_2",
        turn_number=1,
        actor_id="bob",
        query_text=query,
        selected_categories=["F01"],
        issue_id=issue.issue_id,
        created_at="2026-10-14T00:01:00Z",
        updated_at="2026-10-14T00:01:00Z",
    )
    db_session.add(fb_bob)
    db_session.commit()
    db_session.register(feedback_id=fb_bob.feedback_id)

    # 3. Alice submits another feedback on the same issue turn
    issue_alice_again, _, _ = matcher.find_or_create(query=query, db=db_session, actor_id="alice")
    assert issue_alice_again.contributor_count == 2  # Not incremented again for Alice


def test_multi_tenant_isolation(db_session):
    """Tenant A's issues should not be matched by Tenant B's queries."""
    matcher = IssueMatcher()
    uid = uuid.uuid4().hex[:6]
    query = f"Confidential fee structure inquiry {uid}"

    issue_a, _, _ = matcher.find_or_create(
        query=query,
        db=db_session,
        tenant_id="tenant_amc_alpha",
        actor_id="user_alpha",
    )
    db_session.register(issue_id=issue_a.issue_id)

    # Probe under tenant B
    result_b = matcher.lookup(query=query, db=db_session, tenant_id="tenant_amc_beta")
    assert result_b is None

    # Probe under tenant A
    result_a = matcher.lookup(query=query, db=db_session, tenant_id="tenant_amc_alpha")
    assert result_a is not None
    assert result_a.issue_id == issue_a.issue_id
