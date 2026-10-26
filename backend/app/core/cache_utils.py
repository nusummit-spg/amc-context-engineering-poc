# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
# ===========================================================================

"""Utility functions for generating secure, user-scoped cache keys and invalidation."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional


def generate_cache_key(
    namespace: str,
    key_components: Dict[str, Any],
    user_id: str,
    tenant_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Generate a cache key that includes user and tenant isolation.

    Format: {namespace}:tenant:{tenant_id}:user:{user_id}:session:{session_id}:hash:{hash}

    Args:
        namespace: Cache namespace (e.g., "intent", "cypher", "entity_resolve")
        key_components: Dict of values that define cache uniqueness
        user_id: Authenticated user identifier (MANDATORY)
        tenant_id: Tenant identifier for multi-tenant isolation
        session_id: Optional session scope

    Returns:
        str: Fully qualified cache key with user/tenant isolation

    Raises:
        ValueError: If user_id is empty or missing.
    """
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id is mandatory for cache key generation")

    # Sort and serialize key components for consistent hashing
    sorted_items = sorted((str(k), str(v)) for k, v in key_components.items())
    component_str = "|".join(f"{k}:{v}" for k, v in sorted_items)

    # Hash the components to keep key length manageable
    component_hash = hashlib.sha256(component_str.encode("utf-8")).hexdigest()[:16]

    # Build hierarchical key
    parts = [str(namespace).strip()]

    if tenant_id and str(tenant_id).strip():
        parts.extend(["tenant", str(tenant_id).strip()])

    parts.extend(["user", str(user_id).strip()])

    if session_id and str(session_id).strip():
        parts.extend(["session", str(session_id).strip()])

    parts.extend(["hash", component_hash])

    return ":".join(parts)


def invalidate_user_cache(
    client_or_store: Any,
    namespace: str,
    user_id: str,
    tenant_id: Optional[str] = None,
) -> int:
    """Invalidate all cache entries for a specific user.

    Supports both in-memory dict stores and Redis-like clients.

    Returns:
        int: Number of keys deleted

    Args:
        client_or_store (Any): The client or store.
        namespace (str): The namespace.
        user_id (str): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.
    """
    if not user_id or not str(user_id).strip():
        return 0

    clean_user = str(user_id).strip()
    clean_tenant = str(tenant_id).strip() if tenant_id else None

    # Case 1: In-memory dictionary
    if isinstance(client_or_store, dict):
        keys_to_remove = []
        for key in list(client_or_store.keys()):
            key_str = str(key)
            if not key_str.startswith(f"{namespace}:"):
                continue
            if clean_tenant and f":tenant:{clean_tenant}:" not in key_str:
                continue
            if f":user:{clean_user}:" in key_str:
                keys_to_remove.append(key)

        for k in keys_to_remove:
            client_or_store.pop(k, None)
        return len(keys_to_remove)

    # Case 2: Redis-compatible client
    if hasattr(client_or_store, "keys") and hasattr(client_or_store, "delete"):
        pattern_parts = [namespace]
        if clean_tenant:
            pattern_parts.extend(["tenant", clean_tenant])
        pattern_parts.extend(["user", clean_user, "*"])
        pattern = ":".join(pattern_parts)

        try:
            matched_keys = client_or_store.keys(pattern)
            if matched_keys:
                return client_or_store.delete(*matched_keys)
        except Exception:
            return 0

    return 0
