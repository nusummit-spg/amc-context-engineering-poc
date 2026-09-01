# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_security_hardening.py
==========================
Tests sliding window rate limiting, RBAC role enforcement, and encryption.
"""
import pytest
from app.compliance.security import InMemoryRateLimiter, ComplianceDataEncryptor, get_client_role
from app.schemas.compliance_models import Role
from fastapi import HTTPException


def test_rate_limiter_sliding_window():
    limiter = InMemoryRateLimiter()
    client = "192.168.1.100"

    # Allow 3 requests
    assert limiter.is_allowed(client, max_requests=3, window_seconds=10) is True
    assert limiter.is_allowed(client, max_requests=3, window_seconds=10) is True
    assert limiter.is_allowed(client, max_requests=3, window_seconds=10) is True

    # 4th request in window should be blocked
    assert limiter.is_allowed(client, max_requests=3, window_seconds=10) is False

    # Different client should still be allowed
    assert limiter.is_allowed("192.168.1.101", max_requests=3, window_seconds=10) is True


def test_evidence_encryption_decryption():
    encryptor = ComplianceDataEncryptor(secret_key="test_secret_key_123")
    plain = "Confidential Holdings Report: Reliance 18.2% Allocation"

    encrypted = encryptor.encrypt_evidence(plain)
    assert encrypted != plain
    assert len(encrypted) > 10

    decrypted = encryptor.decrypt_evidence(encrypted)
    assert decrypted == plain


def test_rbac_role_parsing():
    assert get_client_role("admin") == Role.ADMIN
    assert get_client_role("resolver") == Role.RESOLVER
    assert get_client_role("reviewer") == Role.REVIEWER
    assert get_client_role("viewer") == Role.VIEWER

    with pytest.raises(HTTPException):
        get_client_role("unauthorized_hacker")
