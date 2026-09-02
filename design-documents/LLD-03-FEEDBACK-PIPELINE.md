# LLD-03 — Feedback Pipeline

**Document:** LLD-03  
**Version:** 1.0  
**Depends on:** LLD-02 (Evidence Capture), LLD-01 (System Overview)  
**Read next:** LLD-04 (Evaluation Router)

---

## 1. Purpose

The feedback pipeline bridges user signals and the evaluation layer. It has two distinct phases with very different latency requirements:

1. **Synchronous capture** — the user submits a rating; they must see confirmation in < 100 ms
2. **Asynchronous evaluation** — feedback is batched, deduplicated, evaluated, and (conditionally) applied — runs hourly, invisible to users

The key design constraint is that these phases are **fully decoupled**. The synchronous phase does no LLM work. The asynchronous phase does no user-facing work. PostgreSQL is the hand-off point.

---

## 2. Synchronous Feedback Capture (< 100 ms)

### 2.1 HTTP Endpoint

```
POST /api/feedback
Content-Type: application/json

{
  "response_id":     "uuid",         // required — links to EvidencePack
  "rating":          1–5,            // required — 1=very poor, 5=excellent
  "feedback_type":   "string",       // optional — entity|citation|completeness|tone|compliance|other
  "entity_name":     "string",       // optional — which entity is wrong
  "comment":         "string",       // optional — free text, max 2000 chars
  "highlighted_span":{ start, end }, // optional — which part of the response
  "correction":      "string"        // optional — what the correct answer should be
}
```

Response:
```json
{
  "feedback_id": "uuid",
  "status": "recorded",
  "evaluation_status": "pending"
}
```

### 2.2 Processing Steps Inside the Endpoint

The endpoint does the minimum needed to be reliable and return quickly. All heavy work is deferred.

```
Step 1: Validate input
  - response_id exists in evidence_packs table (single SELECT, ~1ms)
  - rating in range [1, 5]
  - comment length ≤ 2000 characters
  - feedback_type is a known enum value
  → Return 400 if validation fails

Step 2: Generate feedback_id (UUID v4, ~0ms)

Step 3: Async INSERT to PostgreSQL feedback_records (~5ms, non-blocking)
  - Insert raw feedback with status='pending'
  - Do NOT wait for commit confirmation

Step 4: Schedule BackgroundTask for pre-classification (~0ms scheduling overhead)
  - NER extraction (spaCy, ~20ms in background)
  - Sentiment scoring (VADER, ~5ms in background)
  - Intent classification (rule-based, ~2ms in background)
  → These run after HTTP response is already sent

Step 5: Return HTTP 202 with feedback_id (~0ms)
```

**Total synchronous latency: < 10 ms excluding network.** The user sees "Feedback recorded ✓" immediately.

### 2.3 Pre-Classification (Background Task)

Runs after the HTTP response is sent. Uses only lightweight local models — no LLM.

```python
async def pre_classify_feedback(feedback_id: str, feedback: FeedbackRequest):
    """
    Runs as a FastAPI BackgroundTask after HTTP response is sent.
    No LLM involvement. Uses local spaCy and VADER models.
    """
    # NER: extract entity mentions from comment text
    entities = ner_pipeline.extract(feedback.comment)
    # e.g. [{"name": "Axis Bluechip Fund", "type": "Scheme", "confidence": 0.94}]

    # Sentiment: VADER polarity scoring
    sentiment = vader_analyzer.polarity_scores(feedback.comment)
    # e.g. {"compound": -0.62, "neg": 0.43, "pos": 0.0, "neu": 0.57}

    # Intent: rule-based first, classifier fallback
    intent = classify_feedback_intent(
        feedback_type=feedback.feedback_type,
        comment=feedback.comment,
        rating=feedback.rating,
        entities=entities,
    )
    # intent values: correction | confirmation | complaint | noise | abuse

    # Quality score: heuristic pre-filter
    quality_score = compute_quality_score(
        rating=feedback.rating,
        has_comment=bool(feedback.comment),
        has_entity=bool(entities),
        has_correction=bool(feedback.correction),
        sentiment_compound=sentiment["compound"],
    )

    # Persist classification results
    await db.execute(
        "UPDATE feedback_records SET ner_tags=$1, sentiment=$2, intent=$3, "
        "quality_score=$4, classification_status='complete' WHERE id=$5",
        [json(entities), json(sentiment), intent, quality_score, feedback_id]
    )
```

