"""WS5c — Prompt library: versioned registry of every prompt in the pipeline.

Each prompt is registered with a name + version. Retrieval code asks for
`get_prompt("query_intent")` and gets the latest version; evaluations can pin
older versions for A/B comparison.
"""
from dataclasses import dataclass, field


@dataclass
class PromptTemplate:
    name: str
    version: str
    system: str
    template: str          # user-turn template; .format(**kwargs) at call time
    few_shots: list[dict] = field(default_factory=list)

    def render(self, **kwargs) -> str:
        shots = ""
        if self.few_shots:
            rendered = [
                f"<example>\nInput: {s['input']}\nOutput: {s['output']}\n</example>"
                for s in self.few_shots
            ]
            shots = "Examples:\n" + "\n".join(rendered) + "\n\n"
        return shots + self.template.format(**kwargs)


_REGISTRY: dict[str, dict[str, PromptTemplate]] = {}


def register(prompt: PromptTemplate) -> None:
    _REGISTRY.setdefault(prompt.name, {})[prompt.version] = prompt


def get_prompt(name: str, version: str | None = None) -> PromptTemplate:
    versions = _REGISTRY.get(name)
    if not versions:
        raise KeyError(f"Unknown prompt: {name}")
    if version:
        return versions[version]
    return versions[max(versions)]  # latest by version string


def list_prompts() -> dict[str, list[str]]:
    return {name: sorted(v.keys()) for name, v in _REGISTRY.items()}


# =====================================================================
# 1. Document taxonomy classification
# =====================================================================
register(PromptTemplate(
    name="taxonomy_classification",
    version="1.0",
    system=(
        "You are a document classifier for an Indian asset management company (AMC). "
        "You assign documents to nodes of a fixed 4-level taxonomy. A document may map "
        "to multiple taxonomy paths (multi-tagging), but only choose paths that are "
        "clearly supported by the content. Use exact paths from the provided taxonomy."
    ),
    template=(
        "Taxonomy (one path per line):\n{taxonomy_paths}\n\n"
        "Document filename: {filename}\n"
        "Document content (may be truncated):\n<document>\n{content}\n</document>\n\n"
        "Return the taxonomy paths this document belongs to, plus a document category."
    ),
    few_shots=[
        {
            "input": "Research_Note_AdaniPorts_Mar2026.docx — coverage update on Adani Ports, leverage, Bluechip and Infra Fund positions",
            "output": '{"taxonomy_paths": ["Research/Equity/Infrastructure/Coverage Notes", "Risk/Concentration Exposure/Issuer Group/Monitoring"], "category": "research_note"}',
        },
        {
            "input": "SEBI_Circular_ExitLoad_May2026.pdf — revision to exit load disclosure format, Schedule III",
            "output": '{"taxonomy_paths": ["Compliance/Regulatory Circulars/Exit Load/FY26"], "category": "regulatory_circular"}',
        },
    ],
))

# =====================================================================
# 2. Entity extraction (AMC-domain NER)
# =====================================================================
register(PromptTemplate(
    name="entity_extraction",
    version="1.0",
    system=(
        "You are a named-entity extractor for Indian asset management documents. "
        "Extract entities of exactly these types: Scheme (mutual fund schemes), "
        "Issuer (listed companies), IssuerGroup (conglomerates like 'Adani Group'), "
        "Analyst (internal analysts), Sector (e.g. NBFC, Infrastructure), "
        "RiskTheme (e.g. 'funding cost pressure', 'concentration risk'), "
        "RegulatoryCircular (SEBI circulars with references), "
        "ClauseType (e.g. 'exit load clause'). "
        "Extract the exact surface form as it appears, plus a normalized name. "
        "Do not invent entities that are not in the text."
    ),
    template=(
        "Extract all entities from this text:\n<text>\n{content}\n</text>\n\n"
        "Return entities with type, surface_form, normalized_name, and any properties "
        "you can read directly from the text (e.g. pct_nav for holdings, circular reference numbers)."
    ),
    few_shots=[
        {
            "input": "Infra Fund's Adani exposure (5.8%) is our highest among schemes but still well under the 10% cap.",
            "output": '{"entities": [{"type": "Scheme", "surface_form": "Infra Fund", "normalized_name": "NuSummit Infra Fund", "properties": {}}, {"type": "IssuerGroup", "surface_form": "Adani", "normalized_name": "Adani Group", "properties": {"exposure_pct": 5.8}}, {"type": "RiskTheme", "surface_form": "10% cap", "normalized_name": "Concentration Risk", "properties": {}}]}',
        },
    ],
))

# =====================================================================
# 3. Entity disambiguation
# =====================================================================
register(PromptTemplate(
    name="entity_disambiguation",
    version="1.0",
    system=(
        "You resolve an extracted entity mention to one of a list of known canonical "
        "entities, or decide it is a genuinely new entity. Prefer resolving to an "
        "existing entity when the mention plausibly refers to it."
    ),
    template=(
        "Mention: \"{mention}\" (type: {entity_type})\n"
        "Context: \"{context}\"\n\n"
        "Known candidates:\n{candidates}\n\n"
        "Return the entity_id of the best match, or null if this is a new entity."
    ),
))

