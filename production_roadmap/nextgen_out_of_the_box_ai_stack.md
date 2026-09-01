# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Out-of-the-Box Next-Gen Enterprise AI Blueprint for AMC Context Engineering

## Executive Overview

To build a production-grade system that moves beyond basic vector chunking and naive prompt assembly, this master blueprint integrates **five cutting-edge, enterprise-tested architectural components**:

1. **`PageIndex`**: Vectorless, page-level structural document indexing that preserves SEBI circular hierarchies, tables, and clause boundaries.
2. **`LLMLingua-2` (Microsoft Research)**: Task-agnostic token-classification prompt compression (3x–6x token reduction, eliminating context rot).
3. **`LiteLLM`**: Universal enterprise LLM gateway with multi-provider failover (Claude ↔ Bedrock ↔ Azure OpenAI), rate limiting, and budget caps.
4. **`MCP` (Model Context Protocol) & `MetaMCP`**: Standardized Anthropic tool/context protocols enabling decoupled, composable microservice MCP servers for Graph, Document, and SEBI Registry feeds.
5. **`Temporal.io` & `DSPy`**: Durable asynchronous execution workflows for graph ETL paired with programmatic prompt compilation.

---

## 1. The Next-Gen Enterprise AI Topology

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                           Next-Gen Enterprise Architecture Stack                          │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                           │
│  [ Client / UI / API ] ──► LiteLLM Universal Gateway (Rate Limit, Failover, Budget Caps)  │
│                                           │                                               │
│                                           ▼                                               │
│                            MetaMCP Router & Proxy Gateway                                 │
│                                (RBAC, Discovery, Audit)                                   │
│                                           │                                               │
│             ┌─────────────────────────────┼─────────────────────────────┐                 │
│             │                             │                             │                 │
│             ▼                             ▼                             ▼                 │
│  [ MCP Server 1 ]           [ MCP Server 2 ]           [ MCP Server 3 ]                   │
│   Neptune Graph MCP          PageIndex Layout MCP       SEBI Live Feed MCP                │
│   (openCypher Engine)        (Structural Hierarchy)     (Kafka CDC Engine)                │
│             │                             │                             │                 │
│             └─────────────────────────────┼─────────────────────────────┘                 │
│                                           │                                               │
│                                           ▼                                               │
│                            LLMLingua-2 Prompt Compressor                                  │
│                            (3x–6x Compression, No Context Rot)                            │
│                                           │                                               │
│                                           ▼                                               │
│                            LLM Inference Engine (Claude 3.5 / Bedrock)                    │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component-by-Component Production Deep Dive

### 2.1 `PageIndex`: Vectorless Page-Level Structural Indexing
* **The Problem with Naive RAG**: Standard 512-token chunking splits SEBI circular tables, breaks schedule notes, and loses page context, leading to inaccurate responses.
* **The `PageIndex` Pattern**:
  * Ingests documents as **Hierarchical Layout Trees**: `Document` $\rightarrow$ `Page` $\rightarrow$ `Section` $\rightarrow$ `Table/Clause`.
  * Preserves bounding boxes, table rows, and clause numbers without slicing text artificially.
  * Navigates document structure via **Reasoning Trees** (like a human expert using a Table of Contents) rather than raw cosine distance.
* **Graph Integration**: Every `PageIndex` node maps directly to Neo4j/Neptune `(PageNode)-[:CONTAINS_CLAUSE]->(RegulatoryRule)`.

```
SEBI Master Circular (PDF)
  ├── Page 1: Short Title & Applicability
  ├── Page 14: Clause 2.6.3.16 (Solution Oriented Sunset)
  │     └── Table 4: Merger Window Timeline (24 Months)
  └── Page 28: Penalty Schedule
```

---

### 2.2 `LLMLingua-2` (Microsoft Research): Prompt Compression
* **The Problem**: Passing large graph context + PageIndex documents into LLMs inflates token costs and triggers "Lost in the Middle" context rot.
* **The `LLMLingua-2` Solution**:
  * Uses a fast XLM-RoBERTa / mBERT token-classification model trained via GPT-4 distillation.
  * Compresses context by **3x to 6x (saving 60–80% tokens)** while retaining exact legal clause numbers, dates, and numeric thresholds.
  * Runs in **<15ms CPU inference time**, dramatically lowering LLM Time-to-First-Token (TTFT).

```python
from llmlingua import PromptCompressor

compressor = PromptCompressor(model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank")

# Compress verbose retrieved graph + PageIndex context
compressed_prompt = compressor.compress_prompt(
    context=[verbose_graph_facts, pageindex_clause_text],
    instruction="Analyze 2026 SEBI Solution Oriented scheme merger timeline",
    rate=0.33  # 3x compression
)
print("Compressed Tokens Saved:", compressed_prompt["origin_tokens"] - compressed_prompt["compressed_tokens"])
```

---

### 2.3 `LiteLLM`: Universal LLM Gateway & Failover Proxy
* **Production Capability**:
  * **Multi-Provider Load Balancing**: Dynamically balances requests across Anthropic API, AWS Bedrock, and Azure OpenAI.
  * **Zero-Downtime Fallback**: If Anthropic API returns HTTP 429 / 503, LiteLLM fails over to AWS Bedrock in **<50ms**.
  * **Enterprise Controls**: Implements per-team budget limits, rate limiting, and OpenTelemetry logging out-of-the-box.