### 2.4 Feedback Quality Score

A heuristic pre-filter that runs without LLM. High-quality feedback gets priority in the evaluation queue. Low-quality feedback may be rejected before reaching LLM evaluation.

```
quality_score = base_score * modifiers

base_score = 0.5

modifiers:
  + 0.2   if comment is present and > 20 characters
  + 0.15  if named entity was extracted from comment
  + 0.1   if correction text is present
  + 0.1   if highlighted_span is present
  - 0.3   if rating is extreme (1 or 5) with no comment (likely noise)
  - 0.4   if sentiment is strongly positive (compound > 0.8) for a negative rating
  - 0.5   if flagged as duplicate (same user, same response, < 5 minutes)

quality_score is clamped to [0.0, 1.0]

Routing:
  quality_score < 0.20  → status = 'rejected', skip evaluation
  quality_score ≥ 0.95  → candidate for auto-apply (skip LLM)
  0.20 ≤ score < 0.95   → status = 'pending', enter evaluation queue
```

---

## 3. PostgreSQL Feedback Schema

Core tables used by the feedback pipeline. Full DDL is in LLD-08.

### 3.1 feedback_records

```sql
CREATE TABLE feedback_records (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    response_id          UUID NOT NULL,           -- links to evidence_packs
    interaction_id       UUID NOT NULL,
    session_id           UUID,

    rating               SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    feedback_type        VARCHAR(50),              -- entity | citation | completeness | tone | ...
    entity_name          VARCHAR(255),
    comment              TEXT,
    highlighted_span     JSONB,                    -- {start: int, end: int}
    correction           TEXT,

    -- Pre-classification results (populated by BackgroundTask)
    ner_tags             JSONB,                    -- [{name, type, canonical_id, confidence}]
    sentiment            JSONB,                    -- {compound, neg, pos, neu}
    intent               VARCHAR(50),             -- correction | confirmation | noise | abuse
    quality_score        FLOAT,

    -- Lifecycle
    status               VARCHAR(20) DEFAULT 'pending',
                                                  -- pending | evaluating | applied | rejected | archived
    classification_status VARCHAR(20) DEFAULT 'pending',
                                                  -- pending | complete | failed
    actor_role           VARCHAR(50),             -- user | employee | qa | compliance | sme
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    evaluated_at         TIMESTAMPTZ,
    applied_at           TIMESTAMPTZ,
    archived_at          TIMESTAMPTZ,

    -- Audit
    evaluation_job_id    UUID,
    correction_id        UUID                     -- links to correction_recommendations if applied
);

-- Indexes for common access patterns
CREATE INDEX idx_feedback_response_id    ON feedback_records (response_id);
CREATE INDEX idx_feedback_status_created ON feedback_records (status, created_at);
CREATE INDEX idx_feedback_quality        ON feedback_records (quality_score) WHERE status = 'pending';
CREATE INDEX idx_feedback_entity         ON feedback_records (entity_name) WHERE entity_name IS NOT NULL;
```

### 3.2 evaluation_jobs

```sql
CREATE TABLE evaluation_jobs (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id                  UUID NOT NULL,
    batch_size                INTEGER,
    items_fetched             INTEGER,
    items_deduplicated        INTEGER,     -- after semantic clustering
    items_auto_applied        INTEGER,     -- skipped LLM (quality > 0.95)
    items_auto_rejected       INTEGER,     -- skipped LLM (quality < 0.20)
    items_llm_evaluated       INTEGER,
    corrections_generated     INTEGER,
    corrections_applied       INTEGER,

    status                    VARCHAR(20) DEFAULT 'pending',
                                          -- pending | running | completed | failed
    started_at                TIMESTAMPTZ,
    completed_at              TIMESTAMPTZ,
    error_message             TEXT,

    -- Economics
    llm_tokens_used           INTEGER,
    llm_tokens_saved          INTEGER,     -- vs naive per-item baseline
    llm_calls_made            INTEGER,

    created_at                TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 correction_recommendations

```sql
CREATE TABLE correction_recommendations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id       UUID REFERENCES feedback_records(id),
    evaluation_job_id UUID REFERENCES evaluation_jobs(id),

    correction_type   VARCHAR(50),   -- add_entity | update_property | add_relationship |
                                     -- remove_relationship | update_taxonomy | merge_duplicate
    target_entity     VARCHAR(255),
    target_entity_id  VARCHAR(255),  -- canonical ID
    target_type       VARCHAR(50),

    cypher_mutation   TEXT NOT NULL, -- Cypher statement to execute
    confidence_score  FLOAT NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    reasoning         TEXT,          -- LLM's explanation (stored, not used for execution)

    status            VARCHAR(20) DEFAULT 'pending',
                                    -- pending | approved | applied | rejected | rolled_back
    repair_class      VARCHAR(5),   -- R0 | R1 | R2 | R3 | R4 | R5

    applied_at        TIMESTAMPTZ,
    applied_by        VARCHAR(100), -- 'system' or user_id for manual approvals
    rolled_back_at    TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Asynchronous Evaluation Pipeline

