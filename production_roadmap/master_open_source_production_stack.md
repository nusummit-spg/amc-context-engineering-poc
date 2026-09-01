# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Master Open-Source Production Stack & Technology Map for Enterprise AI

## Executive Summary

To build an industry-grade, zero-hallucination AMC Context Engineering platform without vendor lock-in, this technical blueprint maps out an **exhaustive, multi-layered open-source technology stack**. 

Every evaluated repository is selected based on **production stability**, **community adoption (GitHub stars & enterprise sponsorship)**, **permissive licensing (Apache-2.0 / MIT)**, and **direct architectural value** across the 8 layers of our enterprise system.

---

## 1. The 8-Layer Enterprise Open-Source Technology Stack

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                        Enterprise Production Open-Source Stack                            │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Ingestion & Document Vision │ IBM Docling (`docling-project/docling`)                  │
│                                │ OpenDataLab MinerU (`opendatalab/MinerU`)                │
│                                │ Vik Paruchuri Marker (`datalab-to/marker`)               │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 2. Structural & Layout Index   │ RAGFlow (`infiniflow/ragflow`)                            │
│                                │ PageIndex Structural Layout Indexing                     │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 3. Knowledge Graph Engine      │ Neo4j GraphRAG (`neo4j/neo4j-graphrag`)                  │
│                                │ FalkorDB (`falkordb/falkordb`) / Memgraph (`memgraph`)   │
│                                │ Vespa Engine (`vespa-engine/vespa`)                      │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 4. Token Compression & Caching │ Microsoft LLMLingua-2 (`microsoft/LLMLingua`)            │
│                                │ Zilliz GPTCache (`zilliztech/GPTCache`)                  │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 5. Universal Gateway & MCP     │ LiteLLM (`BerriAI/litellm`)                               │
│                                │ MetaMCP (`metatool-ai/metamcp`)                           │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 6. Agentic Orchestration & Loop│ LangGraph (`langchain-ai/langgraph`)                      │
│                                │ Stanford DSPy (`stanfordnlp/dspy`)                        │
│                                │ CrewAI (`crewAIInc/crewAI`)                              │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 7. Guardrails & Compliance Rail│ NVIDIA NeMo Guardrails (`NVIDIA-NeMo/Guardrails`)        │
│                                │ Guardrails AI (`guardrails-ai/guardrails`)               │
│                                │ Meta Llama Guard (`meta-llama/PurpleLlama`)              │
├────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 8. Orchestration & Evaluation  │ Ragas (`explodinggradients/ragas`)                       │
│                                │ Arize Phoenix (`Arize-ai/phoenix`)                       │
│                                │ Dagster (`dagster-io/dagster`) / Temporal (`temporalio`) │
└────────────────────────────────┴───────────────────────────────────────────────────────────┘
```

---

## 2. Exhaustive GitHub Repository Evaluation Matrix

| Architectural Layer | Open-Source Repository | License | GitHub Stars | Enterprise Backer / Origin | Core Function in AMC Platform |
|---|---|---|---|---|---|
| **1. Document Vision & Parsing** | [`docling-project/docling`](https://github.com/docling-project/docling) | MIT | ~14k+ | IBM Research | Parses PDFs into structured Markdown/JSON preserving tables, formulas, and headers for RAG. |
| | [`opendatalab/MinerU`](https://github.com/opendatalab/MinerU) | AGPL-3.0 | ~21k+ | OpenDataLab | High-fidelity extraction of complex multi-column SEBI annual report PDFs. |
| | [`datalab-to/marker`](https://github.com/datalab-to/marker) | GPL-3.0 | ~19k+ | Vik Paruchuri | Fast PDF-to-Markdown converter stripping headers/footers. |
| | [`datalab-to/surya`](https://github.com/datalab-to/surya) | GPL-3.0 | ~13k+ | Vik Paruchuri | Multilingual OCR and layout analysis across 90+ languages. |
| **2. Deep Layout RAG** | [`infiniflow/ragflow`](https://github.com/infiniflow/ragflow) | Apache-2.0 | ~24k+ | InfiniFlow | Deep document understanding RAG engine with zero-chunk-loss layout parsing. |
| **3. Knowledge Graph Engine** | [`neo4j/neo4j-graphrag`](https://github.com/neo4j/neo4j-graphrag) | Apache-2.0 | High | Neo4j Official | Native Python SDK for hybrid HNSW vector + openCypher edge traversal. |
| | [`falkordb/falkordb`](https://github.com/falkordb/falkordb) | BSD-3-Clause | ~3.2k+ | FalkorDB | Ultra-fast Redis-based C/C++ Knowledge Graph database engine. |
| | [`memgraph/memgraph`](https://github.com/memgraph/memgraph) | Apache-2.0 | ~4.8k+ | Memgraph | In-memory C++ high-performance Cypher-compatible graph database. |
| | [`vespa-engine/vespa`](https://github.com/vespa-engine/vespa) | Apache-2.0 | ~5.6k+ | Yahoo / Spotify | Enterprise multi-vector + hybrid search + real-time graph ranking engine. |
| **4. Compression & Cache** | [`microsoft/LLMLingua`](https://github.com/microsoft/LLMLingua) | MIT | ~3.8k+ | Microsoft Research | Token-classification prompt compressor (3x–6x compression in <15ms). |
| | [`zilliztech/GPTCache`](https://github.com/zilliztech/GPTCache) | MIT | ~6.5k+ | Zilliz | Semantic caching layer serving sub-30ms cache hits on query embeddings. |
| **5. Gateway & MCP** | [`BerriAI/litellm`](https://github.com/BerriAI/litellm) | MIT | ~17.5k+ | BerriAI | Universal LLM gateway with failover routing (Claude ↔ Bedrock ↔ Azure). |
| | [`metatool-ai/metamcp`](https://github.com/metatool-ai/metamcp) | MIT | ~1.2k+ | MetaTool AI | MCP Proxy & Router for namespace routing and tool discovery. |
| **6. Agentic Orchestration**| [`langchain-ai/langgraph`](https://github.com/langchain-ai/langgraph) | MIT | ~7.2k+ | LangChain | Stateful graph-based agentic state machine with cycle control and human checkpointing. |
| | [`stanfordnlp/dspy`](https://github.com/stanfordnlp/dspy) | MIT | ~18k+ | Stanford NLP | Programmatic prompt signature optimizer and compiler. |
| | [`crewAIInc/crewAI`](https://github.com/crewAIInc/crewAI) | MIT | ~22k+ | CrewAI | Role-based autonomous multi-agent orchestration framework. |
| **7. Safety & Guardrails** | [`NVIDIA-NeMo/Guardrails`](https://github.com/NVIDIA-NeMo/Guardrails) | Apache-2.0 | ~3.9k+ | NVIDIA | Programmable Colang guardrails for conversational steering and hallucination control. |
| | [`guardrails-ai/guardrails`](https://github.com/guardrails-ai/guardrails) | Apache-2.0 | ~4.1k+ | Guardrails AI | Pydantic-based output reliability and structured schema validation hub. |
| | [`meta-llama/PurpleLlama`](https://github.com/meta-llama/PurpleLlama) | Permissive | ~2.5k+ | Meta AI | Llama Guard 3 input/output content safety classification model. |
| **8. Pipeline & Evals** | [`explodinggradients/ragas`](https://github.com/explodinggradients/ragas) | Apache-2.0 | ~5.8k+ | Exploding Gradients | RAG evaluation benchmark for Faithfulness, Answer Relevance, and Context Recall. |
| | [`Arize-ai/phoenix`](https://github.com/Arize-ai/phoenix) | Apache-2.0 | ~4.1k+ | Arize AI | OpenTelemetry visual tracing and local evaluation dashboard. |
| | [`dagster-io/dagster`](https://github.com/dagster-io/dagster) | Apache-2.0 | ~11k+ | Elementl / Dagster | Asset-based data orchestrator for graph ETL and embedding pipelines. |
| | [`temporalio/sdk-python`](https://github.com/temporalio/sdk-python) | MIT | ~2.5k+ | Temporal | Durable execution workflow engine for fault-tolerant ingestion. |

---

## 3. Detailed Architectural Layer Blueprint & Code Patterns

### 3.1 Document Vision & Layout Parsing Layer (`IBM Docling`)
Replaces naive 512-character chunking with IBM Docling deep layout analysis:

```python
# Installation: pip install docling
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("SEBI_Master_Circular_2026.pdf")

