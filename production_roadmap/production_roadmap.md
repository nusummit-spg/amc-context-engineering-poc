# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering Graph — Production Architecture & Harness Engineering Roadmap

## Executive Overview
This strategic architecture document establishes the blueprint for evolving the **AMC Context Engineering Graph (v2)** into an enterprise-grade, high-throughput, zero-hallucination compliance platform. It directly addresses product efficiency, advanced harness engineering, AWS cloud-native migration, production readiness, and spec-driven software delivery.

---

## 1. System & Runtime Product Efficiency

To maximize throughput, minimize token overhead, and maintain sub-second response SLAs, the following architectural optimizations are defined:

```
                          ┌──────────────────────────────────────┐
                          │    User Query / API Request          │
                          └──────────────────┬───────────────────┘
                                             │
                                  ┌──────────▼──────────┐
                                  │  Semantic Cache     │ ◄─── Cache Hit (<50ms)
                                  │ (Redis + FAISS HNSW)│
                                  └──────────┬──────────┘
                                             │ Cache Miss
                                  ┌──────────▼──────────┐
                                  │ Query Classifier &  │
                                  │ Hybrid Weight Router│
                                  └─────┬───────────┬───┘
                                        │           │
                 ┌──────────────────────┘           └──────────────────────┐
                 │ (Relational / Temporal)                 │ (Prose Similarity)
        ┌────────▼────────┐                               ┌────────▼────────┐
        │ AWS Neptune /   │                               │ OpenSearch      │
        │ Neo4j Graph RAG │                               │ Vector Search   │
        └────────┬────────┘                               └────────┬────────┘
                 │                                                 │
                 └──────────────────────┬──────────────────────────┘
                                        │
                             ┌──────────▼──────────┐
                             │ Reciprocal Rank     │
                             │ Fusion (RRF) &      │
                             │ Fact Compression    │
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │ Token-Optimized LLM │
                             │ Context Assembler   │
                             └─────────────────────┘
```

### A. Graph Traversal & Cypher Optimization
- **Compiled Parameterized Cypher Templates**: Replace dynamic string concatenation with pre-compiled Cypher queries to enable query plan caching in Neo4j/Neptune query engines.
- **Subgraph Projections & Minimal Hop Extraction**: Utilize APOC and Graph Data Science (GDS) projections to retrieve only 1-hop and 2-hop neighborhood subgraphs matching exact query entity constraints, eliminating unbounded graph scans.

### B. Reciprocal Rank Fusion (RRF) with Dynamic Weighting
- Implement adaptive score weighting based on query intent classification:
  $$Score(d) = \frac{w_{\text{graph}}}{60 + rank_{\text{graph}}(d)} + \frac{w_{\text{vector}}}{60 + rank_{\text{vector}}(d)}$$
  - **Temporal / Comparative Queries**: $w_{\text{graph}} = 0.85, w_{\text{vector}} = 0.15$
  - **Fact Lookup Queries**: $w_{\text{graph}} = 0.30, w_{\text{vector}} = 0.70$

### C. Context Compression & Deduplication
- **Triple Notation Compression**: Convert verbose graph output into micro-notation prior to prompt injection:
  - *Verbose*: `SchemeClass named Index Fund under 2026 regime is open ended tracking an index.`
  - *Compressed*: `[CURRENT_2026] SchemeClass:IndexFund(open_ended, tracks_index)`
- **Jaccard Chunk Deduplication**: Filter vector search results with $>0.75$ Jaccard overlap to eliminate redundancy before assembling the final prompt context window.

---

## 2. Harness Engineering & Context Lifecycle Management

Harness engineering ensures the LLM environment remains predictable, state-aware, and resistant to context degradation over long multi-turn sessions.

```
       ┌─────────────────────────────────────────────────────────────────┐
       │                    Harness Engine Core                          │
       ├─────────────────────────────────────────────────────────────────┤
       │  1. Context Rot Mitigation (Regime Boundary Isolator)           │
       │  2. Hierarchical Context Summarization (State Graph Compressor)  │
       │  3. Reflection & Guard Loops (Self-Correction verifier)         │
       └─────────────────────────────────────────────────────────────────┘
```

### A. Context Rot & Degradation Prevention
- **Regime Boundary Isolation**: Inject explicit System Anchors that strictly demarcate `LEGACY_2017` vs `CURRENT_2026` nodes. This prevents "context leaking" where legacy rules silently bias answers about amended circulars.
- **Decay Factor Weighting**: Apply an epoch-based decay factor $\gamma(t)$ to historical vector chunks:
  $$Score_{\text{final}} = Score_{\text{vector}} \times e^{-\lambda (t_{\text{current}} - t_{\text{circular}})}$$
  This ensures newly published SEBI circulars automatically supersede older guidance in vector relevance scoring.

