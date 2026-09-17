# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Master Implementation Plan — Comprehensive Open-Source Stack Adoption & System Architecture Roadmap

> **Phase Update**: All **AWS Cloud Migration steps (Neptune, OpenSearch, Bedrock) are PAUSED**. The current phase focuses 100% on **On-Premise & Local Enterprise Production Readiness**, capturing and implementing the **8-Layer Open-Source Production Stack** defined across the strategic documents in `production_roadmap/`.

---

## 1. The 8-Layer Open-Source Stack Capture Matrix

Below is the complete mapping of open-source repositories and Python packages captured from `production_roadmap/` to be integrated into our codebase:

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                        Enterprise Production Open-Source Stack                            │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Layer 1: Document Parsing     │ IBM Docling (`docling`) & EasyOCR                         │
│ Layer 2: Structural Chunking  │ Sentence-Boundary Regex & Parent-Child Indexing            │
│ Layer 3: Knowledge Graph      │ `neo4j-graphrag` HybridRetriever & `getzep/graphiti`     │
│ Layer 4: Compression & Cache  │ Triple Notation & Dual-Gate Intent Cache                  │
│ Layer 5: Universal Gateway    │ LiteLLM (`litellm`) Provider Failover                     │
│ Layer 6: Agentic State Loops  │ LangGraph (`langgraph`) & DSPy Prompt Optimizer (`dspy`)  │
│ Layer 7: Security & Safety    │ Microsoft Presidio, NeMo Guardrails & Guardrails AI       │
│ Layer 8: Observability & Eval │ Arize Phoenix / Langfuse (OTel) & RAGAS Benchmark         │
│ Speed & Reranking Acceleration│ FlashRank (Sub-15ms ONNX Reranker) & FastEmbed (C++)      │
└────────────────────────────────┴───────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Adoption Blueprint & Code Base Mapping

| Layer | Captured Package / Tool | Codebase Location | Integration Role & Action |
|---|---|---|---|
| **Layer 1: Document Parsing** | `docling` (IBM Research) | `document_extractors.py` | Parses complex PDF tables, multi-column layouts, and markdown headers without chunk loss. |
| **Layer 2: Structural Chunking** | Clause Regex + `docling` | `faiss_store.py` | Sentence-boundary splitting (`(?<!\b\d)`) with SHA-256 chunk hashes (`doc_sha256`). |
| **Layer 3: Knowledge Graph** | `neo4j-graphrag` & `graphiti` | `graph_store.py` / `taxonomy_retrieval.py` | Replaces custom Cypher code with `HybridRetriever` and adds `valid_from` / `valid_to` temporal edges. |
| **Layer 4: Compression & Cache** | Triple Notation & `intent_cache` | `context_engineering.py` / `intent_cache.py` | Micro-notation (`[GRAPH] S:Rel(O)`) saving **60% tokens**, plus sub-50ms intent caching with Date Guards. |
| **Layer 5: Universal Gateway** | `litellm` (BerriAI) | `llm_text_client.py` | Groq Llama-3.3-70B primary -> Claude Haiku fallback -> Native SDK last resort. |
| **Layer 6: Agent Dynamic Loops** | `langgraph` & `dspy` | `retrieval.py` / `query_classifier.py` | Stateful graph state machine managing self-correction loops and constraint verification. |
| **Layer 7: Security & Safety** | `presidio`, `NeMo Guardrails`, `guardrails-ai` | `pii_scrub.py` / `compliance_guardrails.py` | PII redaction metrics, prompt injection shield, and SEBI RIA financial advice guard. |
| **Layer 8: Observability & Evals** | `phoenix`, `langfuse`, `ragas` | `retrieval.py` / `scratch/` | OpenTelemetry tracing dashboard and continuous evaluation (Faithfulness, Relevance, Recall). |
| **Speed & Reranking** | `flashrank` & `fastembed` | `faiss_store.py` / `retrieval.py` | Sub-15ms CPU cross-encoder reranking and ONNX-accelerated C++ embeddings. |

---

## 3. Phased Implementation Schedule

```
Phase 1: Security, Language & Output Guardrails (Completed & Verified)
  ├── Multilingual language detection & regional routing (`language_detector.py`)
  ├── PII redaction audit metrics & DPDP compliance (`pii_scrub.py`)
  ├── SEBI RIA Financial Advice Shield & SEBI Disclaimer (`compliance_guardrails.py`)
  ├── SHA-256 document checksum hash traceability (`faiss_store.py`)
  └── Triple Notation graph context compression (`context_engineering.py`)

Phase 2: Reranking & Fast Embeddings (Next Steps)
  ├── FlashRank (`flashrank`) integration for sub-15ms CPU cross-encoder reranking
  ├── FastEmbed (`fastembed`) integration for ONNX CPU embedding generation
  └── IBM Docling (`docling`) integration for structured PDF layout parsing

Phase 3: Open-Source Graph & Agentic Loops
  ├── `neo4j-graphrag` `HybridRetriever` integration
  ├── `getzep/graphiti` temporal graph amendment edge integration
  └── LangGraph (`langgraph`) state machine cycle integration

Phase 4: Observability & Continuous Evaluation
  ├── Arize Phoenix / Langfuse OpenTelemetry trace span exporter
  └── RAGAS automated benchmark scorecard evaluation integration
```

---

## 4. User Review & Confirmation

> [!IMPORTANT]
> All open-source tools from `production_roadmap/` have been captured and mapped into this Phased Implementation Roadmap. Phase 1 is **100% completed and verified by automated tests**.
