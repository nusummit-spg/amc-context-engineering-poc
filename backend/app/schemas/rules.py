# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""DocumentRule schema — structured compliance rules extracted from document text.

Adapted from Agentic Testing Platform's Rule model.
Rules capture IF-THEN / WHEN / UNLESS conditions:
  IF entry_age > 60 THEN requires medical examination
  UNLESS sum_assured < 25 lakhs
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentRule(BaseModel):
    """A structured compliance rule extracted from a document section."""
    rule_id:         str     = Field(default_factory=lambda: str(uuid4()))
    document_id:     str
    section_id:      Optional[str] = None
    block_id:        str
    page_num:        Optional[int] = None
    
    # Compiled rule structure
    condition_text:  str            # The IF/WHEN condition
    outcome_text:    Optional[str]  = None   # The THEN outcome
    exception_text:  Optional[str]  = None   # The UNLESS/EXCEPT exception
    
    # Evidence
    evidence_text:   str
    confidence:      float  = Field(default=0.68, ge=0.0, le=1.0)
    
    # Rule trigger keywords found in text
    trigger_words:   list[str] = Field(default_factory=list)
