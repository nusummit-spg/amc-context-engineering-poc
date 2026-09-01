# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Deterministic numeric fact extraction from document text.

Adapted from Agentic Testing Platform's taxonomy.py extract_facts() pipeline.

Extracts:
  - Scalar numeric facts: "minimum entry age 18 years" -> (entry_age, >=, 18, years)
  - Range facts: "age 18 to 60 years" -> (entry_age, between_inclusive, 18..60, years)
  - Indian currency scale normalization: lakh/crore/million
  - Nearest-subject binding via entity mention anchoring

NO LLM required — fully deterministic regex pipeline.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from app.schemas.facts import DocumentFact
from app.schemas.documents import Document, Section

# ─────────────────────────────────────────────────────────────────────────────
# AMC domain concept dictionary (canonical names + aliases for subject binding)
# ─────────────────────────────────────────────────────────────────────────────

AMC_CONCEPTS: dict[str, dict[str, Any]] = {
    "nav": {
        "aliases": ["net asset value", "nav per unit"],
        "type": "financial_metric",
    },
    "aum": {
        "aliases": ["assets under management", "total aum", "corpus"],
        "type": "financial_metric",
    },
    "exit_load": {
        "aliases": ["exit charge", "redemption charge", "exit load percentage"],
        "type": "fee",
    },
    "single_issuer_limit": {
        "aliases": ["single issuer", "single company limit", "issuer limit"],
        "type": "limit",
    },
    "single_group_limit": {
        "aliases": ["single group", "group limit", "conglomerate limit"],
        "type": "limit",
    },
    "holding_percentage": {
        "aliases": ["portfolio allocation", "% of nav", "percent of nav", "pct nav"],
        "type": "holding",
    },
    "credit_rating": {
        "aliases": ["credit rating", "rating", "rated"],
        "type": "credit",
    },
    "minimum_investment": {
        "aliases": ["minimum purchase", "minimum application", "min investment", "minimum sip"],
        "type": "eligibility",
    },
    "lock_in_period": {
        "aliases": ["lock-in", "lock in period", "minimum holding period"],
        "type": "duration",
    },
    "exit_load_duration": {
        "aliases": ["within", "holding period", "before", "redemption within"],
        "type": "duration",
    },
    "returns": {
        "aliases": ["return", "annualized return", "cagr", "absolute return", "performance"],
        "type": "financial_metric",
    },
    "expense_ratio": {
        "aliases": ["total expense ratio", "ter", "annual charges", "management fee"],
        "type": "fee",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

# Numeric value with optional operator, currency, scale, unit
NUMBER_UNIT_RE = re.compile(
    r"(?P<op>at least|at most|minimum|maximum|not less than|not more than|"
    r"up to|more than|less than|above|below|exceeds?|upto)?\s*"
    r"(?P<currency>₹|rs\.?|inr|\$)?\s*"
    r"(?P<value>\d+(?:,\d{2,3})*(?:\.\d+)?)\s*"
    r"(?P<scale>crore|cr|lakh|lac|million|thousand|k)?\s*"
    r"(?P<unit>years?|months?|days?|%|per\s*cent|percent|rupees?|inr|bps|basis\s*points?)?",
    re.I,
)

# Range: "18 to 60 years" | "18-60 years" | "18–60 years"
RANGE_RE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>years?|months?|days?|%|percent|crore|lakh)?",
    re.I,
)

# Date patterns for temporal validity
DATE_RE = re.compile(
    r"effective\s+(?:from|date)?\s+(?P<date>\d{1,2}[-/\s](?:Jan|Feb|Mar|Apr|May|Jun|"
    r"Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.I,
)


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def _scale_number(v: float, scale: str | None) -> float:
    if not scale:
        return v
    s = scale.lower().replace(" ", "")
    return v * {
        "k": 1_000, "thousand": 1_000,
        "lakh": 100_000, "lac": 100_000,
        "million": 1_000_000,
        "crore": 10_000_000, "cr": 10_000_000,
    }.get(s, 1)


def _operator(raw: str | None) -> str:
    x = (raw or "").lower().strip()
    if x in {"minimum", "at least", "not less than"}:
        return ">="
    if x in {"maximum", "at most", "not more than", "up to", "upto"}:
        return "<="
    if x in {"more than", "above", "exceeds", "exceed"}:
        return ">"
    if x in {"less than", "below"}:
        return "<"
    return "="


def _operator_from_context(text: str, value_start: int, raw_op: str | None) -> str:
    """Infer operator from surrounding text when not explicit in the match."""
    direct = _operator(raw_op)
    if raw_op:
        return direct
    prefix = text[max(0, value_start - 90):value_start].lower()
    patterns = [
        (r"(?:maximum|at most|not more than|up to|upto)\b[^.;:]{0,55}$", "<="),
        (r"(?:minimum|at least|not less than)\b[^.;:]{0,55}$", ">="),
        (r"(?:above|more than|greater than|exceeds?)\b[^.;:]{0,35}$", ">"),
        (r"(?:below|less than|lower than)\b[^.;:]{0,35}$", "<"),
    ]
    for pat, op in patterns:
        if re.search(pat, prefix, flags=re.I):
            return op
    return direct


