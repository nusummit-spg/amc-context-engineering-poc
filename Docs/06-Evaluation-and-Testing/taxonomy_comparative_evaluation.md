# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Taxonomy Extraction & Chunking — Comparative Evaluation

**Projects under review:**
- **Spark Testing Tool** (`spark-testing-tool-main`) — faiss_store.py, generation.py
- **Agentic Testing Platform** (`agentic_testing_platform`) — taxonomy.py, gemini_extractor.py
- **Context-Engineering** (`context-engineering`) — chunker.py, entities.py

---

## Executive Summary

| Dimension | Spark Tool | Agentic Platform | Context-Engineering |
|---|---|---|---|
| Extraction Primary | Gemini Multimodal (Vertex / Direct) | Gemini Multimodal + pdfplumber fallback | LLM-structured NER per section |
| Chunking Strategy | Parent-Child (1200c / 250c) sentence-aware | Line-level blocks, section-aware | Heading-aware clause-boundary split (~400 tokens) |
| Taxonomy Model | LLM-prompted JSON (3-layer: metadata/features/constraints) | Deterministic ontology + graph (12 categories) | AMC-domain typed entity graph (Neo4j) |
| Relation Extraction | FAISS vector similarity only | Dict rules + embedding candidates + ambiguity flags | Rule-based regex + LLM-structured JSON (constrained schema) |
| Graph Backend | FAISS flat index | NetworkX in-memory + JSON export | Neo4j + parameterized Cypher |
| Confidence Scoring | None (implicit) | Per-fact/rule/relation explicit (0.68-0.98) | Per-relation extraction method tagging |
| Cross-doc Resolution | None | Federation layer (concept alignment + variance detection) | SAME_AS embedding edges (cosine >= 0.90) |
| LLM Gate Policy | Always on (full doc) | Evidence-packet only (ambiguity-gated) | Per-section structured JSON |
| Test Case Generation | Coverage-query FAISS + LLM prompt | Deterministic generators + LLM scenario packets | N/A (retrieval / QA focused) |
| Domain Pack | Hardcoded SBI Life brochures | YAML domain pack (swappable by env var) | AMC/SEBI seed JSON |

---

## Deep-Dive: Each System

### Spark Testing Tool

**Extraction Architecture**
The core extraction lives in `faiss_store.py`. It is a **Gemini-primary, 4-pass local fallback** pipeline:

1. Gemini-2.5-pro (Vertex AI): renders each PDF page to 150 DPI PNG, sends full-page image to Gemini with a richly engineered prompt
2. Fallback: PyMuPDF prose + `find_tables()` markdown + EasyOCR (embedded images) + full-page OCR if total chars < 150 threshold

**Chunking Strategy - Parent-Child**

```
Parent: ~1200 chars + 150 overlap   (what the LLM reads as context)
Child : ~250  chars + 50 overlap    (what gets embedded and searched)
Both split ONLY at sentence boundaries (Unicode-aware regex)
Table rows are treated as atomic units - never broken mid-row
Hard-split safety net at 1.5x target for oversized tables
```

This is the most sophisticated raw chunking logic of the three systems. The sentence-boundary regex covers Hindi Unicode ranges and handles markdown table pipes, which neither of the other two projects do.

**Taxonomy**
Taxonomy is not a first-class code object - it lives entirely in prompts:
- `Prompt_1_Taxonomy_Generation.md` defines a 3-layer JSON structure: metadata, feature definitions, constraint specifications
- Constraints include formal edge cases: `if age < [min] REJECT`, premium multiples, channel-specific eligibility
- This is **LLM-generated taxonomy** - no code enforces the schema; the LLM writes it

**What is strong:**
The prompt architecture is extremely well-designed for insurance-specific constraint extraction. The `_COVERAGE_QUERIES` list in `generation.py` explicitly samples 7 semantic dimensions across products:

```
"premium calculation formula eligibility age sum assured benefit"
"exclusion clause waiting period lapse revival surrender value"
"claim settlement process documents required death benefit payout"
"rider add-on optional benefit premium waiver accidental disability"
"maturity benefit bonus loyalty addition guaranteed return"
"tax benefit section 80C 10(10D) GST deduction exemption"
"free-look period grace period policy term payment mode"
```

This **multi-dimension coverage sampling** strategy ensures the retrieval context represents different parts of the product taxonomy.

