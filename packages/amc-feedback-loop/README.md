# Human Feedback Loop Module (`amc-feedback-loop`)

Installable Python package providing the core `feedback_loop` module for the AMC feedback pipeline. Captures feedback records, evaluates them across 4 deterministic steps, and builds unified evaluation records.

## Architecture

```
AMC (host app)
   │
   └── start_feedback_loop(feedback_id, session_id, response_id, source)
            │
            ▼
      IngestService.on_ingest()
            │
            ├── [concurrent] Step 1 — ClassificationService   (active only)
            ├── [concurrent] Step 2 — EvidenceEnrichmentService
            │
            ├── [join] ──────────────────────────────────────────
            │
            ├── Step 3 — AdaptiveRouterService
            └── Step 4 — AdjudicationService
                        │
                        └── DB write → unified_evaluation_records
```

## Features

- **Step 1 — Classification (`ClassificationService`)**:
  - Named entity extraction via spaCy
  - Sentiment analysis via VADER
  - Rule-based intent detection (correction vs complaint vs neutral)
- **Step 2 — Evidence Enrichment (`EvidenceEnrichmentService`)**:
  - Frozen context snapshot retrieval (D0–D3 layers)
  - Duplicate detection and session clustering
  - Dissatisfaction signal detection for passive feedback capture
- **Step 3 — Adaptive Router (`AdaptiveRouterService`)**:
  - Referential integrity check (C01)
  - Temporal freshness check (C02)
  - Numeric accuracy verification (C03)
  - Structured correction detection (C04)
  - Compliance and regulatory rule evaluation (C05)
  - Dynamic severity assignment (CRITICAL, HIGH, MEDIUM, LOW)
- **Step 4 — Adjudication (`AdjudicationService`)**:
  - Multi-dimension root cause classification:
    - `model` (hallucination / numerical discrepancy)
    - `knowledge` (information gap / explicit correction)
    - `retrieval` (retriever missed entity or stale data)
    - `compliance` (regulatory violation)
    - `presentation` (formatting / style)
    - `feedback_invalid` (unsupported or contradictory feedback)
- **Extensible Adapters**:
  - `AbstractDatabaseAdapter` with `InMemoryDatabaseAdapter` and `SQLiteDatabaseAdapter`
  - `AbstractEvidenceAdapter` with `InMemoryEvidenceAdapter` and `SQLiteEvidenceAdapter`
- **Automatic Event Triggering**:
  - `register_feedback_trigger` for SQLAlchemy `after_flush` hook execution.

## Installation

### Local editable installation (Development)

```bash
pip install -e packages/amc-feedback-loop
```

## Usage

```python
from feedback_loop import FeedbackLoopConfig, start_feedback_loop
from feedback_loop.adapters import InMemoryDatabaseAdapter, InMemoryEvidenceAdapter

config = FeedbackLoopConfig()
db = InMemoryDatabaseAdapter()
evidence = InMemoryEvidenceAdapter()

# Trigger feedback evaluation pipeline
success = start_feedback_loop(
    feedback_id="fb_001",
    session_id="sess_001",
    response_id="resp_001",
    source="active",
    config=config,
    db=db,
    evidence_adapter=evidence,
)
```

## Running Tests

```bash
pytest packages/amc-feedback-loop/tests
```
