# AMC Feedback Loop

Reusable feedback loop component for Retrieval-Augmented Generation (RAG) and context engineering pipelines.

## Features
- **Config-Driven Architecture**: Easily tune entity recognition, similarity thresholds, and keywords without code modifications.
- **Multi-layer NER Pipeline**: Combines rule-based gazetteers (spaCy) and zero-shot open-domain NER (ONNX-quantized GLiNER).
- **Entity Resolution**: Domain catalog fuzzy matching with RapidFuzz.
- **Dissatisfaction & Correction Detection**: Detects user corrections and dissatisfaction across conversation turns.
- **Pluggable Storage Adapters**: Works seamlessly with SQLite, PostgreSQL, or custom data stores.
