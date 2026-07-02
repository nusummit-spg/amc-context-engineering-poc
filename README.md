# amc-context-engineering-poc

Proof of Concept to evaluate **Traditional RAG vs Context Engineering** for asset
management companies (AMCs). The backend serves both sides of the comparison UI:
a flat vector-search baseline, and NuSummit ContextGraph — taxonomy-scoped hybrid
retrieval over a knowledge graph.

## Architecture

```
INGESTION PIPELINE
  [Documents] → [Parser] → [Chunker] → [PII Scrub] → [Embedder]
        ↓ [LLM Classifier] → [Taxonomy Tagger]
        ↓ [NER + Entity Extractor] → [Entity Resolver]
        ↓ [Relationship Extractor]
        │
  ┌─────┴─────────┐
  VECTOR DB        GRAPH DB
  (Qdrant)         (Neo4j)
  chunks +         entities, taxonomy
  embeddings +     nodes, relationships,
  taxonomy tags    document refs
  └─────┬─────────┘
        ↓
  RETRIEVAL ENGINE (7-step)
  1. Intent classify  2. Entity resolve  3. Graph traverse
  4. Taxonomy scope   5. Vector search   6. Context assemble  7. LLM synthesize
        ↓
  FastAPI: /api/query /api/taxonomy /api/graph /api/docs /api/ingest /api/status
        ↓
  Interactive demo UI (WS4 — separate frontend)
```

## Repository layout

```
backend/
  app/
    schemas/       WS5a — Pydantic data contracts (Document/Chunk, 9 entity types,
                   relationships, taxonomy, QueryIntent, RetrievalResult,
                   AssembledContext, SynthesisOutput, API models)
    prompts/       WS5c — versioned prompt library with few-shot examples
    core/          WS3  — LLM client wrapper (retry + rate limit), errors, logging
    ingestion/     WS2  — parsers (PDF/DOCX/PPTX/MSG/EML/XLSX/MD/TXT), semantic
                   chunker, PII scrubber, ingestion pipeline
    extraction/    taxonomy classifier, AMC-domain NER, entity resolver,
                   rule-based + LLM relationship extractors
    graph/         WS5b/WS5e — Neo4j client, schema, Cypher query library
    vector/        Qdrant client, local fastembed embeddings, scoped search
    retrieval/     WS5d/WS5e — intent, traversal strategies, token-budgeted
                   context assembly with quality gate, synthesis, orchestrator
    api/           WS3  — routes + dependency injection
    tasks/         WS3  — asyncio ingestion job queue
  seeds/           WS5b/WS1 — taxonomy.json (4-level), entity_aliases.json
  scripts/         seed_neo4j.py, ingest_corpus.py
  tests/           unit + contract tests, e2e demo-query tests
docker-compose.yml   WS1/WS3 — Neo4j + Qdrant + Redis + API
```

## Run the stack (one command)

```bash
# 1. Set your API key (or put it in backend/.env — see backend/.env)
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Bring everything up
docker compose up --build
```

- API: http://localhost:8000/docs (OpenAPI — share with frontend)
- Neo4j browser: http://localhost:7474 (neo4j / contextgraph)
- Qdrant dashboard: http://localhost:6333/dashboard

## Local development (without Docker for the API)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
copy .env .env                            # then edit

# start only the databases
docker compose up -d neo4j qdrant

# seed schema + taxonomy + canonical entities
python -m scripts.seed_neo4j

# drop the demo corpus files into backend/data/corpus, then:
python -m scripts.ingest_corpus

# run the API
uvicorn app.main:app --reload
```

## Try it

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our exposure to Adani Group across all schemes?", "mode": "both"}'
```

`mode` is `contextgraph`, `traditional`, or `both` — `both` returns the two panels
of the comparison UI in one response.

## Tests

```bash
cd backend
pytest                    # unit + contract tests (no external services needed)
pytest -m e2e             # end-to-end demo-query tests (full stack + API key required)
```

## Workstream map

| Workstream | Where |
|---|---|
| WS1 Infrastructure | `docker-compose.yml`, `backend/.env.example`, `seeds/`, this README |
| WS2 Ingestion & parsing | `backend/app/ingestion/` |
| WS3 Backend API | `backend/app/api/`, `app/main.py`, `app/core/`, `app/tasks/` |
| WS5a Schemas | `backend/app/schemas/` |
| WS5b Taxonomy & ontology | `backend/seeds/`, `app/graph/schema.py`, `scripts/seed_neo4j.py` |
| WS5c Prompt library | `backend/app/prompts/library.py` |
| WS5d Context engineering | `backend/app/retrieval/context.py`, `intent.py`, `traversal.py` |
| WS5e Retrieval & orchestration | `backend/app/retrieval/orchestrator.py`, `app/graph/cypher_library.py`, `app/extraction/` |
| WS4 Frontend | (separate — consumes `/api/*`; see http://localhost:8000/docs) |