Runs on an APScheduler cron job every hour. Takes ~3 minutes for 500 feedback items with all optimisations applied.

### 4.1 Orchestrator Trigger

```python
# evaluation_orchestrator.py
@scheduler.scheduled_job('cron', minute=0)  # top of every hour
async def run_evaluation_cycle():
    job = await create_evaluation_job()
    try:
        # Step 1: Fetch
        items = await fetch_pending_feedback(limit=500)
        job.items_fetched = len(items)

        # Step 2: Enrich each item with its frozen EvidencePack
        enriched = await enrich_with_evidence(items)

        # Step 3: Aggregate by entity/correction type
        aggregated = aggregate_by_target(enriched)

        # Step 4: Semantic deduplication
        deduplicated = await deduplicate(aggregated)
        job.items_deduplicated = len(aggregated) - len(deduplicated)

        # Step 5: Conditional routing (skip LLM where possible)
        auto_applied, auto_rejected, to_evaluate = route_by_quality(deduplicated)
        job.items_auto_applied = len(auto_applied)
        job.items_auto_rejected = len(auto_rejected)
        job.items_llm_evaluated = len(to_evaluate)

        # Step 6: Batch LLM evaluation
        corrections = await evaluate_batches(to_evaluate)

        # Step 7: Apply eligible corrections
        applied = await apply_corrections(corrections + auto_applied)
        job.corrections_applied = len(applied)

        # Step 8: Cache invalidation
        await invalidate_caches(applied)

        # Step 9: Mark processed
        await mark_processed(items)
        await complete_job(job)

    except Exception as e:
        await fail_job(job, str(e))
        raise
```

### 4.2 Semantic Deduplication

Clusters similar feedback items so the LLM evaluates one representative per cluster rather than every item individually. Reduces item count by ~40%.

```python
async def deduplicate(items: list[FeedbackItem]) -> list[DeduplicatedItem]:
    """
    Embed feedback text using local Sentence Transformers.
    Cluster by cosine similarity >= 0.85.
    Return one representative per cluster + aggregated vote counts.
    No LLM tokens consumed.
    """
    # Embed using local model (no API cost)
    texts = [item.comment or item.feedback_type for item in items]
    embeddings = sentence_transformer.encode(texts)

    # Cosine similarity clustering
    clusters = cluster_by_similarity(embeddings, threshold=0.85)

    result = []
    for cluster in clusters:
        representative = max(cluster, key=lambda x: x.quality_score)
        result.append(DeduplicatedItem(
            representative=representative,
            cluster_size=len(cluster),
            vote_weight=sum(item.quality_score for item in cluster),
            supporting_feedback_ids=[item.id for item in cluster],
        ))

    return result
```

### 4.3 Conditional Routing (60% Skip LLM)

Pre-routes items before LLM evaluation, based on quality score and inter-annotator agreement.

```python
def route_by_quality(items: list[DeduplicatedItem]):
    auto_applied = []
    auto_rejected = []
    to_evaluate = []

    for item in items:
        # High-confidence cluster: majority agreement, high quality
        if item.representative.quality_score >= 0.95 and item.cluster_size >= 3:
            auto_applied.append(item)    # Apply directly, bypass LLM

        # Low-quality / noisy: reject without LLM
        elif item.representative.quality_score < 0.20:
            auto_rejected.append(item)

        # Ambiguous: send to LLM evaluation
        else:
            to_evaluate.append(item)

    return auto_applied, auto_rejected, to_evaluate
```

