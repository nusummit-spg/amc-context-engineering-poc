# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""DocumentFact schema — typed numeric/range facts extracted from document text.

Adapted from Agentic Testing Platform's taxonomy.py Fact model.
Facts capture structured constraints:
  entry_age >= 18 years
  sum_assured between 1..50 lakhs
  exit_load <= 1%
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentFact(BaseModel):
    """A typed numeric or range fact extracted from a document.
    
    Subject-attribute-operator-value triple, e.g.:
      subject='entry_age', attribute='range', operator='between_inclusive',
      value='18..60', unit='years'
    
    This enables:
      - Boundary test generation (test at min-1, min, min+1, max-1, max, max+1)
      - Constraint validation queries
      - Cross-document variance detection
    """
    fact_id:       str     = Field(default_factory=lambda: str(uuid4()))
    document_id:   str
    section_id:    Optional[str] = None
    block_id:      str           # page/block reference for traceability
    page_num:      Optional[int] = None
    
    # Triple
    subject:       str           # canonical concept name, e.g. "entry_age"
    attribute:     str           # "numeric_value" | "range"
    operator:      str           # "=", ">=", "<=", ">", "<", "between_inclusive"
    value:         Union[str, float, int, None]  # "18..60" for ranges, float for scalars
    unit:          Optional[str] = None          # "years", "INR", "%", etc.
    
    # Range helpers (for between_inclusive facts)
    range_low:     Optional[float] = None
    range_high:    Optional[float] = None
    
    # Evidence
    evidence_text: str           # verbatim text block that produced this fact
    confidence:    float         = Field(default=0.93, ge=0.0, le=1.0)
    
    # Temporal validity (Phase 3 extension)
    valid_from:    Optional[str] = None   # ISO date string
    valid_to:      Optional[str] = None   # ISO date string
    
    # Qualifiers
    qualifiers:    dict[str, Any] = Field(default_factory=dict)