def _entity_mentions(
    text: str, concepts: dict[str, dict]
) -> list[tuple[int, int, str]]:
    """Find (start, end, canonical_name) for all concept/alias mentions in text."""
    mentions: list[tuple[int, int, str]] = []
    for canonical, spec in concepts.items():
        terms = [canonical] + spec.get("aliases", [])
        for term in terms:
            for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.I):
                mentions.append((m.start(), m.end(), canonical))
    # Prefer longer matches at the same position
    mentions.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    return mentions


def _nearest_subject(
    mentions: list[tuple[int, int, str]],
    value_start: int,
    value_end: int,
    max_distance: int = 120,
) -> str | None:
    """Find the nearest concept mention relative to a numeric value span."""
    if not mentions:
        return None
    scored: list[tuple[int, int, str]] = []
    for start, end, name in mentions:
        if end <= value_start:
            distance = value_start - end
            side_penalty = 0
        elif start >= value_end:
            distance = start - value_end
            side_penalty = 15  # slight penalty for subject after value
        else:
            distance = 0
            side_penalty = 0
        scored.append((distance + side_penalty, -(end - start), name))
    scored.sort()
    best_distance, _, best_name = scored[0]
    return best_name if best_distance <= max_distance else None


def extract_facts(
    document: Document,
    concepts: dict[str, dict] | None = None,
) -> list[DocumentFact]:
    """Extract numeric and range facts from all sections of a document.
    
    Args:
        document: The ingested Document with sections.
        concepts: Domain concept dictionary. Defaults to AMC_CONCEPTS.
        
    Returns:
        List of DocumentFact objects, deduplicated by stable fact ID.
        Each fact also carries valid_from / valid_to when temporal qualifiers
        are detected in the section text (Phase 3 Item K).
    """
    concepts = concepts or AMC_CONCEPTS
    facts: list[DocumentFact] = []
    seen_ids: set[str] = set()

    for section in document.sections:
        text = section.text
        if not text.strip():
            continue

        mentions = _entity_mentions(text, concepts)

        # Phase 3 Item K: Extract temporal validity from section text
        # Propagate to all facts extracted from this section.
        section_valid_from: Optional[str] = None
        section_valid_to:   Optional[str] = None
        # Inherit from Section model if parser already populated it
        if getattr(section, "valid_from", None):
            section_valid_from = section.valid_from
        if getattr(section, "valid_to", None):
            section_valid_to = section.valid_to
        # Scan for "effective from <date>" patterns in section text
        for dm in DATE_RE.finditer(text):
            raw_date = dm.group("date").strip()
            try:
                from datetime import datetime as _dt
                for fmt in ("%d %B %Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d",
                            "%d %b %Y", "%B %Y", "%b %Y"):
                    try:
                        parsed = _dt.strptime(raw_date, fmt)
                        section_valid_from = parsed.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        # 1. Range facts first (highest value for boundary testing)
        range_spans: list[tuple[int, int]] = []
        for rm in RANGE_RE.finditer(text):
            range_spans.append((rm.start(), rm.end()))
            lo = float(rm.group("low").replace(",", ""))
            hi = float(rm.group("high").replace(",", ""))
            unit = rm.group("unit")
            subject = _nearest_subject(mentions, rm.start(), rm.end()) or "document_value"
            fid = _stable_id("FACT", f"{document.document_id}:{section.section_id}:{subject}:range:{lo}:{hi}:{unit}")
            if fid not in seen_ids:
                seen_ids.add(fid)
                facts.append(DocumentFact(
                    fact_id=fid,
                    document_id=document.document_id,
                    section_id=section.section_id,
                    block_id=f"sec-{section.section_id}",
                    page_num=section.page_start,
                    subject=subject,
                    attribute="range",
                    operator="between_inclusive",
                    value=f"{lo:g}..{hi:g}",
                    unit=unit,
                    range_low=lo,
                    range_high=hi,
                    evidence_text=text[:500],
                    confidence=0.95 if subject != "document_value" else 0.72,
                    valid_from=section_valid_from,
                    valid_to=section_valid_to,
                ))

        # 2. Scalar numeric facts
        for nm in NUMBER_UNIT_RE.finditer(text):
            if any(a <= nm.start() < z or a < nm.end() <= z for a, z in range_spans):
                continue  # skip — already captured as range
            raw_v = nm.group("value")
            if raw_v is None:
                continue
            subject = _nearest_subject(mentions, nm.start(), nm.end())
            if not subject:
                continue

            v = _scale_number(float(raw_v.replace(",", "")), nm.group("scale"))
            unit = nm.group("unit")
            currency = nm.group("currency")
            if currency:
                unit = "INR" if currency.lower() in {"₹", "rs.", "rs", "inr"} else currency
            op = _operator_from_context(text, nm.start(), nm.group("op"))

            fid = _stable_id("FACT", f"{document.document_id}:{section.section_id}:{subject}:{op}:{v}:{unit}")
            if fid not in seen_ids:
                seen_ids.add(fid)
                facts.append(DocumentFact(
                    fact_id=fid,
                    document_id=document.document_id,
                    section_id=section.section_id,
                    block_id=f"sec-{section.section_id}",
                    page_num=section.page_start,
                    subject=subject,
                    attribute="numeric_value",
                    operator=op,
                    value=v,
                    unit=unit,
                    evidence_text=text[:500],
                    confidence=0.93,
                    valid_from=section_valid_from,
                    valid_to=section_valid_to,
                ))

    return facts