### 4.4 Batch LLM Evaluation (25 Items Per Call)

The core token optimisation. 25 feedback items are evaluated in a single LLM call. System prompt, graph context, and few-shot examples are amortised across all 25.

```python
async def evaluate_batches(items: list[DeduplicatedItem]) -> list[CorrectionRecommendation]:
    batch_size = 25
    all_corrections = []

    for batch in chunk(items, batch_size):
        # Fetch graph context once for the whole batch
        affected_entities = extract_entity_ids(batch)
        graph_context = await get_graph_snapshot(affected_entities)  # cached 1h in Redis

        # Fetch few-shot examples once (cached in Redis, no re-computation)
        few_shot = await get_few_shot_examples(batch[0].representative.feedback_type)

        # Build the prompt — system prompt amortised across 25 items
        prompt = build_batch_evaluation_prompt(
            batch=batch,
            graph_context=graph_context,
            few_shot_examples=few_shot,
            output_schema=CORRECTION_JSON_SCHEMA,
        )

        # Single LLM call for 25 items
        response = await llm.call(
            prompt=prompt,
            max_tokens=get_budget(batch),  # token band B0–B5
            response_format={"type": "json_object"},
        )

        corrections = parse_correction_response(response, batch)
        all_corrections.extend(corrections)

    return all_corrections
```

**Token cost comparison:**

| Approach | Tokens/Item | For 500 Items |
|---|---|---|
| Naive (1 call/item) | ~2,100 | ~1,050,000 |
| Batch (25/call) | ~630 | ~315,000 |
| + Deduplication (−40%) | ~378 | ~189,000 |
| + Shared context | ~189 | ~94,500 |
| **Combined** | **~188** | **~94,000** |
| **Saving** | **91%** | **~956,000 tokens saved** |

### 4.5 LLM Prompt Structure

The prompt follows a strict structure to maximise token efficiency and minimise LLM hallucination:

```
SYSTEM (amortised across all 25 items):
  You are an evaluation system for an AMC (asset management company) chatbot.
  Your task: assess whether user feedback indicates a genuine knowledge graph correction.
  Domain: mutual funds (India/US/EU/UK).
  Output format: JSON only, no explanations, no markdown.
  Output schema: [provided as JSON Schema]
  Evaluation criteria: [concise rules, deterministic where possible]

FEW-SHOT (retrieved from Redis, cached per feedback_type):
  Example 1: { input: ..., output: ... }
  Example 2: { input: ..., output: ... }

BATCH (25 items, one per JSON object):
  [
    { "feedback_id": "...", "comment": "...", "entity": "...", "current_graph_state": {...} },
    ...
  ]

USER:
  Evaluate all 25 items. Return a JSON array of corrections.
```

### 4.6 Graph Correction Application

```python
async def apply_corrections(corrections: list[CorrectionRecommendation]):
    applied = []
    for correction in corrections:
        # Only apply if confidence exceeds threshold
        if correction.confidence_score < 0.85:
            await mark_rejected(correction, reason="below_confidence_threshold")
            continue

        # Validate the Cypher mutation before execution
        if not validate_cypher(correction.cypher_mutation):
            await mark_rejected(correction, reason="invalid_cypher")
            continue

        # Execute in Neo4j atomic transaction
        try:
            async with neo4j.transaction() as tx:
                # Capture before state for rollback
                before = await tx.run(get_before_state_query(correction))

                # Apply mutation
                await tx.run(correction.cypher_mutation)

                # Capture after state
                after = await tx.run(get_after_state_query(correction))

                # Write audit record
                await write_audit_trail(tx, correction, before, after)

            await mark_applied(correction)
            applied.append(correction)

        except Exception as e:
            await mark_failed(correction, str(e))

    return applied
```

---

## 5. Token Optimisation Summary

All seven strategies apply in combination. The order of application matters:

