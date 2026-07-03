"""
Entity Resolver — [Entity Resolver] stage. Collapses name variants down to a
canonical entity keyed on ISIN/amfi_code. The master list is loaded directly
from your AMFI/ folder (seed data, never touches NER) — point
AMFI_MASTER_CSV at a normalized export of that folder.
"""
import os
import re
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from rapidfuzz import fuzz, process

AMFI_MASTER_CSV = os.environ.get("AMFI_MASTER_CSV", "data/taxonomy/amfi_master.csv")
FUZZY_THRESHOLD = int(os.environ.get("FUZZY_MATCH_THRESHOLD", "92"))

_SUFFIX_PATTERN = re.compile(
    r"\b(direct|regular|growth|idcw|dividend|payout|reinvestment|plan)\b", re.IGNORECASE
)


@dataclass
class ResolvedEntity:
    raw_text: str
    canonical_name: str
    canonical_key: Optional[str]
    entity_type: str
    match_method: str  # exact | normalized | fuzzy | unresolved
    match_score: float


class EntityResolver:
    def __init__(self, amfi_master_csv: str = AMFI_MASTER_CSV):
        try:
            self.master_df = pd.read_csv(amfi_master_csv)
        except FileNotFoundError:
            print(f"[resolver] WARNING: {amfi_master_csv} not found, resolver will unresolved-flag everything")
            self.master_df = pd.DataFrame(columns=["canonical_name", "isin", "amfi_code", "entity_type"])

        self._name_to_row = {self._normalize(r["canonical_name"]): r for _, r in self.master_df.iterrows()}
        self._canonical_names = list(self._name_to_row.keys())

    @staticmethod
    def _normalize(text: str) -> str:
        text = _SUFFIX_PATTERN.sub("", str(text))
        text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
        return re.sub(r"\s+", " ", text).strip().lower()

    def resolve(self, raw_text: str, entity_type_hint: str = "") -> ResolvedEntity:
        normalized = self._normalize(raw_text)

        if normalized in self._name_to_row:
            row = self._name_to_row[normalized]
            return ResolvedEntity(
                raw_text=raw_text, canonical_name=row["canonical_name"],
                canonical_key=row.get("isin") or row.get("amfi_code"),
                entity_type=row.get("entity_type", entity_type_hint),
                match_method="normalized", match_score=1.0,
            )

        if self._canonical_names:
            best = process.extractOne(normalized, self._canonical_names, scorer=fuzz.token_sort_ratio)
            if best and best[1] >= FUZZY_THRESHOLD:
                row = self._name_to_row[best[0]]
                return ResolvedEntity(
                    raw_text=raw_text, canonical_name=row["canonical_name"],
                    canonical_key=row.get("isin") or row.get("amfi_code"),
                    entity_type=row.get("entity_type", entity_type_hint),
                    match_method="fuzzy", match_score=best[1] / 100.0,
                )

        # Unresolved entities still get written to the graph (name-keyed) —
        # they surface in the ontology review loop rather than being dropped silently.
        return ResolvedEntity(
            raw_text=raw_text, canonical_name=raw_text.strip(), canonical_key=None,
            entity_type=entity_type_hint, match_method="unresolved", match_score=0.0,
        )