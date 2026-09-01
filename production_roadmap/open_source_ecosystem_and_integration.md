# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Open Source Ecosystem & Integration Blueprint for AMC Context Engineering Graph

## Executive Overview

To build a production-grade AMC compliance platform without reinventing foundational components, this blueprint evaluates and selects top **battle-tested, open-source GitHub repositories and frameworks**. 

Each recommended library is evaluated based on **license compatibility** (MIT/Apache 2.0), **community adoption (stars, active commits)**, **relevance to financial compliance**, and **architectural fit with our v2 Dual-Regime stack**.

---

## 1. Top Recommended Open-Source Repositories Matrix

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                           Recommended Open-Source AI Stack                                │
├───────────────────────────┬───────────────────────────┬───────────────────────────────────┤
│ 1. Graph Engines & RAG    │ 2. Spec-Driven & Extraction│ 3. Observability & Evaluation     │
│  • neo4j/neo4j-graphrag   │  • instructor-ai/instructor│  • explodinggradients/ragas        │
│  • getzep/graphiti        │  • pydantic/logfire       │  • Arize-ai/phoenix               │
│  • run-llama/llama_index  │  • urchade/gliner         │  • truera/trulens                 │
└───────────────────────────┴───────────────────────────┴───────────────────────────────────┘
```

| Domain | Repository / Library | License | GitHub Stars | Architecture Role & Integration |
|---|---|---|---|---|
| **GraphRAG Engine** | [`neo4j/neo4j-graphrag`](https://github.com/neo4j/neo4j-graphrag) | Apache-2.0 | High (Official) | **Primary Graph Retriever**. Provides native PyPI `neo4j-graphrag` bindings for HNSW vector + openCypher hybrid retrieval. |
| **Temporal Graph** | [`getzep/graphiti`](https://github.com/getzep/graphiti) | Apache-2.0 | ~3.5k+ | **Temporal Graph Memory Engine**. Dynamically adds time-aware valid-from/valid-to edges for SEBI circular amendment tracking. |
| **Global Context RAG**| [`microsoft/graphrag`](https://github.com/microsoft/graphrag) | MIT | ~18k+ | **Community Clustering**. Generates hierarchical graph community summaries (Leiden clustering) for macro-compliance reports. |
| **Property Graph RAG**| [`run-llama/llama_index`](https://github.com/run-llama/llama_index) | MIT | ~36k+ | **Property Graph Abstraction**. Use `PropertyGraphIndex` for flexible node-edge extraction with Neo4j backends. |
| **Spec Validation** | [`instructor-ai/instructor`](https://github.com/instructor-ai/instructor) | MIT | ~7.5k+ | **Structured Output Enforcer**. Wraps Anthropic/OpenAI SDKs with Pydantic v2 schemas for guaranteed JSON output structure. |
| **Tracing & Specs** | [`pydantic/logfire`](https://github.com/pydantic/logfire) | Apache-2.0 | ~2.8k+ | **OpenTelemetry Spec Engine**. Provides OpenTelemetry tracing and schema validation across the full Python RAG pipeline. |
| **Zero-Shot NER** | [`urchade/gliner`](https://github.com/urchade/gliner) | Apache-2.0 | ~4.2k+ | **Ontology Extraction Engine**. Small bidirectional transformer for zero-shot Named Entity Recognition without fine-tuning. |
| **RAG Evaluation** | [`explodinggradients/ragas`](https://github.com/explodinggradients/ragas) | Apache-2.0 | ~5.8k+ | **RAG Evaluation Benchmark**. Industry standard for Faithfulness, Answer Relevance, and Context Recall metrics. |
| **AI Observability** | [`Arize-ai/phoenix`](https://github.com/Arize-ai/phoenix) | Apache-2.0 | ~4.1k+ | **Local & Cloud Observability**. Visual tracing of vector search, graph traversals, and prompt contexts in a local UI. |

---

## 2. Component-by-Component Technical Integration Guide

### 2.1 GraphRAG Engine: `neo4j-graphrag` (Official Neo4j Integration)

Instead of maintaining custom Cypher formatting scripts, integrate the official `neo4j-graphrag` Python library:

```python
# Installation: pip install neo4j-graphrag
from neo4j import GraphDatabase
from neo4j_graphrag.retrievers import HybridRetriever
from neo4j_graphrag.embeddings import SentenceTransformerEmbeddings

# Initialize connection pool & embedder
driver = GraphDatabase.driver("bolt://localhost:7688", auth=("neo4j", "contextgraph"))
embedder = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

