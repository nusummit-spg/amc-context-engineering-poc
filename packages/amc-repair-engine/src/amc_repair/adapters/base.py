"""
Base adapter interfaces for cache and graph systems.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class CacheAdapter(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        pass

    @abstractmethod
    async def close(self):
        pass


class GraphAdapter(ABC):
    @abstractmethod
    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        pass

    @abstractmethod
    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def close(self):
        pass
