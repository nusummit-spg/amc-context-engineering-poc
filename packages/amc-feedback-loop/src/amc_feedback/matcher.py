"""
Fuzzy entity matcher mapping text spans to canonical entities via RapidFuzz.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from rapidfuzz import fuzz, process
from .config import FeedbackConfig
from .schemas import ResolvedEntity

class EntityMatcher:
    def __init__(self, config: FeedbackConfig):
        self.config = config
        self._catalog: Dict[str, Dict[str, Any]] = {}
        self._names: List[str] = []
        self._load_catalog()

    def _load_catalog(self):
        if self.config.entity_master_path:
            path = Path(self.config.entity_master_path)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                name = item.get("name") or item.get("scheme_name") or ""
                                eid = item.get("isin") or item.get("id") or name
                                if name:
                                    self._catalog[name] = {"id": eid, "metadata": item}
                                    self._names.append(name)
                        elif isinstance(data, dict):
                            for name, meta in data.items():
                                eid = meta.get("id", name) if isinstance(meta, dict) else name
                                self._catalog[name] = {"id": eid, "metadata": meta if isinstance(meta, dict) else {}}
                                self._names.append(name)
                except Exception:
                    pass

        # Seed defaults if empty
        if not self._names:
            defaults = [
                ("Axis Bluechip Fund", "INF846K01DP5"),
                ("HDFC Balanced Advantage Fund", "INF179K01BE2"),
                ("SBI Small Cap Fund", "INF200K01T37"),
                ("Adani Enterprises", "INE423A01024"),
            ]
            for name, isin in defaults:
                self._catalog[name] = {"id": isin, "metadata": {"isin": isin, "name": name}}
                self._names.append(name)

    def match(self, query_text: str) -> Optional[ResolvedEntity]:
        if not self._names:
            return None

        # Check exact or substring containment first
        for name in self._names:
            if name.lower() in query_text.lower():
                meta = self._catalog[name]
                return ResolvedEntity(
                    canonical_id=meta["id"],
                    canonical_name=name,
                    confidence=1.0,
                    metadata=meta["metadata"]
                )

        # Fuzzy matching
        match_result = process.extractOne(
            query_text,
            self._names,
            scorer=fuzz.partial_ratio
        )
        if match_result:
            matched_name, score, _ = match_result
            norm_score = score / 100.0
            if norm_score >= self.config.fuzzy_match_threshold:
                meta = self._catalog[matched_name]
                return ResolvedEntity(
                    canonical_id=meta["id"],
                    canonical_name=matched_name,
                    confidence=norm_score,
                    metadata=meta["metadata"]
                )

        return None
