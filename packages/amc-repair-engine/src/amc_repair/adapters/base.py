"""
Base adapter interfaces for cache and graph systems.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class CacheAdapter(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve operation.

        Args:
            key (str): The key.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Set operation.

        Args:
            key (str): The key.
            value (Dict[str, Any]): The value.
            ttl_seconds (Optional[int]): Collection or list of ttl seconds.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete operation.

        Args:
            key (str): The key.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Retrieve keys by pattern.

        Args:
            pattern (str): The pattern.

        Returns:
            List[str]: List of resulting items or records.
        """
        pass

    @abstractmethod
    async def close(self):
        """Close operation.
        """
        pass


class GraphAdapter(ABC):
    @abstractmethod
    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        """Apply entity patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        """Retrieve entity property.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            Optional[Any]: Matching object or record if found, None otherwise.
        """
        pass

    @abstractmethod
    async def create_shadow_patch(self, entity_id: str, patch_id: str, attribute: str, value: Any) -> bool:
        """Create shadow patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            patch_id (str): Unique identifier of the patch.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def delete_shadow_patch(self, patch_id: str) -> bool:
        """Delete shadow patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def close(self):
        """Close operation.
        """
        pass