### B. Context Summarization & Session Memory Layer
- **State Graph Memory Engine**: Rather than appending raw text turns into chat history (which inflates token usage and degrades attention), maintain a structured **Session State Graph** in Neo4j/Redis:
  - `(UserSession)-[:HAS_SELECTED_SCHEME]->(SchemeClass)`
  - `(UserSession)-[:ACTIVE_REGIME]->(RegulatoryRegime)`
- **Rolling Hierarchical Summarizer**: Compress past dialogue into structured state deltas, keeping prompt overhead under 150 tokens regardless of conversation depth.

### C. Loop Engineering & Autonomous Refinement
- **Self-Correction Verification Loop**:
  ```
  User Query ──► Retrieve & Generate ──► Constraint Verifier ──► [PASS] ──► Output
                                                 │
                                              [FAIL]
                                                 │
                                                 ▼
                                        Re-Query Expansion Loop
  ```
  If the generated response violates a known graph edge (e.g. claims two mutually exclusive schemes can coexist), the Harness catches the violation via Cypher assertion, appends a correction directive, and re-executes the generation step.
- **Bounded Exploration Loop**: Cap recursive graph traversal to $N \le 3$ hops to guarantee deterministic execution bounds.

---

## 3. Migration Architecture: AWS Bedrock & AWS Agent Core

To deploy as a cloud-native AWS enterprise application, the architecture migrates to AWS Bedrock and AWS Neptune Serverless.

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AWS Cloud Environment                                     │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                           │
│  ┌───────────────────────────┐       ┌─────────────────────────────────────────────────┐  │
│  │   Amazon API Gateway /    │       │         AWS Bedrock Agent Core                  │  │
│  │   Application Load Bal.   │──────►│  ┌──────────────────┐  ┌─────────────────────┐  │  │
│  └───────────────────────────┘       │  │ Classifier Agent │  │ Compliance Auditor  │  │  │
│                                      │  └────────┬─────────┘  └──────────▲──────────┘  │  │
│                                      └───────────┼───────────────────────┼─────────────┘  │
│                                                  │                       │                │
│                                      ┌───────────▼───────────────────────┴─────────────┐  │
│                                      │          Bedrock Action Groups                  │  │
│                                      │         (AWS Lambda Orchestration)              │  │
│                                      └───────────┬───────────────────────┬─────────────┘  │
│                                                  │                       │                │
│                                      ┌───────────▼──────────┐ ┌──────────▼──────────┐  │
│                                      │ Amazon Neptune       │ │ OpenSearch          │  │
│                                      │ Serverless (Graph)  │ │ Serverless (Vector) │  │
│                                      └──────────────────────┘ └─────────────────────┘  │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

### Migration Step-by-Step Blueprint

1. **Graph Storage Tier**: Migrate local Neo4j 5.x graph data to **Amazon Neptune Serverless** (openCypher / Gremlin endpoint) with auto-scaling Capacity Units (NCUs).
2. **Vector Index Tier**: Migrate FAISS local index to **Amazon OpenSearch Serverless (Vector Engine)** using HNSW indexing and k-NN search APIs.
3. **LLM Orchestration**: Replace direct Anthropic SDK calls with **Amazon Bedrock Converse API** (`anthropic.claude-3-5-haiku-20241022-v1:0`), backed by **Amazon Bedrock Guardrails** for PII filtering, refusal enforcement, and hallucination bounds.
4. **Agentic Orchestration (AWS Agent Core)**:
   - **Classifier Agent**: Classifies incoming query intent (Compliance, Categorization, Tax, Historical).
   - **Graph Action Group**: AWS Lambda executing openCypher queries on Amazon Neptune.
   - **Vector Action Group**: AWS Lambda querying OpenSearch Serverless.
   - **Compliance Audit Agent**: Cross-evaluates retrieved graph facts against LLM generated text before returning final JSON to the user.

---

## 4. Production-Grade Enterprise Requirements

To transition from Proof-of-Concept to Production Grade, the following non-functional infrastructure standards must be enforced:

