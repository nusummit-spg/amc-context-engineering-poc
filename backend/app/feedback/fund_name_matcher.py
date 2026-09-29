# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
fund_name_matcher.py
====================
Resolves ambiguous, fuzzy, and abbreviated mutual fund names from user feedback
to canonical ISIN identifiers using a 4-tier fallback chain:
  1. Exact Match Lookup
  2. Fuzzy String Matching (RapidFuzz / SequenceMatcher)
  3. Semantic Embedding Similarity (SentenceTransformer)
  4. User Context Disambiguation (Direct vs Regular plan)
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.feedback.fund_name_matcher")

# Lazy embedder
_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            logger.debug("SentenceTransformer notice in fund matcher: %s", exc)
            _embedder = False
    return _embedder if _embedder is not False else None


@dataclass
class FundCandidate:
    isin: str
    fund_name: str
    score: float
    match_method: str


class FundNameMatcher:
    FUZZY_THRESHOLD = 0.70  # 70% match threshold
    EMBEDDING_THRESHOLD = 0.75
    AMBIGUITY_THRESHOLD = 0.80

    ABBREVIATIONS = {
        "absl": "aditya birla sun life",
        "icici pru": "icici prudential",
        "mirae": "mirae asset",
        "sbi": "sbi",
        "hdfc": "hdfc",
        "kotak": "kotak flexicap",
        "axis": "axis",
    }

    def __init__(self, fund_master_data: Optional[List[Dict[str, Any]]] = None):
        if fund_master_data is None:
            fund_master_data = self._load_default_fund_master()
        self.fund_master = fund_master_data

        self.isin_to_fund = {f["isin"]: f for f in self.fund_master}
        self.name_to_isin = {f["fund_name"].lower(): f["isin"] for f in self.fund_master}
        self.fund_names = [f["fund_name"] for f in self.fund_master]

        self._fund_embeddings = None
        self._embeddings_initialized = False

    def _load_default_fund_master(self) -> List[Dict[str, Any]]:
        master_path = Path(__file__).resolve().parent.parent / "data" / "fund_master.json"
        if master_path.exists():
            try:
                with open(master_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Could not load fund_master.json: %s", exc)
        return []

    def _get_fund_embeddings(self):
        if not self._embeddings_initialized:
            self._embeddings_initialized = True
            embedder = get_embedder()
            if embedder and self.fund_names:
                try:
                    self._fund_embeddings = embedder.encode(self.fund_names)
                except Exception as exc:
                    logger.warning("Failed precomputing fund embeddings: %s", exc)
        return self._fund_embeddings

    def _normalize_input(self, text: str) -> str:
        clean = (text or "").strip().lower()
        for abbr, full in self.ABBREVIATIONS.items():
            if abbr in clean:
                clean = clean.replace(abbr, full)
        return clean

    def resolve(
        self,
        user_input: str,
        user_context: Optional[Dict[str, Any]] = None,
        top_k: int = 3
    ) -> Optional[Dict[str, Any]]:
        if not user_input or not user_input.strip():
            return None

        clean_input = self._normalize_input(user_input)

        # 1. Exact match (or direct ISIN match)
        if user_input.strip() in self.isin_to_fund:
            fund = self.isin_to_fund[user_input.strip()]
            return {
                "isin": fund["isin"],
                "fund_name": fund["fund_name"],
                "confidence": 1.0,
                "method": "exact_isin_match",
                "ambiguous": False
            }

        if clean_input in self.name_to_isin:
            isin = self.name_to_isin[clean_input]
            return {
                "isin": isin,
                "fund_name": self.isin_to_fund[isin]["fund_name"],
                "confidence": 1.0,
                "method": "exact_name_match",
                "ambiguous": False
            }

        # 2. Fuzzy string matching
        fuzzy_candidates = self._fuzzy_match(clean_input)

        # 3. Embedding similarity
        embedding_candidates = self._embedding_match(user_input)

        # Merge and sort
        all_candidates = self._merge_candidates(fuzzy_candidates, embedding_candidates)
        if not all_candidates:
            return None

        all_candidates.sort(key=lambda x: x.score, reverse=True)
        top_candidate = all_candidates[0]

        # 4. Disambiguation if multiple high-scoring candidates exist
        high_scoring = [c for c in all_candidates if c.score >= self.AMBIGUITY_THRESHOLD]
        if len(high_scoring) > 1:
            disambiguated = self._disambiguate(high_scoring[:top_k], user_context)
            if disambiguated:
                return disambiguated

            # Ambiguous result
            return {
                "isin": top_candidate.isin,
                "fund_name": top_candidate.fund_name,
                "confidence": round(top_candidate.score, 2),
                "method": "ambiguous",
                "ambiguous": True,
                "candidates": [
                    {"isin": c.isin, "fund_name": c.fund_name, "score": round(c.score, 2)}
                    for c in all_candidates[:top_k]
                ]
            }

        return {
            "isin": top_candidate.isin,
            "fund_name": top_candidate.fund_name,
            "confidence": round(top_candidate.score, 2),
            "method": top_candidate.match_method,
            "ambiguous": False
        }

    def _fuzzy_match(self, clean_input: str) -> List[FundCandidate]:
        candidates = []
        try:
            from rapidfuzz import fuzz
            use_rapidfuzz = True
        except ImportError:
            import difflib
            use_rapidfuzz = False

        for fund in self.fund_master:
            fname = fund["fund_name"].lower()
            if use_rapidfuzz:
                from rapidfuzz import fuzz
                score = fuzz.token_set_ratio(clean_input, fname) / 100.0
            else:
                import difflib
                score = difflib.SequenceMatcher(None, clean_input, fname).ratio()

            # Boost score if key words (like bluechip, large cap) match
            words_in_input = set(clean_input.split())
            words_in_fname = set(fname.split())
            overlap = len(words_in_input & words_in_fname)
            if overlap >= 2:
                score = min(score + 0.15, 1.0)

            if score >= self.FUZZY_THRESHOLD:
                candidates.append(FundCandidate(
                    isin=fund["isin"],
                    fund_name=fund["fund_name"],
                    score=score,
                    match_method="fuzzy_match"
                ))
        return candidates

    def _embedding_match(self, user_input: str) -> List[FundCandidate]:
        embedder = get_embedder()
        fund_embeddings = self._get_fund_embeddings()
        if embedder is None or fund_embeddings is None:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            u_emb = embedder.encode([user_input])
            sims = cosine_similarity(u_emb, fund_embeddings)[0]
            candidates = []
            for idx, score in enumerate(sims):
                if score >= self.EMBEDDING_THRESHOLD:
                    fund = self.fund_master[idx]
                    candidates.append(FundCandidate(
                        isin=fund["isin"],
                        fund_name=fund["fund_name"],
                        score=float(score),
                        match_method="embedding_match"
                    ))
            return candidates
        except Exception as exc:
            logger.debug("Embedding similarity match error: %s", exc)
            return []

    def _merge_candidates(
        self,
        fuzzy_candidates: List[FundCandidate],
        embedding_candidates: List[FundCandidate]
    ) -> List[FundCandidate]:
        best_by_isin: Dict[str, FundCandidate] = {}
        for c in fuzzy_candidates + embedding_candidates:
            if c.isin not in best_by_isin or c.score > best_by_isin[c.isin].score:
                best_by_isin[c.isin] = c
        return list(best_by_isin.values())

    def _disambiguate(
        self,
        candidates: List[FundCandidate],
        user_context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if user_context:
            queries = user_context.get("previous_queries", [])
            q_text = " ".join(queries).lower()
            if "direct" in q_text:
                for c in candidates:
                    fund = self.isin_to_fund.get(c.isin, {})
                    if fund.get("plan") == "Direct":
                        return {
                            "isin": c.isin,
                            "fund_name": c.fund_name,
                            "confidence": 0.88,
                            "method": "user_context_disambiguation",
                            "ambiguous": False
                        }
            elif "regular" in q_text:
                for c in candidates:
                    fund = self.isin_to_fund.get(c.isin, {})
                    if fund.get("plan") == "Regular":
                        return {
                            "isin": c.isin,
                            "fund_name": c.fund_name,
                            "confidence": 0.88,
                            "method": "user_context_disambiguation",
                            "ambiguous": False
                        }

        # Popularity heuristic: Direct Growth plans are most commonly queried
        for c in candidates:
            fund = self.isin_to_fund.get(c.isin, {})
            if fund.get("plan") == "Direct" and fund.get("option") == "Growth":
                return {
                    "isin": c.isin,
                    "fund_name": c.fund_name,
                    "confidence": 0.82,
                    "method": "popularity_heuristic",
                    "ambiguous": False
                }

        return None

    def match_fund(
        self,
        fund_name: str,
        user_context: Optional[Dict[str, Any]] = None,
        top_k: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Alias for resolve() method."""
        return self.resolve(fund_name, user_context=user_context, top_k=top_k)


_global_fund_matcher = None


def get_fund_name_matcher() -> FundNameMatcher:
    global _global_fund_matcher
    if _global_fund_matcher is None:
        _global_fund_matcher = FundNameMatcher()
    return _global_fund_matcher