# =====================================================================
# 4. Relationship extraction
# =====================================================================
register(PromptTemplate(
    name="relationship_extraction",
    version="1.0",
    system=(
        "You extract typed relationships between known entities from AMC documents. "
        "Allowed relationship types: HOLDS (Scheme->Issuer, props: pct_nav), "
        "ISSUED_BY (Issuer->IssuerGroup), IN_SECTOR (Issuer->Sector), "
        "MONITORED_FOR (IssuerGroup->RiskTheme), FLAGGED_IN (Issuer->RiskTheme), "
        "COVERS (Analyst->Issuer or Analyst->Sector), "
        "APPLIES_TO (RegulatoryCircular->ClauseType), "
        "AFFECTS (ClauseType->Scheme, props: status one of outdated|compliant|not_reviewed). "
        "Only extract relationships stated or directly implied by the text, between "
        "entities in the provided entity list."
    ),
    template=(
        "Known entities in this text:\n{entities}\n\n"
        "Text:\n<text>\n{content}\n</text>\n\n"
        "Return the relationships with source, target, type, properties, and a confidence 0-1."
    ),
    few_shots=[
        {
            "input": "Entities: [Scheme: NuSummit Infra Fund, Issuer: Adani Green Energy]. Text: 'Top Holdings: Adani Green Energy — 1.7%' (from Infra Fund SID)",
            "output": '{"relationships": [{"source": "NuSummit Infra Fund", "target": "Adani Green Energy", "type": "HOLDS", "properties": {"pct_nav": 1.7}, "confidence": 0.95}]}',
        },
    ],
))

# =====================================================================
# 5. Query intent classification
# =====================================================================
register(PromptTemplate(
    name="query_intent",
    version="1.0",
    system=(
        "You classify user queries against an AMC knowledge base into one query type "
        "and identify which entities and taxonomy branches are involved.\n"
        "Query types:\n"
        "- exposure_aggregation: aggregate holdings/exposure across schemes for an issuer or group\n"
        "- compliance_check: which schemes/documents are affected by a regulation or need updates\n"
        "- house_view_synthesis: summarize analyst opinions/views across many documents\n"
        "- entity_lookup: factual question about a single entity\n"
        "- general: anything else (falls back to plain semantic search)"
    ),
    template=(
        "Available taxonomy branches:\n{taxonomy_paths}\n\n"
        "Query: \"{query}\"\n\n"
        "Classify the query. List entity mentions exactly as they appear in the query."
    ),
    few_shots=[
        {
            "input": "What's our exposure to Adani Group across all schemes, and what's the latest risk commentary?",
            "output": '{"query_type": "exposure_aggregation", "entities_mentioned": ["Adani Group"], "taxonomy_paths": ["Risk/Concentration Exposure/Issuer Group"], "requires_graph": true, "requires_vector": true}',
        },
        {
            "input": "Which schemes need exit load disclosure updates after SEBI's latest circular?",
            "output": '{"query_type": "compliance_check", "entities_mentioned": ["exit load", "SEBI"], "taxonomy_paths": ["Compliance/Regulatory Circulars/Exit Load"], "requires_graph": true, "requires_vector": true}',
        },
        {
            "input": "Summarize our house view on NBFCs across all analyst notes this quarter",
            "output": '{"query_type": "house_view_synthesis", "entities_mentioned": ["NBFC"], "taxonomy_paths": ["Research/Sector/BFSI/NBFC"], "requires_graph": true, "requires_vector": true}',
        },
    ],
))

# =====================================================================
# 6. Synthesis with inline citations
# =====================================================================
register(PromptTemplate(
    name="synthesis",
    version="1.0",
    system=(
        "You are the answer synthesizer for NuSummit ContextGraph, an AMC knowledge "
        "assistant. You are given (a) STRUCTURED FACTS from a knowledge graph — these "
        "are verified and take precedence — and (b) supporting document excerpts.\n"
        "Rules:\n"
        "- Answer only from the provided context. If the context is insufficient, say so.\n"
        "- Cite sources inline with bracketed indices like [1], [2] matching the source list.\n"
        "- Every number (percentages, counts, dates) must come from a structured fact or "
        "an excerpt, with a citation.\n"
        "- When the query is about exposure or compliance, also return structured_rows "
        "(one row per scheme) for tabular display.\n"
        "- Note any compliance implication (e.g. SEBI limits) in compliance_note."
    ),
    template=(
        "Query: \"{query}\"\n\n"
        "{context}\n\n"
        "Synthesize the answer now."
    ),
))

# =====================================================================
# 7. Fallback / error prompts
# =====================================================================
register(PromptTemplate(
    name="fallback_no_context",
    version="1.0",
    system=(
        "You are an AMC knowledge assistant. The retrieval system found no relevant "
        "context for the user's query. Politely explain that the knowledge base has "
        "no matching documents, suggest 1-2 reformulations, and do NOT attempt to "
        "answer from general knowledge."
    ),
    template="Query: \"{query}\"\n\nRespond to the user.",
))

register(PromptTemplate(
    name="fallback_low_quality",
    version="1.0",
    system=(
        "You are an AMC knowledge assistant. Retrieval found only weakly-related "
        "context. Answer only what the context supports, clearly flag the low "
        "confidence, and list what additional documents would be needed."
    ),
    template="Query: \"{query}\"\n\n{context}\n\nAnswer with appropriate caveats.",
))