| Dimension | Production Standard | Implementation Strategy |
|---|---|---|
| **Observability & Tracing** | Full Request Telemetry | OpenTelemetry instrumentation integrated with AWS X-Ray & Arize Phoenix for trace-level visibility into retrieval latency. |
| **Evaluation Benchmarking** | Continuous RAGAS Pipeline | Automated evaluation running RAGAS metrics (Faithfulness, Answer Relevance, Context Recall) on every build. |
| **Security & Authorization** | Attribute-Based Access Control (ABAC) | Graph node-level and edge-level security policies restricting access based on user role (e.g. PM vs Compliance Officer vs External Auditor). |
| **High Availability & Failover** | 99.95% Availability SLA | Multi-AZ deployment of Neptune, OpenSearch, and ECS container tasks with automated failover and health checks. |
| **Data Lineage & Audit Trails** | Immutable Regulatory Ledger | Write-once Audit Log in Amazon S3 Object Lock recording every query, graph edge traversed, and LLM prompt footprint. |

---

## 5. Spec-Driven Engineering (SDD) Framework

Spec-Driven Engineering ensures that all system behaviors, graph schemas, API contracts, and compliance rules are defined declaratively in version-controlled specifications before implementation.

```
       ┌─────────────────────────────────────────────────────────────┐
       │               Spec-Driven Development Pipeline               │
       ├─────────────────────────────────────────────────────────────┤
       │  1. OpenAPI 3.1 & AsyncAPI Contracts (Interface Spec)        │
       │  2. Declarative Cypher/Pydantic Ontology (Data Spec)         │
       │  3. Gherkin/BDD Executable Compliance Suite (Behavior Spec) │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
                                      ▼
                       Automated CI/CD Validation
```

### A. Interface Specification (OpenAPI 3.1)
All API endpoints must adhere strictly to versioned OpenAPI specs. Request payload schemas and response schemas are strictly validated via Pydantic v2 prior to execution:

```yaml
openapi: 3.1.0
info:
  title: AMC Context Engineering API
  version: 3.0.0
paths:
  /api/v3/query/contextgraph:
    post:
      summary: Dual-Regime Hybrid ContextGraph Query
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/QueryRequest'
      responses:
        '200':
          description: Grounded Compliance Response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QueryResponse'
```

### B. Ontology & Ingestion Specification
All Neo4j/Neptune entities and relationships are governed by a central YAML schema spec (`ontology_spec.v2.yaml`). During data ingestion, extracted entities that do not match the ontology spec are rejected automatically before graph insertion:

```yaml
version: 2.0
entities:
  SchemeClass:
    properties:
      code: { type: string, required: true }
      canonical_label: { type: string, required: true }
      regime_id: { type: string, enum: [LEGACY_2017, CURRENT_2026] }
  RegulatoryCircular:
    properties:
      circular_id: { type: string, required: true }
      effective_date: { type: date, required: true }

relationships:
  MUTUALLY_EXCLUSIVE_WITH:
    source: SchemeClass
    target: SchemeClass
  AMENDED_BY:
    source: RegulatoryCircular
    target: Amendment
```

### C. Executable Behavior Specifications (BDD / Gherkin)
Compliance verification tests are defined as executable Gherkin feature files that run in CI/CD pipeline test suites:

```gherkin
Feature: SEBI 2026 Dual-Regime Mutual Exclusion Enforcement

  Scenario: Large Cap and Index Fund Coexistence Validation
    Given an AMC managing an existing "Index Fund" under regime "CURRENT_2026"
    When the portfolio manager queries to launch a new "Large Cap Equity Scheme"
    Then the system must traverse edge "MUTUALLY_EXCLUSIVE_WITH"
    And return result "PASS" with exact overlap ceiling "50%"
    And the total prompt token footprint must not exceed 2,200 tokens
```

---

## 6. Implementation Roadmap & Milestones

```
Phase 1: Efficiency & Compression (Weeks 1-3)
  ├── Implement Cypher query parameter compilation
  ├── Integrate Reciprocal Rank Fusion (RRF)
  └── Deploy Triple Notation prompt compression

Phase 2: Harness & Lifecycle Management (Weeks 4-6)
  ├── Implement Session State Graph Memory
  ├── Build Dual-Regime Boundary Isolator
  └── Deploy Self-Correction Verification Loop

Phase 3: Spec-Driven CI/CD & Testing (Weeks 7-9)
  ├── Standardize OpenAPI 3.1 & Pydantic v2 schemas
  ├── Implement Ontology Spec Ingestion Validator
  └── Build Gherkin BDD compliance test suite

Phase 4: AWS Bedrock Cloud Migration (Weeks 10-14)
  ├── Migrate graph data to Amazon Neptune Serverless
  ├── Migrate FAISS to OpenSearch Serverless
  ├── Deploy Bedrock Agents & Guardrails
  └── Integrate OpenTelemetry tracing & RAGAS benchmarking
```
