"""
AMC Context Engineering — Multilingual Language Detector & Regional Query Router
Supports English, Hindi, Hinglish, Marathi, Gujarati, Tamil, and other Indian languages.
Uses 'langdetect' if installed, with a native Unicode script + keyword fallback engine.
"""

import re
from typing import Dict, Any

# Try importing langdetect if available
HAS_LANGDETECT = False
try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

# Regional Unicode Ranges
UNICODE_RANGES = {
    "hi": re.compile(r'[\u0900-\u097F]'),  # Devanagari (Hindi / Marathi)
    "gu": re.compile(r'[\u0A80-\u0AFF]'),  # Gujarati
    "ta": re.compile(r'[\u0B80-\u0BFF]'),  # Tamil
    "te": re.compile(r'[\u0C00-\u0C7F]'),  # Telugu
    "kn": re.compile(r'[\u0C80-\u0CFF]'),  # Kannada
    "bn": re.compile(r'[\u0980-\u09FF]'),  # Bengali
}

# Hinglish Common Indicators (Romanized Hindi words in financial queries).
# Deliberately excludes "fund", "rule", "circular" — standard English terms
# in this exact domain, which false-positived on almost every plain-English
# query ("what's the exit load on this fund?") when included.
HINGLISH_KEYWORDS = {
    "kya", "hai", "kaise", "kab", "karo", "nivesh", "paisa", "milega",
    "chahiye", "batao", "kaunsa", "sabse", "accha", "fayda"
}

# English term normalization mapping for regional queries
REGIONAL_QUERY_TRANSLATIONS = {
    "nivesh": "investment",
    "fayda": "benefit returns",
    "batao": "tell explain",
    "accha": "best top performing",
    "niti": "policy regulation",
    "niyam": "rule regulation",
}


def detect_query_language(query: str) -> Dict[str, Any]:
    """
    Detect language of query string. Returns dict with:
    - language: ISO language code ('en', 'hi', 'gu', 'ta', etc.)
    - is_regional: True if regional/Hinglish
    - is_hinglish: True if Romanized Hindi
    - normalized_query: Query with regional terms mapped to English for Cypher lookup
    """
    if not query or not query.strip():
        return {"language": "en", "is_regional": False, "is_hinglish": False, "normalized_query": query}

    query_str = query.strip()

    # 1. Check Unicode script ranges first (100% deterministic for non-Latin scripts)
    for lang_code, pattern in UNICODE_RANGES.items():
        if pattern.search(query_str):
            normalized = _normalize_regional_terms(query_str)
            return {
                "language": lang_code,
                "is_regional": True,
                "is_hinglish": False,
                "normalized_query": normalized,
                "detection_engine": "unicode_script_range"
            }

    # 2. Try langdetect if available
    if HAS_LANGDETECT:
        try:
            detected = detect(query_str)
            if detected != "en":
                normalized = _normalize_regional_terms(query_str)
                return {
                    "language": detected,
                    "is_regional": True,
                    "is_hinglish": False,
                    "normalized_query": normalized,
                    "detection_engine": "langdetect_library"
                }
        except Exception:
            pass

    # 3. Check for Hinglish (Romanized Hindi) keywords
    tokens = set(re.findall(r'\b\w+\b', query_str.lower()))
    matching_hinglish = tokens.intersection(HINGLISH_KEYWORDS)
    if len(matching_hinglish) >= 1:
        normalized = _normalize_regional_terms(query_str)
        return {
            "language": "hi_hinglish",
            "is_regional": True,
            "is_hinglish": True,
            "normalized_query": normalized,
            "detection_engine": "hinglish_keyword_rules"
        }

    # Default to English
    return {
        "language": "en",
        "is_regional": False,
        "is_hinglish": False,
        "normalized_query": query_str,
        "detection_engine": "default_english"
    }


def _normalize_regional_terms(text: str) -> str:
    """Normalize regional terms to English keywords to improve Neo4j entity matching."""
    normalized = text
    for term, eng in REGIONAL_QUERY_TRANSLATIONS.items():
        normalized = re.sub(rf'\b{term}\b', eng, normalized, flags=re.IGNORECASE)
    return normalized
