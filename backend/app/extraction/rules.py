# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Deterministic rule compilation from document text.

Adapted from Agentic Testing Platform's extract_rules() pipeline.

Extracts structured compliance rules:
  IF...THEN patterns (confidence 0.94)
  WHEN...THEN / WHEN...COMMA patterns (confidence 0.86)
  UNLESS/EXCEPT patterns (confidence 0.78)
  General rule-trigger sentences (confidence 0.68)

Filter: Pure scalar constraints ("maximum X is 60") are excluded unless
they also contain true branching (IF/WHEN/UNLESS).
This avoids double-counting facts already captured by extract_facts().
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.schemas.rules import DocumentRule
from app.schemas.documents import Document

# Keywords that signal a conditional or rule sentence
RULE_TRIGGERS = (
    " if ", " when ", " where ", " provided that ", " subject to ",
    " unless ", " except ", " only if ", " shall ", " must ",
    " cannot ", " not eligible ", " may not ", " within ",
    " no later than ", " in case ", " in the event ",
)

# True branching keywords (exclude pure scalar constraints that have these)
_BRANCHING_RE = re.compile(
    r"\b(if|when|unless|except|provided that|subject to|only if|where|in case|in the event)\b",
    re.I,
)

# Scalar constraint keywords (without branching -> becomes a Fact, not a Rule)
_SCALAR_RE = re.compile(
    r"\b(maximum|minimum|at least|at most|not less than|not more than|up to|more than|less than)\b",
    re.I,
)


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_rules(document: Document) -> list[DocumentRule]:
    """Extract structured conditional rules from all sections of a document.
    
    Returns:
        List of DocumentRule objects, each with condition/outcome/exception.
    """
    rules: list[DocumentRule] = []
    seen_ids: set[str] = set()

    for section in document.sections:
        text = section.text
        if not text.strip():
            continue

        # Split into sentences for per-sentence rule detection
        sentences = re.split(r"(?<=[.!?;])\s+(?=[A-Z])", text)

        for sentence in sentences:
            sentence = _clean(sentence)
            if len(sentence) < 20:
                continue

            padded = f" {sentence.lower()} "
            if not any(t in padded for t in RULE_TRIGGERS):
                continue

            lower = sentence.lower()
            has_branching = bool(_BRANCHING_RE.search(lower))
            has_scalar = bool(_SCALAR_RE.search(lower)) and bool(re.search(r"\d", sentence))

            # Skip pure scalar constraints — they're captured as Facts
            if has_scalar and not has_branching:
                continue

            # ── Compile IF...THEN ─────────────────────────────────────────────
            condition = sentence
            outcome = None
            exception = None
            confidence = 0.68
            trigger_words: list[str] = []

            m_if_then = re.search(
                r"\bif\b(.+?)\bthen\b(.+)$", sentence, flags=re.I
            )
            if m_if_then:
                condition = _clean(m_if_then.group(1))
                outcome = _clean(m_if_then.group(2))
                confidence = 0.94
                trigger_words.append("if-then")
            else:
                # ── WHEN...COMMA/COLON ────────────────────────────────────────
                m_when = re.search(
                    r"\bwhen\b(.+?)(?:,|;|:\s)(.+)$", sentence, flags=re.I
                )
                if m_when:
                    condition = _clean(m_when.group(1))
                    outcome = _clean(m_when.group(2))
                    confidence = 0.86
                    trigger_words.append("when")

            # ── UNLESS/EXCEPT ─────────────────────────────────────────────────
            m_unless = re.search(r"\b(?:unless|except)\b(.+)$", sentence, flags=re.I)
            if m_unless:
                exception = _clean(m_unless.group(1))
                confidence = max(confidence, 0.78)
                trigger_words.append("unless" if "unless" in lower else "except")

            # Collect other trigger words found
            for trigger in RULE_TRIGGERS:
                word = trigger.strip()
                if word in lower and word not in trigger_words:
                    trigger_words.append(word)

            rid = _stable_id(
                "RULE",
                f"{document.document_id}:{section.section_id}:{sentence}",
            )
            if rid in seen_ids:
                continue
            seen_ids.add(rid)

            rules.append(DocumentRule(
                rule_id=rid,
                document_id=document.document_id,
                section_id=section.section_id,
                block_id=f"sec-{section.section_id}",
                page_num=section.page_start,
                condition_text=condition,
                outcome_text=outcome,
                exception_text=exception,
                evidence_text=sentence,
                confidence=confidence,
                trigger_words=trigger_words[:10],
            ))

    return rules