# Production Hybrid Retriever (Vector + Cypher Edge Traversal)
retriever = HybridRetriever(
    driver=driver,
    vector_index_name="tax_scheme_vector",
    embedder=embedder,
    return_properties=["code", "canonical_label", "investment_mandate", "regime_id"]
)

# Execute hybrid search with score threshold
results = retriever.search(query="Solution Oriented Schemes 2026", top_k=3)
```

---

### 2.2 Spec-Driven Structured Output: `instructor` (Pydantic Validation)

To guarantee that the LLM returns typed, valid JSON matching our OpenAPI spec:

```python
# Installation: pip install instructor anthropic
import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field

client = instructor.from_anthropic(Anthropic())

class SchemeComplianceResult(BaseModel):
    scheme_code: str = Field(description="SEBI scheme code e.g. SC_INDEX")
    is_compliant: bool = Field(description="True if scheme meets 2026 rules")
    violating_clause: str | None = Field(default=None, description="Clause reference if non-compliant")
    confidence_score: float = Field(ge=0.0, le=1.0)

# Guaranteed Pydantic object output with automatic retry on ValidationError
resp: SchemeComplianceResult = client.messages.create(
    model="claude-3-5-haiku-20241022",
    response_model=SchemeComplianceResult,
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}]
)
```

---

### 2.3 Temporal Graph Engine: `graphiti` (Dynamic Time-Aware Edges)

For tracking regulatory circular amendments over time:

```python
# Installation: pip install graphiti-core
from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode, RelationEdge

graphiti = Graphiti("bolt://localhost:7688", "neo4j", "contextgraph")

# Add time-aware regulatory amendment edge
graphiti.add_edge(
    source=EntityNode(name="SEBI Circular 2017"),
    target=EntityNode(name="SEBI Circular 2026"),
    relation="AMENDED_BY",
    valid_from="2026-02-26"
)
```

---

### 2.4 Evaluation & Observability: `ragas` + `phoenix`

Automate continuous CI/CD evaluation of compliance answers:

```python
# Installation: pip install ragas phoenix-arize
import phoenix as px
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevance, context_precision

# Launch local Phoenix tracing dashboard at http://localhost:6006
session = px.launch_app()

# Run RAGAS metric evaluation dataset
eval_dataset = {
    "question": ["Can an AMC run two equity schemes under 2026 rules?"],
    "contexts": [["SchemeClass [CURRENT_2026] 'Index Fund'..."]],
    "answer": ["No, clause 2.6.3.16 enforces mutual exclusion..."]
}

results = evaluate(
    dataset=eval_dataset,
    metrics=[faithfulness, answer_relevance, context_precision]
)
print("RAGAS Scorecard:", results)
```

---

## 3. Production Architecture Integration Stack

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                              AMC ContextGraph Open Source Stack                           │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                           │
│  [ Client API ] ──► FastAPI (Validated via Pydantic v2 & OpenAPI 3.1)                      │
│                           │                                                               │
│                           ▼                                                               │
│  [ Observability ] ──► Pydantic Logfire / Arize Phoenix (OpenTelemetry Spans)             │
│                           │                                                               │
│                           ▼                                                               │
│  [ Harness Layer ] ──► Instructor (Spec-Driven Pydantic Validation & Retry Loops)          │
│                           │                                                               │
│            ┌──────────────┴──────────────┐                                                │
│            │                             │                                                │
│            ▼                             ▼                                                │
│  [ Graph Retriever ]           [ Vector Retriever ]                                       │
│   neo4j-graphrag / Graphiti     FAISS HNSW / Qdrant                                       │
│   (Neptune / Neo4j 5.x)         (384d Cosine Index)                                       │
│            │                             │                                                │
│            └──────────────┬──────────────┘                                                │
│                           │                                                               │
│                           ▼                                                               │
│  [ Evaluation CI/CD ] ──► RAGAS (Faithfulness & Context Precision Metrics)                 │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Recommended Adoption Path for AMC Team

1. **Step 1: Replace Custom Neo4j Glue Code**: Replace ad-hoc Cypher execution in `taxonomy_retrieval.py` with `neo4j-graphrag` `HybridRetriever`.
2. **Step 2: Add Type Safety & Guard Loops**: Adopt `instructor` for LLM generation to guarantee validated Pydantic outputs and automatic retry loops.
3. **Step 3: Embed Automated Evaluation**: Integrate `ragas` into GitHub Actions CI/CD to evaluate answer quality automatically on every pull request.
4. **Step 4: Enable OpenTelemetry Tracing**: Add `pydantic-logfire` or `arize-phoenix` for zero-overhead local and cloud request tracing.