**What is weak:**
- Taxonomy has no in-code schema validation - entirely LLM-dependent
- No confidence scores anywhere
- No cross-document comparison or variance detection
- No graph - facts are not linked, just chunked and indexed

---

### Agentic Testing Platform

**Extraction Architecture**
A fully engineered **deterministic-first pipeline** in `taxonomy.py`:

```
Document -> read_pdf/docx/xlsx -> Block list
         -> extract_entities (regex, domain seed)
         -> extract_facts (NUMBER_UNIT_RE + RANGE_RE, nearest-subject binding)
         -> extract_rules (RULE_TRIGGERS + IF-THEN/WHEN compilation)
         -> deterministic_relations (domain schema rules)
         -> semantic_relations (embedding cosine, candidates only)
         -> build_taxonomy (12 TAXONOMY_ROOTS)
         -> build_graph (NetworkX MultiDiGraph)
         -> quality_report + LLM gate
```

**Chunking Strategy**
Unlike Spark, chunking here is **block-level** (line-by-line from PDF pages). Each block is a raw line, classified as paragraph or table. The `gemini_extractor.py` adds `_split_into_blocks()` that does word-count-aware splitting at sentence ends (~400 chars). This is weaker than Spark's parent-child hierarchy.

**Taxonomy Model - Most Advanced**
The taxonomy is a first-class typed object graph:
- **12 TAXONOMY_ROOTS**: `PRODUCT_OBJECT`, `PROCESS_OBJECT`, `ROLE`, `MONEY_CONCEPT`, `DURATION`, `ELIGIBILITY`, `BENEFIT`, `SERVICING`, `POLICY_STATE`, `PROCESS`, `UNDERWRITING`, `EXCEPTION`
- Each `TaxonomyNode` carries `entity_refs`, `fact_refs`, `rule_refs`, `source_document` - fully traceable
- **Fact model** includes operator (>=, <=, between_inclusive), unit, subject-binding confidence, scale normalization (lakh/crore/million)
- **Rule model** compiles IF...THEN, WHEN..., UNLESS/EXCEPT patterns with explicit condition + outcome + exception fields

**Entity Extraction**
`extract_entities()` uses word-boundary regex with canonical name + alias matching. Confidence = 0.98 for canonical match, 0.92 for alias match. Stable SHA-1 IDs prevent duplicate creation.

The `rich_entity_extractor.py` adds domain-specific extractors:
- `extract_regulations()` - Insurance Act / IRDAI patterns
- `extract_illustrations()` - Mr./Mrs. names near tables => illustration test cases
- `extract_contact_points()` - phone/email/website/SMS
- `extract_keywords()` - bold markdown text + known insurance keywords

**Confidence and Ambiguity System - Unique**
This is the only project with an explicit quality gate:
- `detect_conflicts()` - flags same (subject, attribute, unit) with different values -> high priority
- `detect_low_confidence()` - rules < 0.80, unbound numeric facts -> flagged as ambiguities
- `quality_report()` - returns `represented_block_ratio`, `rule_resolution_ratio`, `llm_gate.eligible_for_llm`
- **LLM is invoked ONLY for ambiguity packets**, never for full-document prompting

**Federation Layer**
`federation.py` aligns concepts across multiple documents:
- `align_concepts()` - groups by (label, node_type) => FederatedConcept with multiple occurrences
- `detect_context_variances()` - flags when same concept has different fact values across documents
- `compose_cross_document_tests()` - generates cross-product test cases from variances

**What is strong:**
Deterministic-first philosophy means taxonomy quality is auditable and reproducible. Domain pack is a YAML file, not hardcoded. The 3-mode architecture (Deterministic/Semi-agentic/Agentic) gives full control over cost vs quality. Plugin registry allows custom extractors, embedding backends, and LLM providers.

**What is weak:**
- Block-level chunking is coarser than Spark's parent-child hierarchy
- No Neo4j persistence - graph is in-memory NetworkX, harder to query at scale
- No section-by-section LLM extraction

---

### Context-Engineering

**Extraction Architecture**
Pure LLM-based NER via structured JSON schema per document section in `entities.py`:

```
Document -> section iteration
         -> LLM.complete_structured(entity_extraction prompt, _EXTRACTION_SCHEMA)
         -> dedup by (type, normalized_name)
```

Entities: Scheme, Issuer, IssuerGroup, Analyst, Sector, RiskTheme, RegulatoryCircular, ClauseType, Document, TableFact, FinancialMetric, ESGMetric, ComplianceRule, Penalty, Clause, Section