| Strategy | When Applied | Token Impact |
|---|---|---|
| **1. Quality pre-filter** | Before any evaluation | −60% items reach LLM |
| **2. Semantic deduplication** | After pre-filter | −40% of remaining items |
| **3. Batch processing** | LLM call construction | −70% prompt tokens |
| **4. Shared graph context** | Per batch, cached | −50% context tokens |
| **5. Few-shot caching** | Per batch, Redis | −15% prompt tokens |
| **6. Structured JSON output** | LLM response format | −30% output tokens |
| **7. Incident short-circuit** | Before routing | −100% for matched items |

Applied sequentially, the combined effect is an 88–91% token reduction versus naive per-item evaluation.

---

## 6. Cache Invalidation After Graph Correction

After a correction is applied to Neo4j, dependent caches must be cleared surgically. Broad invalidation (clearing all caches) is too slow and disrupts unrelated queries.

```python
async def invalidate_caches(applied_corrections: list[CorrectionRecommendation]):
    for correction in applied_corrections:
        affected_entities = extract_affected_entities(correction)

        # 1. FAISS: remove and re-embed only affected chunks
        for entity_id in affected_entities:
            chunk_ids = await faiss_store.get_chunks_for_entity(entity_id)
            await faiss_store.remove_chunks(chunk_ids)
            # Chunks will be re-embedded on next retrieval request

        # 2. Redis: clear EvidencePack caches for responses using affected entities
        response_ids = await db.get_responses_using_entities(affected_entities)
        for response_id in response_ids:
            await redis.delete(f"evidence:{response_id}")

        # 3. Redis: clear graph context snapshots for affected entities
        for entity_id in affected_entities:
            await redis.delete(f"graph_context:{entity_id}")

        # 4. Entity resolver cache: clear alias mappings for affected entities
        await entity_resolver.invalidate(affected_entities)

        # 5. Neo4j traversal cache: clear cached paths through affected nodes
        await neo4j_cache.invalidate_paths_through(affected_entities)
```

---

## 7. Feedback State Machine

```
                     ┌──────────────────────────────┐
                     │                              │
     POST /feedback  │                              │
         ▼           │                              ▼
    ┌─────────┐      │   quality < 0.20        ┌──────────┐
    │ pending │──────┼────────────────────────►│ rejected │
    └────┬────┘      │                         └──────────┘
         │           │
         │ hourly cycle
         ▼           │
    ┌───────────┐    │   quality ≥ 0.95 &      ┌──────────┐
    │ evaluating│    │   cluster_size ≥ 3 ──► │  applied │
    └─────┬─────┘    │                         └────┬─────┘
          │          │   confidence < 0.85           │
          │          ├──────────────────────────►rejected      90 days
          │          │                                           ▼
          │          │   confidence ≥ 0.85         ┌──────────────┐
          └──────────┴──────────────────────────► │   archived   │
                                                   └──────────────┘
```

---

## 8. Monitoring and Alerting

| Metric | Threshold | Action |
|---|---|---|
| `feedback_capture_latency_p99` | > 500 ms | Alert: investigate endpoint |
| `pending_feedback_count` | > 2000 | Alert: evaluation cycle may be falling behind |
| `evaluation_cycle_duration_min` | > 10 min | Alert: batch size or LLM throughput issue |
| `correction_apply_failure_rate` | > 5% | Alert: Cypher validation or Neo4j issue |
| `quality_score_mean` | < 0.30 trending | Alert: possible feedback abuse |
| `llm_tokens_per_cycle` | > 200k | Alert: deduplication or routing not working |
| `rejected_rate` | > 80% | Warning: feedback quality degrading |

---

*Previous: [LLD-02 — Evidence Capture](./LLD-02-EVIDENCE-CAPTURE.md)*  
*Next: [LLD-04 — Evaluation Router](./LLD-04-EVALUATION-ROUTER.md)*


---

## 9. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Phase 2 — Synchronous Capture: Full Sub-Component Timing

