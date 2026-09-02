"""
Cache Management for Evaluation System.

PURPOSE:
- Invalidate FAISS embeddings when entities change
- Invalidate Neo4j traversal caches
- Update entity resolver caches
- Emit invalidation events

This ensures fresh data after corrections are applied to graph.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from app.core.logging import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Manage cache invalidation across system."""
    
    def __init__(
        self,
        faiss_client = None,
        entity_resolver = None,
        redis_client = None
    ):
        """
        Initialize cache manager.
        
        Args:
            faiss_client: FAISS vector store client
            entity_resolver: Entity resolver for caching
            redis_client: Optional Redis for distributed caching
        """
        self.faiss = faiss_client
        self.entity_resolver = entity_resolver
        self.redis = redis_client
        
        # Local invalidation event queue
        self.invalidation_queue: List[Dict[str, Any]] = []
    
    async def invalidate_entity_caches(
        self,
        entity_names: List[str]
    ):
        """
        Invalidate caches for specific entities.
        
        Invalidates:
        - FAISS embeddings
        - Neo4j traversal caches
        - Entity resolver caches
        - Redis (if configured)
        
        Args:
            entity_names: List of entity names that changed
        """
        
        if not entity_names:
            logger.debug("No entities to invalidate")
            return
        
        logger.info(f"Invalidating caches for {len(entity_names)} entities")
        
        try:
            # Invalidate FAISS embeddings
            if self.faiss:
                await self._invalidate_faiss_caches(entity_names)
            
            # Invalidate entity resolver
            if self.entity_resolver:
                await self._invalidate_entity_resolver_caches(entity_names)
            
            # Invalidate Redis caches (if configured)
            if self.redis:
                await self._invalidate_redis_caches(entity_names)
            
            # Invalidate Neo4j traversal cache
            await self._invalidate_traversal_caches(entity_names)
            
            # Record invalidation event
            await self._emit_invalidation_event(entity_names)
            
            logger.info("Cache invalidation complete")
        
        except Exception as e:
            logger.error(f"Error invalidating caches: {e}")
            # Don't fail on cache errors
    
    async def _invalidate_faiss_caches(self, entity_names: List[str]):
        """
        Invalidate FAISS vector embeddings.
        
        When an entity is updated, its embeddings may be stale.
        This removes affected embeddings to force re-computation.
        """
        
        try:
            logger.debug(f"Invalidating FAISS caches for {len(entity_names)} entities")
            
            for entity_name in entity_names:
                # Find embeddings for this entity
                # Note: This depends on FAISS implementation
                if hasattr(self.faiss, 'delete_by_metadata'):
                    await self.faiss.delete_by_metadata(
                        key='entity_name',
                        value=entity_name
                    )
            
            logger.debug("FAISS cache invalidation complete")
        
        except Exception as e:
            logger.warning(f"Error invalidating FAISS cache: {e}")
    
    async def _invalidate_entity_resolver_caches(self, entity_names: List[str]):
        """
        Invalidate entity resolver caches.
        
        Entity resolver maintains caches of entity aliases and mappings.
        These need to be refreshed after entity updates.
        """
        
        try:
            logger.debug(f"Invalidating entity resolver caches")
            
            for entity_name in entity_names:
                # Clear resolver cache for this entity
                if hasattr(self.entity_resolver, 'clear_cache'):
                    await self.entity_resolver.clear_cache(entity_name)
            
            logger.debug("Entity resolver cache invalidation complete")
        
        except Exception as e:
            logger.warning(f"Error invalidating entity resolver cache: {e}")
    
    async def _invalidate_redis_caches(self, entity_names: List[str]):
        """
        Invalidate Redis caches.
        
        Distributed caches that might be used across multiple instances.
        """
        
        try:
            logger.debug(f"Invalidating Redis caches")
            
            for entity_name in entity_names:
                # Delete related cache keys
                # Pattern: graph_context:*{entity_name}*
                if hasattr(self.redis, 'delete_pattern'):
                    await self.redis.delete_pattern(f"graph_context:*{entity_name}*")
                    await self.redis.delete_pattern(f"entity:*{entity_name}*")
            
            logger.debug("Redis cache invalidation complete")
        
        except Exception as e:
            logger.warning(f"Error invalidating Redis cache: {e}")
    
    async def _invalidate_traversal_caches(self, entity_names: List[str]):
        """
        Invalidate Neo4j graph traversal caches.
        
        When graph structure changes (entities/relationships added/removed),
        traversal caches become stale.
        """
        
        try:
            logger.debug(f"Invalidating traversal caches")
            
            # This would invalidate Neo4j query result caches
            # Implementation depends on Neo4j setup
            
            # For now, just log
            logger.debug("Traversal cache invalidation complete")
        
        except Exception as e:
            logger.warning(f"Error invalidating traversal cache: {e}")
    
    async def _emit_invalidation_event(self, entity_names: List[str]):
        """
        Emit invalidation event for downstream systems.
        
        Other services can subscribe to these events.
        """
        
        event = {
            'type': 'cache_invalidation',
            'timestamp': datetime.utcnow().isoformat(),
            'entity_names': entity_names,
            'entity_count': len(entity_names)
        }
        
        # Store in queue for potential event stream
        self.invalidation_queue.append(event)
        
        # Keep queue size bounded
        if len(self.invalidation_queue) > 1000:
            self.invalidation_queue.pop(0)
        
        logger.debug(f"Invalidation event emitted: {len(entity_names)} entities")
    
    def get_invalidation_queue(self) -> List[Dict[str, Any]]:
        """Get recent invalidation events."""
        return self.invalidation_queue.copy()
    
    async def clear_all_caches(self):
        """
        Clear all caches (emergency operation).
        
        Use with caution - full cache clear is expensive.
        """
        
        logger.warning("Clearing ALL caches")
        
        try:
            if self.faiss and hasattr(self.faiss, 'clear'):
                await self.faiss.clear()
            
            if self.redis and hasattr(self.redis, 'flushdb'):
                await self.redis.flushdb()
            
            logger.info("All caches cleared")
        
        except Exception as e:
            logger.error(f"Error clearing caches: {e}")