**Chunking Strategy - Most Principled**
`chunker.py` has the cleanest chunk architecture:
1. Never crosses section (heading) boundaries
2. Tries **clause-boundary splits first** (`\n3.1`, `\nA.`, `\n(1)`, `\n(a)`) - perfect for numbered regulatory/insurance text
3. Falls back to sentence splits
4. Keeps [TABLE] blocks as standalone atomic chunks
5. Prepends [Document Title - Section Title] header to every chunk for retrieval context

This is the best-engineered chunker for compliance/regulatory documents with numbered clauses.

**Relationship Extraction - Hybrid Design**
`relationships.py` has the cleanest rule-first, LLM-second architecture:
- Rule-based: `_HOLDING_LINE_RE` (issuer - pct% lines), `_STATUS_RE` (Scheme/Status compliance rows)
- LLM-assisted: constrained to a fixed ontology schema {HOLDS, ISSUED_BY, IN_SECTOR, MONITORED_FOR, FLAGGED_IN, COVERS, APPLIES_TO, AFFECTS} - LLM cannot hallucinate new relation types
- Deduplication against already-extracted rule-based results before LLM call

**Entity Resolution - 3-tier**
`resolver.py` uses:
1. Exact / alias index match (O(1) dict lookup)
2. Fuzzy containment: alias in surface or surface in alias
3. LLM disambiguation for genuine conflicts, constrained to candidates of the correct type

Entity learns new aliases from LLM resolutions, updating the index in-place.

**Graph Backend - Neo4j with Cypher Library**
`cypher_library.py` has 15 parameterized query templates covering:
- Group exposure aggregation across schemes
- Regulatory circular to clause type to scheme compliance chains
- Temporal queries (effective_date / valid_to)
- ESG metrics, financial facts, cross-document SAME_AS resolution

This is the only project that can answer **temporal and multi-hop graph queries** out of the box.

**Cross-Document Resolution**
`cross_doc_resolver.py` uses embedding cosine >= 0.90 + exact case-insensitive match to create SAME_AS edges in Neo4j, enabling entity deduplication across documents.

**What is strong:**
Cleanest section-aware chunker. Best graph persistence (Neo4j). LLM constraints prevent hallucination in relationship extraction. Section-level extraction keeps prompts tight.

**What is weak:**
- No confidence scores on entities or facts
- No rule extraction (IF-THEN conditions)
- No numeric fact binding (does not extract `premium >= 50000`)
- No test-case generation layer
- Domain is hardcoded (AMC/SEBI) - no swappable domain pack

---

## Technique Comparison Matrix

| Technique | Spark | Agentic Platform | Context-Engineering |
|---|:---:|:---:|:---:|
| Gemini multimodal page extraction | YES Primary | YES Optional | NO |
| EasyOCR for embedded images | YES | NO | NO |
| Sentence-boundary aware chunking | YES Advanced | PARTIAL Basic | YES Clause-aware |
| Parent-Child chunk hierarchy | YES | NO | NO |
| Multilingual chunking (Hindi/Devanagari) | YES | NO | NO |
| Typed ontology (domain seed) | NO LLM-only | YES YAML pack | YES JSON seed |
| Numeric fact extraction (regex) | NO | YES | NO |
| Range extraction (30-60 years) | NO | YES | NO |
| Rule compilation (IF-THEN) | NO | YES | NO |
| Confidence scoring | NO | YES per artifact | NO |
| Ambiguity detection and flagging | NO | YES | NO |
| LLM gate policy (evidence-packet) | NO | YES | PARTIAL Per-section |
| Entity alias resolution | PARTIAL FAISS only | YES regex + dict | YES 3-tier |
| Cross-document federation | NO | YES Concept alignment | YES SAME_AS edges |
| Graph persistence | FAISS | NetworkX in-memory | Neo4j |
| Graph query patterns (Cypher) | NO | NO | YES 15 templates |
| Temporal queries | NO | NO | YES |
| Test case generation | YES | YES Deterministic | NO |
| Coverage map tracking | YES | YES | NO |
| Plugin/extension system | NO | YES | NO |

---

## What to Adopt into Context-Engineering

### From Spark - High Priority Adoptions

