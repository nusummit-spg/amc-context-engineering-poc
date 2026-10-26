"""
Cache adapter implementations (Memory & Redis).
"""
import fnmatch
import json
import logging
from typing import Any, Dict, List, Optional
from .base import CacheAdapter

logger = logging.getLogger("amc_repair.cache")


class MemoryCacheAdapter(CacheAdapter):
    def __init__(self):
        """Initialize a new instance of MemoryCacheAdapter.
        """
        self._store: Dict[str, Dict[str, Any]] = {}

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve operation.

        Args:
            key (str): The key.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        return self._store.get(key)

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Set operation.

        Args:
            key (str): The key.
            value (Dict[str, Any]): The value.
            ttl_seconds (Optional[int]): Collection or list of ttl seconds.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        self._store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        """Delete operation.

        Args:
            key (str): The key.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Retrieve keys by pattern.

        Args:
            pattern (str): The pattern.

        Returns:
            List[str]: List of resulting items or records.
        """
        return [k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)]

    async def close(self):
        """Close operation.
        """
        self._store.clear()


# Alias for compatibility with Task 2.2
MemoryAdapter = MemoryCacheAdapter


class RedisAdapter(CacheAdapter):
    """Redis-backed cache adapter with in-memory fallback if Redis is unavailable."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, **kwargs):
        """Initialize a new instance of RedisAdapter.

        Args:
            host (str): The host.
            port (int): The port.
            db (int): Database session instance.
        """
        self.host = host
        self.port = port
        self.db = db
        self._fallback = MemoryCacheAdapter()
        self._client = None
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.Redis(host=host, port=port, db=db, decode_responses=True, **kwargs)
        except Exception as exc:
            logger.warning("Redis client initialization failed (%s); using in-memory fallback", exc)
            self._client = None

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve operation.

        Args:
            key (str): The key.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        if self._client:
            try:
                val = await self._client.get(key)
                if val:
                    return json.loads(val)
                return None
            except Exception as exc:
                logger.debug("Redis get error (%s), using fallback", exc)
        return await self._fallback.get(key)

    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Set operation.

        Args:
            key (str): The key.
            value (Dict[str, Any]): The value.
            ttl_seconds (Optional[int]): Collection or list of ttl seconds.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        serialized = json.dumps(value)
        if self._client:
            try:
                if ttl_seconds:
                    await self._client.setex(key, ttl_seconds, serialized)
                else:
                    await self._client.set(key, serialized)
                # Keep fallback in sync
                await self._fallback.set(key, value, ttl_seconds)
                return True
            except Exception as exc:
                logger.debug("Redis set error (%s), using fallback", exc)
        return await self._fallback.set(key, value, ttl_seconds)

    async def delete(self, key: str) -> bool:
        """Delete operation.

        Args:
            key (str): The key.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if self._client:
            try:
                res = await self._client.delete(key)
                await self._fallback.delete(key)
                return bool(res > 0)
            except Exception as exc:
                logger.debug("Redis delete error (%s), using fallback", exc)
        return await self._fallback.delete(key)

    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Retrieve keys by pattern.

        Args:
            pattern (str): The pattern.

        Returns:
            List[str]: List of resulting items or records.
        """
        if self._client:
            try:
                keys = []
                async for k in self._client.scan_iter(match=pattern):
                    keys.append(k)
                if keys:
                    return keys
            except Exception as exc:
                logger.debug("Redis scan error (%s), using fallback", exc)
        return await self._fallback.get_keys_by_pattern(pattern)

    async def close(self):
        """Close operation.
        """
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
        await self._fallback.close()
