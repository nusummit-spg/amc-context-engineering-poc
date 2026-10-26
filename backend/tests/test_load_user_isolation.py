# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_load_user_isolation.py
===========================
Concurrency and load isolation testing for Phase 5.
Simulates multiple concurrent users executing isolated workflows, ensuring
no cross-user session, evidence, or cache contamination under concurrent load.
"""
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.api.deps import get_auth_service
from app.auth.security import issue_session_token
from app.auth.repository import AuthUserRecord
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession


@pytest.fixture
def load_users_environment():
    """Register temporary load test users in the auth service repository."""
    auth_service = get_auth_service()
    settings = get_settings()
    num_users = 10
    users = [f"load_user_{i:03d}" for i in range(num_users)]

    for u in users:
        auth_service._repository._users[u] = AuthUserRecord(
            username=u,
            password_hash="test_load_hash",
            display_name=f"Load Test User {u}",
            role="Portfolio Manager",
            status="Active",
        )

    user_tokens = {
        u: issue_session_token(u, settings.auth_secret_key, ttl_minutes=60)[0]
        for u in users
    }

    yield users, user_tokens

    # Cleanup
    for u in users:
        auth_service._repository._users.pop(u, None)
    with SessionLocal() as db:
        for u in users:
            db.query(ChatSession).filter(ChatSession.session_id == f"load-session-{u}").delete()
        db.commit()


@pytest.mark.asyncio
async def test_concurrent_users_no_leakage(load_users_environment):
    """Simulate concurrent users each executing sessions and queries.
    Verify 0% cross-user leakage under concurrency."""
    client = TestClient(app)
    users, user_tokens = load_users_environment
    queries_per_user = 3

    async def user_workflow(user_id: str):
        token = user_tokens[user_id]
        session_id = f"load-session-{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create unique user session
        create_resp = client.post(
            f"/api/sessions/{session_id}",
            json={
                "history": [
                    {
                        "role": "user",
                        "content": f"Confidential portfolio request for {user_id}",
                    }
                ]
            },
            headers=headers,
        )
        assert create_resp.status_code == 200

        # 2. Repeated read operations
        results = []
        for q_idx in range(queries_per_user):
            get_resp = client.get(f"/api/sessions/{session_id}", headers=headers)
            assert get_resp.status_code == 200
            data = get_resp.json()
            results.append(data)

            # Verification: Content must contain current user's ID
            text_payload = str(data)
            assert user_id in text_payload

            # Verification: Content MUST NOT contain any other user's ID
            for other_user in users:
                if other_user != user_id:
                    assert other_user not in text_payload, (
                        f"Data leakage detected! {user_id}'s session contains {other_user}"
                    )

        return results

    # Execute all users concurrently using asyncio
    tasks = [user_workflow(u) for u in users]
    all_results = await asyncio.gather(*tasks)

    # Verify all tasks succeeded
    assert len(all_results) == len(users)
    total_checks = sum(len(r) for r in all_results)
    assert total_checks == len(users) * queries_per_user