#### 1. Parent-Child Chunk Hierarchy
**Current gap:** Context-engineering uses single-level chunks.
**Adopt:** Spark's `build_parent_child_chunks()` model - parent ~1200c for LLM context, child ~250c for vector search. Child stores `parent_id` so retrieval can return the full contextual window.
- Impact: retrieval precision up, LLM context quality up
- Effort: medium - add `parent_id` to Chunk schema, update chunker.py

#### 2. Multi-Dimension Coverage Query Sampling
**Current gap:** Context-engineering does not systematically ensure coverage across all taxonomy dimensions during retrieval.
**Adopt:** The `_COVERAGE_QUERIES` list - 7 semantic queries that sample different product/document dimensions (eligibility, exclusions, claims, riders, maturity, tax, policy lifecycle). Run these as batch retrievals when building context for any taxonomy-related prompt.
- Impact: taxonomy completeness up significantly
- Effort: low - add as a retrieval utility

#### 3. Multilingual Sentence Boundary Regex
**Current gap:** If the system processes Hindi/regional language documents, the current chunker will break.
**Adopt:** Spark's Unicode-aware `sentence_pattern` covering Devanagari, Bengali, Gujarati Unicode ranges in the sentence splitter.
- Impact: multilingual document support
- Effort: low - one regex update in chunker.py

---

### From Agentic Platform - Structural Adoptions

#### 4. Deterministic Numeric Fact Extraction
**Current gap:** Context-engineering extracts entity types (Scheme, Issuer) but not facts like `entry age >= 18`, `sum assured <= 5 crore`.
**Adopt:** The `NUMBER_UNIT_RE` + `RANGE_RE` + `_nearest_subject()` pipeline from `taxonomy.py`. This turns raw text like "Minimum entry age: 18 years" into a typed Fact: subject=entry_age, operator=>=, value=18, unit=years.
- Impact: enables boundary test generation, constraint validation
- Effort: high - new extraction module + Fact schema + Neo4j FinancialFact nodes already exist, extend them

#### 5. Rule Extraction (IF-THEN/UNLESS/WHEN Compilation)
**Current gap:** Context-engineering captures `ComplianceRule` entities as strings but does not parse condition + outcome structure.
**Adopt:** `extract_rules()` from `taxonomy.py` - the `RULE_TRIGGERS` list + IF...THEN, WHEN..., UNLESS patterns. Add condition_text, outcome_text, exception_text to rule entities.
- Impact: structured compliance rule testing, edge-case test generation
- Effort: medium - extend existing ComplianceRule entity schema

#### 6. Explicit Confidence Scoring + LLM Ambiguity Gate
**Current gap:** Context-engineering has no confidence on extracted entities, no quality gate before LLM calls.
**Adopt:**
- Per-entity/relation confidence scores (0.68-0.98)
- `detect_conflicts()` to flag same-entity, same-attribute contradictions across sections/documents
- `quality_report()` with `represented_block_ratio` - tells you how much of the document was actually covered
- LLM call only when `ambiguity_count > 0 AND priority == high` - saves tokens on clean documents
- Impact: cost reduction up, extraction reliability up, auditability up
- Effort: medium

#### 7. Rich Entity Extractor Patterns
**Current gap:** Context-engineering does not extract regulatory citations, contact points, or illustration examples.
**Adopt:**
- `extract_regulations()` - Insurance Act 1938 Section X, IRDAI Regulation citations => link to `RegulatoryCircular` in graph
- `extract_illustrations()` - "Mr. Rajesh, age 35" near table => creates illustration test personas
- `extract_contact_points()` - phone, email, website => enriches Document node properties
- Impact: richer graph topology, better coverage of regulatory citations
- Effort: low - drop-in module, regex only

#### 8. Federation-Layer Concept Variance Detection
**Current gap:** Context-engineering creates SAME_AS edges but does not detect value conflicts (e.g., two documents with different entry_age_max for the same product).
**Adopt:** `detect_context_variances()` from `federation.py` - when the same concept has different numeric facts across documents, classify as document_specific_variance vs possible_conflict vs scope_difference. Store as a separate ContextVariance node in Neo4j.
- Impact: critical for regulatory compliance - catches conflicting specs
- Effort: medium - new Neo4j node type, extend cross_doc_resolver.py