| Sub-Component | File | Sync/Async | Latency | LLM? | Output |
|---|---|---|---|---|---|
| Input Validator | `feedback.py` | Sync | ~1ms | No | 400/404 on fail, proceed on pass |
| feedback_id Generator | `feedback.py` | Sync | ~0ms | No | UUID v4 |
| PostgreSQL INSERT | `postgres_client.py` | Async (non-blocking) | ~5ms bg | No | feedback_records row with status='pending' |
| HTTP 202 Response | `feedback.py` | Sync | ~0ms | No | {feedback_id, status, evaluation_status} |
| NER Tagger (spaCy) | `feedback_collector.py` | BackgroundTask | ~20ms | No | ner_tags JSONB |
| Sentiment Scorer (VADER) | `feedback_collector.py` | BackgroundTask | ~5ms | No | sentiment JSONB {compound, neg, pos, neu} |
| Intent Classifier | `feedback_collector.py` | BackgroundTask | ~2ms | No | intent VARCHAR |
| Quality Score Engine | `feedback_collector.py` | BackgroundTask | ~1ms | No | quality_score FLOAT [0,1] |
| PostgreSQL UPDATE | `postgres_client.py` | BackgroundTask | ~5ms | No | classification_status='complete' |

**Total synchronous path: < 10ms** (excluding network). Classification completes in background 30–50ms after HTTP response is already sent.

### Phase 4 — Orchestration: Step-by-Step Internals

| Step | Component | Input | Output | Token Cost | Latency |
|---|---|---|---|---|---|
| 1 | Pending Feedback Fetcher | `status='pending', classification_status='complete'` | ≤500 enriched items with D2 join | 0 | ~200ms |
| 2 | Evidence Enricher | feedback_records + evidence_packs | items with frozen D2 attached | 0 | ~100ms |
| 3 | Aggregation Engine | enriched items | grouped by entity+correction_type | 0 | ~50ms |
| 4 | Semantic Deduplicator | aggregated groups | representative per cluster + vote counts | 0 (local model) | ~500ms |
| 5 | Conditional Router | deduplicated items + quality_scores | 3 lanes: auto_apply, auto_reject, to_evaluate | 0 | ~10ms |
| 6 | Batch Builder | to_evaluate items | batches of 25 with graph_ctx + few_shot | 0 | ~200ms |
| 7 | Batch LLM Evaluator | batches | correction_recommendations | Controlled (B2–B3) | ~60s for 20 batches |
| 8 | Graph Correction Applier | approved corrections (conf ≥ 0.85) | applied Neo4j mutations + audit trail | 0 | ~2s |
| 9 | Cache Invalidation | applied correction entity IDs | cleared FAISS/Redis/resolver/Neo4j caches | 0 | ~500ms |
| 10 | Cleanup + Metrics | all processed items | archived records, evaluation_jobs final counts | 0 | ~100ms |

**Total for 500 items: ~3 minutes** with all optimisations.

### Quality Score Formula — Complete Specification

```
base_score = 0.50

# Positive modifiers
+0.20  comment present AND length > 20 characters
+0.15  named entity extracted from comment (ner_tags not empty)
+0.10  correction text field present (feedback.correction is not None)
+0.10  highlighted_span present in request

# Negative modifiers
-0.30  rating is extreme (1 or 5) AND comment is absent
-0.40  sentiment.compound > 0.8 AND rating < 3 (sentiment-rating conflict)
-0.50  duplicate detected (same session_id + same response_id within 5 minutes)

# Clamped to [0.0, 1.0]

# Routing thresholds
quality_score < 0.20        → status = 'rejected', skip evaluation
quality_score >= 0.95 AND cluster_size >= 3 → auto_apply (bypass LLM)
0.20 <= quality_score < 0.95 → status = 'pending', enter evaluation queue
```

### Monitoring Alert Thresholds

| Metric | Alert Threshold | Likely Cause | Action |
|---|---|---|---|
| `feedback_capture_latency_p99` | > 500ms | Database overload or validator bottleneck | Scale PG connection pool |
| `pending_feedback_count` | > 2,000 | Evaluation cycle falling behind | Increase batch size or reduce cron interval |
| `evaluation_cycle_duration_min` | > 10 min | LLM throughput or batch size issue | Check LLM API quota, reduce batch size to 15 |
| `correction_apply_failure_rate` | > 5% | Cypher validation errors or Neo4j contention | Review generated Cypher, check Neo4j health |
| `quality_score_mean` | < 0.30 (trending) | Possible feedback abuse or spam | Activate abuse detection rules |
| `llm_tokens_per_cycle` | > 200k | Deduplication or routing not working | Check Sentence Transformer model, routing thresholds |
| `rejected_rate` | > 80% | Feedback quality degrading | Review quality score formula, check UI |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Phase 2, Phase 3, Phase 4 tabs for interactive component cards.*
