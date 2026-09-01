# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Evidence-Based Baseline Kit

This directory is the starting point for convergence work. It records what the
running system actually does before a serving-path, ingestion, or data-store
change is made. It deliberately distinguishes **observed evidence** from the
repository's intended design documents.

## What this baseline answers

1. Which API, UI, graph, and vector paths are currently live?
2. Which documents and identifiers are visible through the API and graph?
3. Does a fixed set of representative queries produce grounded, traceable
   answers on the production serving path?
4. Which failures are service/configuration failures versus retrieval failures?
5. Can each claimed metric be reproduced from raw response data?

## Current static evidence (2026-08-14)

| Concern | Observed implementation | Evidence |
|---|---|---|
| Production query route | `/api/query` calls `app.engine.retrieval`, not `RetrievalOrchestrator`. | `backend/app/api/routes/query.py` |
| Modern pipeline | `/api/ingest` queues `IngestionPipeline`, which writes its own FAISS payload store plus Neo4j. | `backend/app/api/routes/ingest.py`, `backend/app/ingestion/pipeline.py` |
| Modern orchestrator | Constructed in the dependency container; used by graph/taxonomy utility routes and tests, not `/api/query`. | `backend/app/api/deps.py` |
| Default UI mode | Streamlit calls the FastAPI API when `API_BASE` is an HTTP URL; it has a local taxonomy fallback on outage/offline mode. | `streamlit_app/app.py` |
| Deployed Neo4j topology | `docker-compose.yml` exposes a single Neo4j service on port 7687. | `docker-compose.yml` |
| Taxonomy build topology | The taxonomy build script still has a hard-coded 7688 endpoint. | `backend/scripts/build_taxonomy_graph.py` |
| Legacy index identity | The 50-document index stores a raw `doc_name` in its metadata. | `backend/scripts/build_50doc_faiss_index.py` |
| Modern index identity | Modern chunks use one generated `document_id` across graph and vector writes within an ingestion run. | `backend/app/schemas/documents.py`, `backend/app/vector/client.py` |

The static evidence is a hypothesis about deployment, not a substitute for the
live run. Update this table only after keeping raw probe output in a dated run
directory.

## Run a live baseline

Prerequisites:

- The API is running and reachable from the machine running the script.
- PowerShell 7+ or Windows PowerShell 5.1 is available.
- The default collection is read-only; use a non-production environment for
  any follow-up ingestion or cache experiments.

From the repository root:

```powershell
./backend/scripts/collect_baseline.ps1
```

Useful variants:

```powershell
./backend/scripts/collect_baseline.ps1 -ApiBase 'http://localhost:8000'
./backend/scripts/collect_baseline.ps1 -ApiBase 'https://example.internal' -SkipQueries
./backend/scripts/collect_baseline.ps1 -OutputRoot 'C:\baseline-results'
```

The collector writes raw endpoint responses, query responses, a run manifest,
and a compact summary under `logs/baseline/<UTC timestamp>/`. It does not send
documents, create ingestion jobs, clear caches, or modify a graph/index. Query
and chat routes may still create their normal audit-log or cache entries; this
is an expected side effect that must be recorded as the run's cache state.

Never treat a failed request as an empty result: each failure is saved with its
HTTP status and error body in `manifest.json`.

## Run the static test baseline

The current machine has no installed Python interpreter (`py -0p` reported no
interpreters on 2026-08-14), so tests cannot run until the project interpreter
is provisioned. Once it is available:

```powershell
cd backend
python -m pytest tests/test_schemas_and_contracts.py tests/test_ingestion_units.py -q
python -m pytest -m e2e -q
```

Keep the first command (offline contract/unit checks) separate from the second
(live services + LLM). Record the interpreter version, dependency lock state,
environment name, and both exit codes in the baseline run manifest.

## Graph integrity checks

Run the read-only Cypher queries in
`Docs/baseline/neo4j_integrity_queries.cypher` against the same Neo4j instance
reported by `/api/status`. Export their results into the corresponding
`logs/baseline/<run>/` folder. The API document list and graph document list
must be compared using the exact `document_id`, not filename/title.

## Acceptance criteria for a usable baseline

- A timestamped raw result exists for `/api/status`, `/api/docs`, `/api/taxonomy`,
  `/api/graph`, `/api/query`, and `/api/chat` (or a recorded reason it cannot).
- All fixture queries in `query_fixtures.json` have a response or a captured
  service failure; none are silently omitted.
- The selected environment, API revision/image, configuration-safe topology,
  corpus/index counts, and graph counts are recorded.
- Query results retain raw sources, graph highlights, metrics, and latency.
- Any metrics headline is calculated from raw output and names its denominator:
  cold versus warm cache, successful requests only versus all requests, and
  observed versus estimated tokens.

## What not to do during baseline collection

- Do not rebuild FAISS, reseed Neo4j, invoke taxonomy builders, or run batch
  ingestion against the reference environment.
- Do not clear caches before the first run. Capture cold/warm state explicitly
  in separate runs instead.
- Do not manually edit response files; write an addendum if interpretation
  changes.