#### 9. Domain Pack (YAML-based, Swappable)
**Current gap:** Context-engineering has AMC-specific seed JSON hardcoded in the resolver. Adding a new domain (insurance, banking) requires code changes.
**Adopt:** The `DOMAIN_PACK_PATH` environment variable pattern - load canonical concepts, aliases, and schema-level relations from a YAML file. One domain pack for AMC, one for insurance, one for banking.
- Impact: system reusability across domains
- Effort: low-medium - refactor seed loading to read from YAML

---

## Industry-Grade Taxonomy - What's Still Missing in All Three

### 1. Section-Hierarchy Preservation
None of the systems preserve the full heading tree (H1 > H2 > H3) as a node in the taxonomy. Industry-grade systems need section provenance chains: Benefits > Death Benefit > Accidental Death Benefit Rider > Exclusions.

**Recommendation:** Add a `SectionNode` to the taxonomy that captures the heading hierarchy as a tree, linking facts and rules to their section path.

### 2. Temporal Validity on Facts
Only Context-Engineering has temporal query templates (effective_date / valid_to), but none of the systems extract temporal qualifiers from the document text itself - e.g., "effective from 1 April 2025", "applicable for policies issued after UIN X".

**Recommendation:** Extend fact extraction to capture `valid_from`, `valid_to`, `effective_date` qualifiers using date-pattern regex and bind them to facts.

### 3. Structured Test Case Traceability Matrix
Spark and Agentic Platform generate test cases, but neither produces a **bidirectional traceability matrix** (test case -> taxonomy node -> document section -> page/block). This is required for insurance/regulatory audit.

**Recommendation:** Every test case should carry a source_chain: test_case_id -> taxonomy_node -> fact/rule id -> block_id -> page_no -> document_id.

### 4. SEBI/IRDAI Circular Cross-Reference
None of the systems link extracted clauses to their authoritative regulatory circulars by regulatory reference number (e.g., "IRDAI/LIFE/CIR/2024/012"). Context-Engineering has `RegulatoryCircular` as a node, but ingestion does not extract citation numbers.

---

## Adoption Roadmap

### Phase 1 - Immediate, High ROI

| ID | Technique | Source | Effort |
|---|---|---|---|
| A | Parent-Child chunk hierarchy | Spark | Medium |
| B | Multi-dimension coverage queries | Spark | Low |
| C | Confidence scoring per entity/relation | Agentic Platform | Medium |
| D | Ambiguity detection + LLM gate | Agentic Platform | Medium |

### Phase 2 - Next Sprint, Structural

| ID | Technique | Source | Effort |
|---|---|---|---|
| E | Numeric fact extraction (NUMBER_UNIT_RE) | Agentic Platform | High |
| F | Rule compilation (IF-THEN/UNLESS) | Agentic Platform | Medium |
| G | Rich entity extractor (regs, contacts, illustrations) | Agentic Platform | Low |
| H | Domain pack YAML (swappable ontology) | Agentic Platform | Medium |

### Phase 3 - Industry-Grade Completion

| ID | Technique | Source | Effort |
|---|---|---|---|
| I | Federation variance detection | Agentic Platform | Medium |
| J | Section hierarchy tree in taxonomy | New design | High |
| K | Temporal validity on facts | New design | Medium |
| L | Traceability matrix (test -> doc) | New design | High |
| M | Multilingual chunking (Devanagari) | Spark | Low |

---

## Final Verdict

**Agentic Platform is architecturally the most sound** - deterministic-first, LLM-gated, fully traceable, domain-pluggable. It is the closest to industry-grade taxonomy.

**Spark Tool has the best extraction primitives** - parent-child chunking, Gemini multimodal, multilingual sentence-boundary handling, and coverage-query sampling are all production-quality techniques that should be brought into context-engineering.

**Context-Engineering has the best persistence and query layer** - Neo4j + parameterized Cypher + temporal queries + cross-doc SAME_AS resolution is the right graph foundation. It just needs the upstream extraction and taxonomy machinery from the other two projects.

**The ideal combined architecture:**

```
Gemini multimodal extraction (Spark)
    |
    v
Clause-aware + parent-child chunking (Spark + Context-Eng hybrid)
    |
    v
Domain-pack entity detection + numeric/rule extraction (Agentic Platform)
    |
    v
Confidence-scored taxonomy + ambiguity-gated LLM (Agentic Platform)
    |
    v
Federation + variance detection (Agentic Platform)
    |
    v
Neo4j + temporal Cypher library (Context-Engineering)
    |
    v
Deterministic test generators + coverage matrix (Agentic Platform)
```