```yaml
# LiteLLM config.yaml
model_list:
  - model_name: compliance-haiku
    litellm_params:
      model: anthropic/claude-3-5-haiku-20241022
      api_key: os.environ/CLAUDE_API_KEY
  - model_name: compliance-haiku
    litellm_params:
      model: bedrock/anthropic.claude-3-5-haiku-20241022-v1:0
      aws_region_name: ap-south-1

router_settings:
  fallbacks: [{"compliance-haiku": ["bedrock-haiku"]}]
  num_retries: 3
  timeout: 10
```

---

### 2.4 `MCP` (Model Context Protocol) & `MetaMCP` Gateway
Anthropic's **Model Context Protocol (MCP)** standardizes how AI agents connect to enterprise data sources.

```
                  ┌──────────────────────────────────────────────┐
                  │            MetaMCP Proxy Gateway             │
                  │   (Namespace Routing, Policy Enforcement)    │
                  └──────────────────────┬───────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
┌───────▼─────────────┐       ┌──────────▼──────────┐        ┌────────────▼────────────┐
│ Neptune Graph MCP   │       │ PageIndex Layout MCP│        │ SEBI Registry Feed MCP  │
│ Server (openCypher) │       │ Server (PDF Layout) │        │ Server (Live Circulars) │
└─────────────────────┘       └─────────────────────┘        └─────────────────────────┘
```

#### MCP Server Architecture:
1. **`neptune-graph-mcp-server`**: Exposes openCypher graph traversals as standardized MCP tools (`get_mutual_exclusion`, `get_regime_amendments`).
2. **`pageindex-sebi-mcp-server`**: Exposes structural page navigation as standardized MCP tools (`get_page_hierarchy`, `get_table_by_clause`).
3. **`MetaMCP` Proxy**: Multiplexes all microservice MCP servers into a single secure endpoint with OAuth2/JWT authentication, rate limiting, and RBAC.

---

### 2.5 `Temporal.io` & `DSPy`: Durable Ingestion & Prompt Compilation
* **`Temporal.io` (Durable Execution Workflows)**: Replaces fragile Python ETL scripts with stateful, fault-tolerant workflows. If a PDF ingestion job fails mid-page due to server restart, Temporal resumes from the exact failed activity step without data loss.
* **`DSPy` (Programmatic Prompt Optimization)**: Replaces manual prompt string tuning with compiled, self-improving prompt signatures optimized against a validation dataset.

---

## 3. Comprehensive Open-Source GitHub Repository Matrix

| Technology | GitHub Repository | License | Stars | Production Role in AMC Stack |
|---|---|---|---|---|
| **`LLMLingua-2`** | [`microsoft/LLMLingua`](https://github.com/microsoft/LLMLingua) | MIT | ~3.8k+ | **Prompt Compression Engine**. Reduces prompt size by 3x–6x, eliminating context rot. |
| **`LiteLLM`** | [`BerriAI/litellm`](https://github.com/BerriAI/litellm) | MIT | ~17.5k+ | **Universal LLM Gateway**. Failover routing across Claude, Bedrock, and Azure OpenAI. |
| **`MetaMCP`** | [`metatool-ai/metamcp`](https://github.com/metatool-ai/metamcp) | MIT | ~1.2k+ | **MCP Proxy & Orchestrator**. Namespace routing and security middleware for MCP servers. |
| **`Temporal.io`** | [`temporalio/sdk-python`](https://github.com/temporalio/sdk-python) | MIT | ~2.5k+ | **Durable ETL Workflow**. Fault-tolerant ingestion pipelines with automatic state recovery. |
| **`DSPy`** | [`stanfordnlp/dspy`](https://github.com/stanfordnlp/dspy) | MIT | ~18k+ | **Prompt Compiler**. Replaces hand-written prompt templates with compiled optimization. |
| **`Unstructured`** | [`Unstructured-IO/unstructured`](https://github.com/Unstructured-IO/unstructured) | Apache-2.0 | ~8.5k+ | **PageIndex Document Parser**. Structural PDF/Table parser preserving page layouts. |

---

## 4. Next-Gen Architecture Implementation Roadmap

```
Phase 1: PageIndex & Prompt Compression (Weeks 1–3)
  ├── Deploy Unstructured / PyMuPDF PageIndex layout parser
  ├── Integrate Microsoft LLMLingua-2 prompt compressor (3x reduction)
  └── Connect PageIndex structural nodes to Neo4j/Neptune

Phase 2: Gateway & MCP Infrastructure (Weeks 4–6)
  ├── Deploy LiteLLM Proxy with Bedrock failover routing
  ├── Build neptune-graph-mcp-server and pageindex-mcp-server
  └── Deploy MetaMCP gateway for tool discovery and RBAC

Phase 3: Durable Workflows & Optimization (Weeks 7–10)
  ├── Deploy Temporal.io durable ETL ingestion workflows
  ├── Compile prompt signatures using DSPy optimizer
  └── Integrate OpenTelemetry tracing across LiteLLM and MCP servers
```