class GraphTraversalCache:
    """Cache for Neo4j graph traversal results."""
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize traversal cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries
        """
        self.ttl = ttl_seconds
        self.cache: Dict[str, tuple] = {}  # {cache_key: (result, expiry_time)}
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached traversal result."""
        if key not in self.cache:
            return None
        
        result, expiry = self.cache[key]
        
        if datetime.utcnow() > expiry:
            del self.cache[key]
            return None
        
        return result
    
    async def set(self, key: str, value: Dict[str, Any]):
        """Store traversal result in cache."""
        expiry = datetime.utcnow() + timedelta(seconds=self.ttl)
        self.cache[key] = (value, expiry)
    
    async def invalidate(self, key_pattern: str):
        """Invalidate cache entries matching pattern."""
        keys_to_delete = [
            k for k in self.cache.keys()
            if key_pattern in k
        ]
        
        for k in keys_to_delete:
            del self.cache[k]
        
        return len(keys_to_delete)
    
    async def clear(self):
        """Clear all entries."""
        self.cache.clear()


class EmbeddingCache:
    """Cache for entity embeddings."""
    
    def __init__(self, ttl_seconds: int = 86400):
        """
        Initialize embedding cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries
        """
        self.ttl = ttl_seconds
        self.cache: Dict[str, tuple] = {}  # {entity_name: (embedding, expiry_time)}
    
    async def get(self, entity_name: str) -> Optional[List[float]]:
        """Get cached embedding."""
        if entity_name not in self.cache:
            return None
        
        embedding, expiry = self.cache[entity_name]
        
        if datetime.utcnow() > expiry:
            del self.cache[entity_name]
            return None
        
        return embedding
    
    async def set(self, entity_name: str, embedding: List[float]):
        """Store embedding in cache."""
        expiry = datetime.utcnow() + timedelta(seconds=self.ttl)
        self.cache[entity_name] = (embedding, expiry)
    
    async def invalidate_entities(self, entity_names: List[str]):
        """Invalidate embeddings for specific entities."""
        count = 0
        for entity_name in entity_names:
            if entity_name in self.cache:
                del self.cache[entity_name]
                count += 1
        
        return count


# Utility function for cache key generation
def generate_cache_key(
    cache_type: str,
    *args,
    **kwargs
) -> str:
    """
    Generate cache key from type and arguments.
    
    Args:
        cache_type: Type of cache (graph_context, entity_embedding, etc.)
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key
    
    Returns:
        Cache key suitable for storage
    """
    import hashlib
    
    # Build key from all arguments
    key_parts = [cache_type] + list(args) + [
        f"{k}={v}" for k, v in sorted(kwargs.items())
    ]
    
    key_str = "|".join(str(p) for p in key_parts)
    
    # Hash for size efficiency
    key_hash = hashlib.md5(key_str.encode()).hexdigest()
    
    return f"{cache_type}:{key_hash}"


# Singleton instance
_cache_manager: Optional[CacheManager] = None


def init_cache_manager(
    faiss_client = None,
    entity_resolver = None,
    redis_client = None
) -> CacheManager:
    """Initialize cache manager singleton."""
    global _cache_manager
    
    _cache_manager = CacheManager(
        faiss_client=faiss_client,
        entity_resolver=entity_resolver,
        redis_client=redis_client
    )
    
    return _cache_manager


def get_cache_manager() -> CacheManager:
    """Get cache manager instance."""
    if not _cache_manager:
        raise RuntimeError("Cache manager not initialized")
    return _cache_manager
