"""WS5a — Query intent, retrieval result, assembled context, and synthesis output schemas.

Unified with WS5a extended design:
  - QueryType gains no new values (their 5 types cover all live use cases)
  - QueryIntent gains confidence field and key_entities deduplication
  - ResolvedEntity added as typed replacement for the dict[str, str] resolved_entities
    (backwards-compatible: RetrievalResult keeps both forms)
  - GraphFact keeps statement + subject/predicate/object triple (their format, better for UI)
  - TraversalStrategy added as a typed schema with quota validators
  - TRAVERSAL_STRATEGIES registry maps QueryType → TraversalStrategy
  - AssembledContext keeps context_text (pre-formatted) + adds raw counts for debug UI
  - SynthesisOutput: confidence stays str ("high"/"medium"/"low") to match live LLM output
    schema — adding structured_rows and compliance_note already present in their code
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class QueryType(str, Enum):
    """Drives the traversal strategy (WS5d query-type → traversal-strategy mapper)."""
    EXPOSURE_AGGREGATION = "exposure_aggregation"   # "Adani exposure across all schemes"
    COMPLIANCE_CHECK     = "compliance_check"        # "which SIDs need updates after circular X"
    HOUSE_VIEW_SYNTHESIS = "house_view_synthesis"    # "summarize our view on NBFCs"
    ENTITY_LOOKUP        = "entity_lookup"           # single-entity factual question
    GENERAL              = "general"                 # fallback: pure vector search


class QueryIntent(BaseModel):
    """Output of the intent classifier (Step 1 of the retrieval flow).

    entities_mentioned: raw surface forms exactly as they appear in the query.
    taxonomy_paths:     slash-joined paths validated against the live taxonomy tree.
    confidence:         LLM's confidence in this classification [0,1].
    """
    query_type:        QueryType
    entities_mentioned: list[str] = Field(default_factory=list)
    taxonomy_paths:    list[str]  = Field(default_factory=list)
    requires_graph:    bool       = True
    requires_vector:   bool       = True
    confidence:        float      = Field(default=0.0, ge=0.0, le=1.0)
    reasoning:         Optional[str] = None

    @field_validator("entities_mentioned", mode="before")
    @classmethod
    def deduplicate_entities(cls, v: list[str]) -> list[str]:
        """Remove duplicate entity mentions (case-insensitive)."""
        seen: set[str] = set()
        result: list[str] = []
        for e in v:
            key = e.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(e.strip())
        return result


class ResolvedEntity(BaseModel):
    """Typed result of resolving one surface form to a canonical entity.

    Replaces the raw dict[str, str] for new code; RetrievalResult carries both
    forms for backwards compatibility.
    """
    surface_form:   str
    canonical_name: str
    entity_id:      Optional[str] = None    # UUID; None if entity not yet in graph
    entity_type:    Optional[str] = None    # EntityType value string
    method:         str           = "alias" # "alias" | "fuzzy" | "llm" | "new"
    confidence:     float         = Field(default=1.0, ge=0.0, le=1.0)
    is_provisional: bool          = False   # True if a new entity node was created


class GraphFact(BaseModel):
    """A structured fact returned by graph traversal.

    Prioritized over prose in context assembly (graph facts appear first in the prompt).
    Uses subject/predicate/object triple for UI graph highlighting.
    """
    fact_id:             str            = Field(default_factory=lambda: str(uuid4()))
    statement:           str            = Field(min_length=5, description="Human-readable fact sentence")
    subject:             str
    predicate:           str
    object:              str
    properties:          dict           = Field(default_factory=dict)
    source_document_ids: list[str]      = Field(default_factory=list)
    traversal_path:      Optional[str]  = None  # e.g. "Scheme→HOLDS→Issuer→ISSUED_BY→IssuerGroup"


class RetrievedChunk(BaseModel):
    """A vector-retrieved chunk from Qdrant, ranked by cosine similarity."""
    chunk_id:       str           = Field(min_length=1)
    document_id:    str
    document_title: Optional[str] = None
    text:           str
    score:          float         = Field(ge=0.0, le=1.0)
    taxonomy_paths: list[str]     = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """Combined output of graph traversal + scoped vector search (Steps 2–5).

    resolved_entities: dict form kept for backwards compatibility with existing code.
    resolved_entity_list: typed form for new code consuming this schema.
    """
    intent:                QueryIntent
    resolved_entities:     dict[str, str]        = Field(
        default_factory=dict,
        description="surface_form → canonical_name (backwards-compatible dict form)",
    )
    resolved_entity_list:  list[ResolvedEntity]  = Field(
        default_factory=list,
        description="Typed resolution results (preferred for new code)",
    )
    graph_facts:           list[GraphFact]        = Field(default_factory=list)
    chunks:                list[RetrievedChunk]   = Field(default_factory=list)
    traversal_paths:       list[str]              = Field(default_factory=list)
    cypher_queries_run:    list[str]              = Field(default_factory=list)


class SourceAttribution(BaseModel):
    """Source citation for the synthesis answer.
    source_index maps to inline [n] citation markers in the answer text.
    """
    source_index:   int
    document_id:    str
    document_title: str
    chunk_id:       Optional[str] = None
    snippet:        Optional[str] = None


class AssembledContext(BaseModel):
    """Output of the context engineering layer (WS5d, Step 6).

    context_text: the pre-formatted string passed directly to the synthesis prompt.
    traversal_explanation: list of human-readable path descriptions for the UI ontology panel.
    quality_score: heuristic 0–1 (graph fact density + top chunk scores).
    passed_quality_gate: False triggers a warning log; orchestrator may retry with fallback.
    """
    context_text:             str
    token_count:              int           = Field(ge=0)
    token_budget:             int           = Field(ge=0)
    structured_facts_included: int         = Field(default=0, ge=0)
    chunks_included:          int           = Field(default=0, ge=0)
    chunks_dropped:           int           = Field(default=0, ge=0)
    sources:                  list[SourceAttribution] = Field(default_factory=list)
    quality_score:            float         = Field(default=0.0, ge=0.0, le=1.0)
    passed_quality_gate:      bool          = True
    traversal_explanation:    list[str]     = Field(
        default_factory=list,
        description="Human-readable traversal path descriptions for the UI ontology panel",
    )

    @model_validator(mode="after")
    def token_count_within_budget(self) -> "AssembledContext":
        """token_count must not exceed token_budget."""
        if self.token_budget > 0 and self.token_count > self.token_budget:
            raise ValueError(
                f"token_count ({self.token_count}) exceeds token_budget ({self.token_budget}). "
                "ContextAssembler must trim content before constructing AssembledContext."
            )
        return self

    @property
    def utilization_pct(self) -> float:
        """Token budget utilization as a percentage."""
        if self.token_budget == 0:
            return 0.0
        return round((self.token_count / self.token_budget) * 100, 1)


class Citation(BaseModel):
    """Inline citation in the synthesis answer."""
    source_index:   int
    document_title: str


class SynthesisOutput(BaseModel):
    """WS5a — LLM output schema (Step 7).

    The synthesis prompt instructs the model to return this exact shape via
    structured outputs (output_config.format = json_schema).

    confidence is kept as str ("high"/"medium"/"low") to match the live LLM
    output schema — change this only if you update the synthesis prompt simultaneously.
    """
    answer:          str            = Field(min_length=5, description="Markdown answer with inline [n] citations")
    structured_rows: list[dict]     = Field(
        default_factory=list,
        description="Tabular facts for the answer card UI (one dict per scheme/issuer row)",
    )
    compliance_note: Optional[str]  = None
    citations:       list[Citation] = Field(default_factory=list)
    confidence:      str            = Field(
        default="high",
        description="LLM self-reported confidence: 'high' | 'medium' | 'low'",
    )
    has_gaps:        bool           = False
    gap_description: Optional[str] = None

    @model_validator(mode="after")
    def valid_confidence_level(self) -> "SynthesisOutput":
        allowed = {"high", "medium", "low"}
        if self.confidence not in allowed:
            raise ValueError(
                f"confidence must be one of {sorted(allowed)}, got '{self.confidence}'"
            )
        return self

    @model_validator(mode="after")
    def gap_description_when_has_gaps(self) -> "SynthesisOutput":
        if self.has_gaps and not self.gap_description:
            raise ValueError("gap_description must be provided when has_gaps=True")
        return self


# ── Traversal Strategy Registry (WS5d) ────────────────────────────────────────

class TraversalStrategy(BaseModel):
    """Retrieval parameters for a given QueryType.

    Token budget allocation: graph_fact_quota + vector_quota + system_reserve == 1.0
      graph_fact_quota × token_budget = tokens allocated to graph facts
      vector_quota × token_budget     = tokens allocated to vector passages
      system_reserve × token_budget   = reserved for prompt overhead + answer generation

    Stored here (not in retrieval code) so tuning is a schema change, not a code change.
    """
    cypher_template:  str   = Field(description="Key into the Cypher query library")
    max_hops:         int   = Field(ge=0, le=5, description="0 = no graph traversal (GENERAL type)")
    graph_fact_quota: float = Field(ge=0.0, le=1.0)
    vector_quota:     float = Field(ge=0.0, le=1.0)
    system_reserve:   float = Field(ge=0.0, le=1.0)
    qdrant_k:         int   = Field(ge=1, le=50)
    needs_aggregation: bool = False

    @model_validator(mode="after")
    def quotas_sum_to_one(self) -> "TraversalStrategy":
        total = self.graph_fact_quota + self.vector_quota + self.system_reserve
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"graph_fact_quota + vector_quota + system_reserve = {total:.3f}; must equal 1.0"
            )
        return self


TRAVERSAL_STRATEGIES: dict[QueryType, TraversalStrategy] = {

    QueryType.EXPOSURE_AGGREGATION: TraversalStrategy(
        cypher_template   = "GROUP_EXPOSURE",
        max_hops          = 2,       # Scheme → HOLDS → Issuer → ISSUED_BY → IssuerGroup
        graph_fact_quota  = 0.70,    # Answer lives in structured HOLDS facts
        vector_quota      = 0.20,
        system_reserve    = 0.10,
        qdrant_k          = 5,
        needs_aggregation = True,
    ),

    QueryType.COMPLIANCE_CHECK: TraversalStrategy(
        cypher_template   = "CIRCULAR_AFFECTED_SCHEMES",
        max_hops          = 3,       # Circular → APPLIES_TO → Clause → AFFECTS → Scheme
        graph_fact_quota  = 0.60,
        vector_quota      = 0.30,    # Circular text needed for context
        system_reserve    = 0.10,
        qdrant_k          = 8,
        needs_aggregation = False,
    ),

    QueryType.HOUSE_VIEW_SYNTHESIS: TraversalStrategy(
        cypher_template   = "SECTOR_COVERAGE",
        max_hops          = 2,       # Analyst → COVERS → Issuer → IN_SECTOR → Sector
        graph_fact_quota  = 0.35,
        vector_quota      = 0.55,    # Synthesis needs broad analyst note coverage
        system_reserve    = 0.10,
        qdrant_k          = 12,
        needs_aggregation = False,
    ),

    QueryType.ENTITY_LOOKUP: TraversalStrategy(
        cypher_template   = "ENTITY_FACTS",
        max_hops          = 1,       # 1-hop neighbourhood
        graph_fact_quota  = 0.50,
        vector_quota      = 0.40,
        system_reserve    = 0.10,
        qdrant_k          = 8,
        needs_aggregation = False,
    ),

    QueryType.GENERAL: TraversalStrategy(
        cypher_template   = "NOOP",  # no graph traversal
        max_hops          = 0,
        graph_fact_quota  = 0.00,
        vector_quota      = 0.90,    # Pure vector search
        system_reserve    = 0.10,
        qdrant_k          = 15,
        needs_aggregation = False,
    ),
}
"""
Registry mapping each QueryType to its TraversalStrategy.
GraphTraversal.traverse() looks up this dict in Step 3.
To tune retrieval behaviour: change the quota values here, not in retrieval code.
"""