# Returns layout-aware JSON structure with table boundaries and section nodes
exported_json = result.document.export_to_dict()
markdown_content = result.document.export_to_markdown()
```

---

### 3.2 High-Speed Semantic Caching Layer (`GPTCache`)
Interceptors sitting in front of LiteLLM to serve sub-30ms responses for recurring compliance queries:

```python
# Installation: pip install gptcache
from gptcache import Cache
from gptcache.adapter import openai

cache = Cache()
cache.init(
    pre_embedding_func=get_prompt,
    embedding_func=get_embedding,
    data_manager=get_data_manager()
)
```

---

### 3.3 Programmable Guardrails Layer (`NVIDIA NeMo Guardrails`)
Enforces Colang conversational rails to block off-topic queries and verify factual grounding:

```colang
# config/rails.co
define user query sebi compliance
  "Can an AMC run two equity schemes under 2026 rules?"

define flow sebi compliance
  user query sebi compliance
  $graph_facts = execute neptune_cypher_lookup()
  $answer = execute generate_answer(context=$graph_facts)
  $is_grounded = execute check_grounding(answer=$answer, context=$graph_facts)
  if not $is_grounded
    bot refrains from answering
  else
    bot respond
```

---

### 3.4 Stateful Agentic Loop Control (`LangGraph`)
Implements deterministic state machine cycles for multi-hop graph exploration:

```python
# Installation: pip install langgraph
from langgraph.graph import StateGraph, END

class GraphState(dict):
    query: str
    graph_context: list
    retry_count: int

workflow = StateGraph(GraphState)

# Add node state machine functions
workflow.add_node("retrieve", neptune_retriever_node)
workflow.add_node("verify", cypher_assertion_verifier_node)
workflow.add_node("generate", llm_generation_node)

# Connect execution edges
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "verify")
workflow.add_conditional_edges("verify", should_retry_condition, {True: "retrieve", False: END})
```

---

## 4. Phased Open-Source Technology Adoption Timeline

```
Phase 1: Ingestion & Parsing Upgrade (Weeks 1–3)
  ├── Integrate IBM Docling (`docling-project/docling`) for page layout parsing
  └── Implement Zilliz GPTCache for sub-30ms query caching

Phase 2: Guardrails & Universal Gateway (Weeks 4–6)
  ├── Deploy NVIDIA NeMo Guardrails (`NVIDIA-NeMo/Guardrails`) with Colang rails
  ├── Deploy Guardrails AI (`guardrails-ai/guardrails`) Pydantic validator hub
  └── Configure LiteLLM proxy with multi-provider failover routing

Phase 3: Agentic Loops & Orchestration (Weeks 7–10)
  ├── Migrate agent workflow to LangGraph (`langchain-ai/langgraph`)
  ├── Deploy Dagster (`dagster-io/dagster`) for automated graph ETL orchestration
  └── Establish OpenTelemetry tracing with Arize Phoenix (`Arize-ai/phoenix`)
```
