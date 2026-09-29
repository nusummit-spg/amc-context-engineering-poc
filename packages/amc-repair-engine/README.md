# AMC Repair Engine

Self-correcting repair engine for RAG knowledge bases, featuring:
- **Correction Patch Layer**: In-memory and Redis-backed active patches for instant query context healing.
- **Tiered Evaluation Engine**: Multi-stage evaluation rules (deterministic verification, NLI, and LLM judge).
- **Automated Governance**: Batch promotion of validated patches into canonical graph databases (Neo4j).
- **Pluggable Adapters**: Clean abstraction for cache backends (memory / Redis) and graph stores.
