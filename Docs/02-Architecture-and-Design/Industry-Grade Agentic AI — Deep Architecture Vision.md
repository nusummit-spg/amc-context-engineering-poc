# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Industry-Grade Agentic AI — Deep Architecture Vision
### From Document Q&A → Autonomous Knowledge Platform

> **The Fundamental Shift**: Today the system is a *sophisticated RAG pipeline with a UI on top*. 
> An industry-grade agentic solution is fundamentally different: it **plans**, **acts**, **reflects**, **learns**, and **monitors** — all without being prompted to do so.

---

## The Gap: What "Agentic" Actually Means

```
CURRENT SYSTEM (Reactive RAG Pipeline):
  User query → Fixed pipeline → Answer
  
  Every query follows the same path:
  NER → Cache → Embed → [Graph || Vector] → Rerank → LLM → Answer
  
  The system cannot: change its strategy mid-query, decompose problems,
  use multiple retrieval rounds, evaluate its own answer, or work without a query.

INDUSTRY-GRADE AGENTIC SYSTEM:
  User query → Planner → Dynamic tool selection → Multi-round execution
              → Self-critique → Answer (+ proactive monitoring in background)
  
  The system CAN: decide it needs to run 3 sub-queries to answer 1 question,
  recognize when its answer is probably wrong, escalate to a human,
  monitor documents for changes without being asked.
```

---

# Part 1: The Agentic Core — Planner + Executor + Critic

## 1.1 Query Decomposition & Dynamic Planning

**Current**: `query_classifier.py` maps a query to exactly ONE category: aggregation/comparison/lookup/open_ended. One strategy per query, always.

**Problem**: Consider this query from a compliance officer:
> *"Compare the carbon emission reduction commitments of the top 3 ESG-rated AMCs in our corpus, factoring in their current SEBI categorization and whether any have received regulatory notices in the past year."*

This requires:
1. Find which AMCs have ESG ratings → `direct_lookup` × N
2. Rank them → `aggregation`
3. Pull their SEBI categorization → `lookup` per AMC
4. Check for regulatory notices → `graph traversal` per AMC
5. Synthesize comparison → `comparison` with 4 sub-results

A single-path classifier cannot handle this. A planner can.

**Implementation — `agent_planner.py`**:
```python
"""
agent_planner.py
================
Decomposes complex queries into a structured plan of sub-tasks.
Each sub-task is a tool call with specific parameters.
The executor runs sub-tasks sequentially or in parallel.
The critic evaluates the assembled result before returning.
"""

PLANNING_PROMPT = """
You are a research planner for a financial document AI system.
Given a complex question, break it into ordered sub-tasks.

Available tools:
  - graph_lookup(entity, attribute): Get a specific fact from knowledge graph
  - vector_search(query, top_k): Semantic search over document corpus
  - aggregate(cypher_description): Compute a numeric aggregate from graph
  - compare(entity_list, attribute): Compare multiple entities on one attribute
  - text_to_cypher(nl_query): Convert a natural language query to graph query

Question: {query}
Corpus domains: {domain_list}
Known entities: {known_entities}

Return a JSON plan:
{{
  "complexity": "simple|moderate|complex",
  "sub_tasks": [
    {{"id": 1, "tool": "graph_lookup", "params": {{"entity": "...", "attribute": "..."}}, "depends_on": []}},
    {{"id": 2, "tool": "compare", "params": {{"entity_list": ["...", "..."], "attribute": "..."}}, "depends_on": [1]}}
  ],
  "synthesis_strategy": "table|prose|mixed"
}}
"""

class AgentPlanner:
    def plan(self, query: str, context: dict) -> ExecutionPlan:
        """Decompose query into sub-tasks with dependency graph."""
        raw = llm_text_client.call_llm_json(PLANNING_PROMPT.format(
            query=query,
            domain_list=context["domains"],
            known_entities=context["entities"][:20]
        ))
        return ExecutionPlan.from_dict(raw)

    def should_plan(self, query: str) -> bool:
        """Only invoke planner for genuinely complex queries."""
        complexity_signals = [
            "compare" in query.lower() and ("and" in query.lower() or "versus" in query.lower()),
            query.count("?") > 1,      # multi-part question
            len(query.split()) > 30,   # long = likely complex
            bool(re.search(r"\b(top \d|rank|best|worst)\b", query, re.I)),
        ]
        return sum(complexity_signals) >= 2
```

---

## 1.2 Multi-Round Adaptive Retrieval

**Current**: Retrieval runs exactly once per query. If the first round finds nothing, the LLM says "I don't know" — even though a second retrieval round with different entity resolution might have found the answer.

**Implementation — Retrieval Loop with Reflection**:
```python
class AdaptiveRetriever:
    MAX_ROUNDS = 3
    
    def retrieve(self, query: str, query_vec, plan: ExecutionPlan) -> RetrievalResult:
        round_num = 0
        accumulated_context = []
        reflection_feedback = None
        
        while round_num < self.MAX_ROUNDS:
            # Round 1: standard retrieval
            # Round 2: if round 1 weak → expand entity search, relax thresholds
            # Round 3: if round 2 weak → cross-document graph traversal
            
            if round_num == 0:
                result = self._primary_retrieval(query, query_vec)
            elif round_num == 1 and reflection_feedback == "insufficient":
                result = self._expanded_retrieval(query, query_vec, 
                    relax_threshold=0.35,  # down from 0.45
                    extra_hops=1)
            elif round_num == 2:
                result = self._cross_document_retrieval(query,
                    entity_expansion=True)
            
            accumulated_context.extend(result.chunks)
            
            # Self-assess context sufficiency before calling LLM
            quality = self._assess_context_quality(
                query=query,
                context=accumulated_context,
                min_relevant_chunks=2,
                min_entity_coverage=0.5
            )
            
            if quality.is_sufficient:
                break
                
            reflection_feedback = quality.feedback
            round_num += 1
        
        return RetrievalResult(chunks=accumulated_context, rounds=round_num)
    
    def _assess_context_quality(self, query, context, **thresholds) -> Quality:
        """
        Fast heuristic check — no LLM call.
        Checks: entity coverage, chunk relevance scores, knowledge gap signals.
        """
        query_entities = set(e["text"] for e in ner_pipeline.run_layers_ab(query))
        context_text = " ".join(c.get("parent_text","") for c in context)
        
        covered = sum(1 for e in query_entities if e.lower() in context_text.lower())
        coverage = covered / max(len(query_entities), 1)
        
        gap_signals = ["not found", "no information", "not available"]
        has_gap = any(g in context_text.lower() for g in gap_signals)
        
        return Quality(
            is_sufficient=(coverage >= thresholds["min_entity_coverage"] and not has_gap),
            feedback="insufficient" if coverage < 0.5 else "partial"
        )
```

---

## 1.3 Self-Critique Before Response (LLM-as-Judge)

**Current**: The system returns whatever the LLM generates. There is no verification step.

**The Risk**: An LLM confidently stating an incorrect SEBI investment limit (e.g., "15%" instead of "10%") in a compliance context has real-world consequences.

**Implementation — `answer_critic.py`**:
```python
"""
answer_critic.py
================
After LLM generates an answer, a lightweight critic model evaluates it.
Only triggered for high-stakes query types (direct_lookup, aggregation).
Uses a separate, cheaper model call — not the same model (avoid self-confirmation bias).
"""

CRITIC_PROMPT = """
You are a strict fact-checker reviewing an AI-generated answer.
Check the answer against the provided source context.

SOURCE CONTEXT (ground truth):
{context}

GENERATED ANSWER:
{answer}

ORIGINAL QUESTION:
{query}

Evaluate:
1. Are all numeric claims in the answer supported by the context? (yes/no + which ones)
2. Are entity names correct? (yes/no + corrections if needed)
3. Is anything stated as fact but NOT present in the context? (yes/no + what)
4. Overall verdict: APPROVE / FLAG / REJECT

Return JSON: {{"verdict": "APPROVE|FLAG|REJECT", "issues": [...], "corrected_answer": "..."}}
"""

class AnswerCritic:
    TRIGGER_TYPES = {"direct_lookup", "aggregation"}  # highest factual stakes
    
    def critique(self, query: str, answer: str, context: str, query_type: str) -> CritiqueResult:
        if query_type not in self.TRIGGER_TYPES:
            return CritiqueResult(verdict="APPROVE", answer=answer)
        
        if len(answer) < 50:  # too short to critique usefully
            return CritiqueResult(verdict="APPROVE", answer=answer)
        
        result = llm_text_client.call_llm_json(
            CRITIC_PROMPT.format(context=context[:3000], answer=answer, query=query),
            model_id=config.CLAUDE_MODEL_LIGHT  # lightweight model
        )
        
        verdict = result.get("verdict", "APPROVE")
        issues = result.get("issues", [])
        corrected = result.get("corrected_answer", answer)
        
        # Log critic findings to audit log (always)
        _log_critic_finding(query, verdict, issues, corrected)
        
        if verdict == "REJECT":
            return CritiqueResult(verdict="REJECT", answer=corrected, 
                                  flagged=True, issues=issues)
        if verdict == "FLAG":
            # Return original but append a transparency note
            disclaimer = f"\n\n⚠️ *Confidence note: {'; '.join(issues)}*"
            return CritiqueResult(verdict="FLAG", answer=answer + disclaimer,
                                  flagged=True, issues=issues)
        
        return CritiqueResult(verdict="APPROVE", answer=answer)
```

**Impact**: Catches hallucinated numbers (the most dangerous error type in compliance) before they reach the user. A second model reviewing the first model's work is standard in medical/legal AI systems.

---

## 1.4 Human-in-the-Loop Escalation

**Current**: Every answer is returned directly to the user, regardless of confidence.

**Pattern**: When confidence < threshold OR critic flags → route to human review queue.

```python
# In retrieval.py hybrid_graphrag():

critique = answer_critic.critique(query, raw_answer, context_str, query_type)
conf_label, conf_reason = calibrate_confidence(hits, graph_result, domain_intent)

# Human-in-the-loop trigger
if (critique.verdict == "FLAG" or conf_label == "low confidence") \
   and config.ENABLE_HUMAN_REVIEW:
    review_id = human_review_queue.submit(
        query=query,
        answer=critique.answer,
        confidence=conf_label,
        issues=critique.issues,
        context_snippets=[h["parent_text"][:200] for h in hits[:3]],
        urgency="high" if query_type == "aggregation" else "normal"
    )
    return {
        "answer": f"This answer has been flagged for expert review (ID: {review_id}). "
                  f"Preliminary response: {critique.answer}",
        "confidence_label": f"PENDING_REVIEW ({conf_label})",
        "review_id": review_id,
        ...
    }
```

**What `human_review_queue` does**:
- Stores pending reviews in a `reviews.jsonl` file (or Redis queue)
- A separate "Review" tab in the UI shows pending reviews to designated reviewers
- Reviewer can: Approve as-is, Edit + Approve, Reject with comment
- Approved answers go into the intent cache as high-confidence gold entries
- Over time, the review queue shrinks as the cache fills with validated answers

---

# Part 2: Multi-Agent Panel for High-Stakes Answers

## The Pattern: Adversarial Collaboration

For queries where a single agent's answer is insufficient (regulatory compliance, investment decisions), use multiple specialized agents that challenge each other.

```
Query: "Can a mutual fund scheme hold more than 25% in a single sector under SEBI regulations?"
  │
  ├─► Agent 1 (Retrieval Expert): Searches corpus, returns answer with citations
  ├─► Agent 2 (Devil's Advocate): Challenges Agent 1's answer — looks for contradictions
  ├─► Agent 3 (Synthesizer): Weighs both, resolves conflicts, writes final answer
  │
  Panel vote → if consensus → HIGH CONFIDENCE
             → if split → FLAG FOR HUMAN REVIEW
```

**Implementation — `agent_panel.py`**:
```python
class AgentPanel:
    """
    Runs 2-3 independent retrieval + reasoning agents and synthesizes their outputs.
    Only invoked for: aggregation, comparison, and direct_lookup on regulatory topics.
    Cost: ~3× single-agent LLM cost. Time: ~same as single agent (parallel execution).
    """
    
    def run_panel(self, query: str, context: str, query_type: str) -> PanelResult:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            # Agent 1: Answer directly from context
            f1 = pool.submit(self._primary_agent, query, context)
            # Agent 2: Answer but look for caveats, exceptions, amendments
            f2 = pool.submit(self._skeptic_agent, query, context)
            # Agent 3: Synthesize + resolve conflicts
            a1 = f1.result()
            a2 = f2.result()
        
        a3 = self._synthesizer_agent(query, a1, a2, context)
        
        agreement = self._compute_agreement(a1, a2)
        
        return PanelResult(
            final_answer=a3,
            agent_answers=[a1, a2],
            agreement_score=agreement,
            confidence="high" if agreement > 0.8 else "medium" if agreement > 0.5 else "low",
        )
    
    def _skeptic_agent(self, query: str, context: str) -> str:
        prompt = (
            f"You are a strict regulatory compliance reviewer. "
            f"Answer the question, but actively look for: "
            f"(1) exceptions to the general rule, "
            f"(2) recent amendments that change the answer, "
            f"(3) scenarios where the answer differs.\n\n"
            f"Context: {context}\n\nQuestion: {query}\n\nAnswer:"
        )
        return llm_text_client.call_llm(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
```

**Why this is differentiating**: Financial services firms use "four-eyes" review as a standard practice. An AI system that has an internal equivalent of four-eyes review — where one agent challenges another — is more defensible in a regulatory audit than a single-agent system.

---

# Part 3: Persistent Agent Memory

## The Three Memory Layers

```
SHORT-TERM MEMORY (existing — conversation history, 4-6 turns):
  In session_state. Cleared on page reload.

MEDIUM-TERM MEMORY (missing — learned query patterns):
  What topics does THIS user ask about most?
  Which answers did they find useful (thumbs up)?
  What queries did they refine (suggesting the first answer was wrong)?
  
LONG-TERM MEMORY (missing — organizational knowledge):
  Which document chunks were most cited in accepted answers?
  Which entities appear in >80% of queries? (candidate for pre-caching)
  What knowledge gaps does the corpus have? (queries with low confidence)
```

**Implementation — `agent_memory.py`**:
```python
"""
agent_memory.py
================
Three-layer persistent memory for the agentic system.
Stored in SQLite (local) or PostgreSQL (production).
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime

class AgentMemory:
    
    # ── Episodic Memory: session-level patterns ────────────────────────────
    def remember_query(self, user_id: str, query: str, answer: str, 
                       quality: str, domain: str, tokens: int):
        """Store every Q&A pair with outcome for learning."""
        self.db.execute("""
            INSERT INTO episodic_memory 
            (user_id, query, answer, quality, domain, tokens, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, query, answer, quality, domain, tokens, datetime.now()))
    
    # ── Semantic Memory: cross-session knowledge ───────────────────────────
    def get_user_domain_profile(self, user_id: str) -> dict:
        """What domains does this user query most? Used to pre-warm cache."""
        rows = self.db.execute("""
            SELECT domain, COUNT(*) as freq
            FROM episodic_memory WHERE user_id = ?
            GROUP BY domain ORDER BY freq DESC
        """, (user_id,)).fetchall()
        return {r["domain"]: r["freq"] for r in rows}
    
    def get_frequent_queries(self, domain: str, min_count: int = 5) -> list[str]:
        """Queries asked >5 times = candidates for pre-computed answers."""
        return self.db.execute("""
            SELECT query, COUNT(*) as cnt
            FROM episodic_memory WHERE domain = ?
            GROUP BY query HAVING cnt >= ?
            ORDER BY cnt DESC LIMIT 20
        """, (domain, min_count)).fetchall()
    
    # ── Procedural Memory: system-level learning ──────────────────────────
    def record_chunk_citation(self, chunk_id: str, query_id: str, quality: str):
        """Track which chunks lead to good answers — for future re-ranking."""
        self.db.execute("""
            INSERT INTO chunk_citations (chunk_id, query_id, quality, ts)
            VALUES (?, ?, ?, ?)
        """, (chunk_id, query_id, quality, datetime.now()))
    
    def get_chunk_quality_score(self, chunk_id: str) -> float:
        """Return historical quality score for a chunk — boosts re-ranking."""
        row = self.db.execute("""
            SELECT AVG(CASE quality WHEN 'good' THEN 1.0 WHEN 'ok' THEN 0.5 ELSE 0.0 END)
            FROM chunk_citations WHERE chunk_id = ?
        """, (chunk_id,)).fetchone()
        return float(row[0] or 0.5)
    
    # ── Knowledge Gap Detection ────────────────────────────────────────────
    def get_knowledge_gaps(self) -> list[dict]:
        """Queries with consistently low confidence = corpus knowledge gaps."""
        return self.db.execute("""
            SELECT query, AVG(confidence_score) as avg_conf, COUNT(*) as freq
            FROM episodic_memory
            WHERE confidence_score < 0.5 AND freq >= 3
            GROUP BY query ORDER BY freq DESC
        """).fetchall()
```

**Why this matters**: A system that remembers which topics a compliance team asks about can:
- Pre-warm the cache with those queries every morning (before the team arrives)
- Surface knowledge gaps proactively ("You've asked about REIT investment limits 8 times this month, but our confidence is consistently low — suggest indexing the SEBI REIT circular")
- Rank chunks higher that have historically led to good answers

---

# Part 4: Proactive Monitoring Agent

**Current**: System is 100% reactive — it only works when a user submits a query.

**Vision**: Background agents that monitor for events and proactively surface insights.

```python
# agent_monitor.py — runs as a background scheduled task

class RegulatoryMonitorAgent:
    """
    Scheduled agent (daily) that:
    1. Checks SEBI website for new circulars (via web search or RSS)
    2. Detects if any indexed document has a newer version available
    3. Runs golden-set evaluation and alerts if accuracy drops
    4. Pre-computes answers to the 20 most-asked queries and stores in cache
    """
    
    def daily_run(self):
        self._check_regulatory_changes()
        self._refresh_frequent_query_cache()
        self._run_accuracy_check()
        self._detect_document_staleness()
    
    def _check_regulatory_changes(self):
        """
        Web search for 'SEBI circular mutual fund 2026' in last 7 days.
        If a new circular is found that mentions any indexed document's topic,
        send a Streamlit notification / email alert to admin.
        """
        ...
    
    def _refresh_frequent_query_cache(self):
        """
        Get top 20 queries from agent_memory.get_frequent_queries().
        Run them through the full pipeline during off-hours.
        Store results in intent_cache — ready for instant response next morning.
        """
        memory = AgentMemory()
        for domain in DOMAIN_PATTERNS:
            top_queries = memory.get_frequent_queries(domain, min_count=3)
            for q in top_queries:
                result = hybrid_graphrag(q["query"])
                # Already stored in intent_cache by hybrid_graphrag
                print(f"Pre-warmed cache: '{q['query'][:50]}'")
    
    def _detect_document_staleness(self):
        """
        For each indexed document, compute 'staleness score':
        - days since last indexed
        - query frequency (high query rate = users care about it)
        - document type TTL (daily NAV vs annual report)
        Alert admin for documents that are stale + high-query-rate.
        """
        ...
```

---

# Part 5: Production Engineering — Enterprise-Grade

## 5.1 Circuit Breaker Pattern

**Current**: If Neo4j goes down, every query waits for timeout (10-30s) before failing.

```python
# circuit_breaker.py
from enum import Enum
import time

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing — skip fast
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    """
    Neo4j Circuit Breaker:
    - If 5 consecutive failures → OPEN (fast-fail, skip graph retrieval)
    - After 60s → HALF_OPEN (try one request)
    - If success → CLOSED (normal operation resumes)
    """
    def __init__(self, name: str, failure_threshold=5, recovery_timeout=60):
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
    
    def call(self, fn, *args, fallback=None, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                print(f"[CircuitBreaker:{self.name}] Testing recovery...", flush=True)
            else:
                print(f"[CircuitBreaker:{self.name}] OPEN — fast-fail to fallback", flush=True)
                return fallback() if fallback else None
        
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            if fallback:
                return fallback()
            raise
    
    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self, e):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            print(f"[CircuitBreaker:{self.name}] OPENED after {self.failure_count} failures", flush=True)

# Usage in retrieval.py:
neo4j_breaker = CircuitBreaker("neo4j")
graph_result = neo4j_breaker.call(
    graph_store.get_subgraph_for_query,
    query, entity_texts,
    fallback=lambda: {"edges": [], "matched_by": "circuit_breaker_fallback"}
)
```

**Impact**: When Neo4j is down for maintenance, the system degrades to vector-only mode (still useful) instead of showing errors or hanging for 30 seconds.

---

## 5.2 Immutable Audit Trail (Regulatory Grade)

**Current**: JSONL audit logs are appended to a file — can be edited or deleted.

**Financial Services Requirement**: SEBI and DPDP require audit trails that are tamper-proof. An AI system that provides investment-adjacent information must be able to prove what it said, when, and based on what context.

```python
# audit_chain.py — Blockchain-style audit trail using hash chaining
import hashlib, json

class ImmutableAuditLog:
    """
    Each log entry contains a hash of the previous entry.
    Any tampering with a past entry breaks the chain — detectable.
    This is the same principle as a blockchain, without the distributed consensus overhead.
    """
    
    def append(self, entry: dict) -> str:
        # Get previous hash
        prev_hash = self._get_last_hash()
        
        # Build this entry
        entry_with_meta = {
            **entry,
            "prev_hash": prev_hash,
            "timestamp": time.time_ns(),  # nanosecond precision
            "schema_version": "1.0",
        }
        
        # Compute this entry's hash
        content = json.dumps(entry_with_meta, sort_keys=True, default=str)
        current_hash = hashlib.sha256(content.encode()).hexdigest()
        entry_with_meta["entry_hash"] = current_hash
        
        # Append to WORM (Write-Once) log
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry_with_meta) + "\n")
        
        return current_hash
    
    def verify_chain(self) -> tuple[bool, int]:
        """Verify the entire audit chain is intact. Run periodically."""
        entries = self._load_all()
        for i, entry in enumerate(entries[1:], 1):
            expected_prev = entries[i-1]["entry_hash"]
            if entry["prev_hash"] != expected_prev:
                return False, i  # Chain broken at entry i
        return True, len(entries)
```

**What this logs** (for every query):
- Exact query text (post-PII scrub)
- Exact context sent to LLM (graph edges + vector chunks)
- Exact LLM response (pre and post compliance filter)
- Critic verdict + issues
- User identity (if multi-tenant)
- Model used + version
- All timing data
- Chain hash (tamper-evident)

---

## 5.3 Structured Output Mode (Machine-Readable Answers)

**Current**: All answers are unstructured prose.

**Enterprise Need**: Systems integrating this AI into their own pipelines need structured JSON output, not prose.

```python
# In retrieval.py:

STRUCTURED_SCHEMAS = {
    "direct_lookup": {
        "entity": str,
        "attribute": str,
        "value": str,
        "unit": Optional[str],
        "as_of_date": Optional[str],
        "source_document": str,
        "source_page": int,
        "confidence": float,
    },
    "comparison": {
        "entities": list[str],
        "attribute": str,
        "values": dict[str, str],  # entity → value
        "winner": Optional[str],
        "source_documents": list[str],
        "confidence": float,
    },
    "aggregation": {
        "metric": str,
        "total": str,
        "breakdown": list[dict],
        "methodology": str,
        "confidence": float,
    }
}

def hybrid_graphrag(query: str, ..., output_format: str = "prose") -> dict:
    # ... retrieval ...
    
    if output_format == "structured":
        schema = STRUCTURED_SCHEMAS.get(query_type)
        if schema:
            structured = _extract_structured(raw_answer, schema, context)
            return {**result, "structured_output": structured}
    
    return result
```

**Why this is powerful**: A compliance software vendor integrating this system can directly parse the `structured_output` into their database, without NLP post-processing of prose answers.

---

## 5.4 Blue-Green Index Deployment

**Current**: When a new document is added, the FAISS index is rebuilt and the app uses the new index immediately — during this period, retrieval is degraded or unavailable.

```python
# faiss_store.py enhancement

class IndexManager:
    """
    Manages blue (active) and green (building) indexes.
    Switch is atomic — no downtime during rebuilds.
    """
    
    def __init__(self, indexes_dir: Path):
        self.indexes_dir = indexes_dir
        self.active_color = self._read_active_color()  # "blue" or "green"
    
    @property
    def active_index_path(self) -> Path:
        return self.indexes_dir / self.active_color
    
    @property
    def build_index_path(self) -> Path:
        return self.indexes_dir / ("green" if self.active_color == "blue" else "blue")
    
    def start_background_build(self, pdf_path: str) -> str:
        """Build new index in the inactive slot."""
        build_path = self.build_index_path
        # ... build in build_path ...
        return f"Building in {build_path}"
    
    def promote_build(self):
        """Atomically switch active from blue to green."""
        new_color = "green" if self.active_color == "blue" else "blue"
        self._write_active_color(new_color)
        self.active_color = new_color
        print(f"[IndexManager] Promoted {new_color} index — zero downtime", flush=True)
        # Invalidate intent cache for affected domains
        intent_cache.get_cache().clear_all()
```

---

# Part 6: Financial Services-Specific Intelligence

## 6.1 Regulatory Change Diff Engine

**The Most Unique Feature Possible**:
```
User uploads SEBI Master Circular 2025 (updated version).
System automatically:
  1. Detects it's an update of an already-indexed circular
  2. Computes diff: which clauses changed, which are new, which were removed
  3. Extracts the specific changes as entities: "investment_limit: 10% → 15%"
  4. Updates the knowledge graph with the new values (not replaces — keeps history)
  5. Notifies subscribed users: "SEBI Circular updated: 3 rules changed"
  6. Answers: "What changed in the latest SEBI circular?" from the diff, not from prose
```

```python
# regulatory_diff.py
class RegulatoryDiffEngine:
    def compute_diff(self, old_doc_id: str, new_pdf_path: str) -> RegulatoryDiff:
        old_entities = graph_store.get_all_entities_for_document(old_doc_id)
        new_entities = self._extract_entities_from_pdf(new_pdf_path)
        
        changed = []
        for entity in new_entities:
            old = next((e for e in old_entities 
                       if e["text"] == entity["text"] and e["attribute"] == entity["attribute"]), None)
            if old and old["value"] != entity["value"]:
                changed.append({
                    "entity": entity["text"],
                    "attribute": entity["attribute"],
                    "old_value": old["value"],
                    "new_value": entity["value"],
                    "change_type": "MODIFIED"
                })
        
        return RegulatoryDiff(changes=changed, circular_id=new_pdf_path)
```

---

## 6.2 Bias & Fairness Monitoring

**Regulatory Requirement**: If an AI system consistently gives better answers about certain AMCs over others, it could constitute a form of informational bias in financial services.

```python
# bias_monitor.py
class FairnessMonitor:
    """
    Tracks whether the system has differential quality across entities.
    E.g., does it give higher confidence answers about HDFC AMC vs SBI AMC?
    """
    
    def analyze_entity_bias(self, audit_logs: list[dict]) -> BiasReport:
        entity_metrics = {}
        
        for log in audit_logs:
            for entity in log.get("ner_entities", []):
                name = entity["text"]
                if name not in entity_metrics:
                    entity_metrics[name] = {"confidence_scores": [], "hit_rates": []}
                entity_metrics[name]["confidence_scores"].append(log["confidence_score"])
                entity_metrics[name]["hit_rates"].append(1 if log["cache_hit"] else 0)
        
        # Detect statistical outliers
        all_scores = [s for m in entity_metrics.values() for s in m["confidence_scores"]]
        mean_conf, std_conf = np.mean(all_scores), np.std(all_scores)
        
        biased_entities = [
            name for name, m in entity_metrics.items()
            if len(m["confidence_scores"]) >= 10  # enough data
            and abs(np.mean(m["confidence_scores"]) - mean_conf) > 2 * std_conf
        ]
        
        return BiasReport(biased_entities=biased_entities, 
                         entity_metrics=entity_metrics)
```

---

## 6.3 RLHF-Style Feedback Loop (Self-Improving System)

**Current**: User gets an answer. That's the end of the interaction.

**With feedback loop**:
```
1. User gets answer → sees 👍/👎 buttons
2. User marks answer:
   - 👍 "Correct" → answer stored as a high-quality cache entry
   - 👎 "Wrong" → answer stored as a negative example
   - ✏️ "Edit" → user corrects the answer → stored as gold standard
3. Every 100 feedback events:
   - Re-rank chunks by historical quality score (procedural memory)
   - Adjust domain confidence calibration
   - Update entity resolver similarity thresholds
   - Generate a quality report: "This week, 87% of direct_lookup answers were marked correct"
```

```python
# feedback_processor.py
class FeedbackProcessor:
    def process_feedback(self, query_id: str, feedback: str, corrected_answer: str = None):
        log = self.audit_log.get_entry(query_id)
        
        if feedback == "correct":
            # Boost the retrieved chunks' quality scores
            for chunk_id in log["retrieved_chunk_ids"]:
                self.memory.record_chunk_citation(chunk_id, query_id, "good")
            # Store as gold cache entry with high TTL
            intent_cache.get_cache().store(..., ttl_override=86400*30)
        
        elif feedback == "wrong":
            # Penalize chunks
            for chunk_id in log["retrieved_chunk_ids"]:
                self.memory.record_chunk_citation(chunk_id, query_id, "bad")
            # Invalidate cache entry if it was a cache hit
            if log["cache_hit"]:
                intent_cache.get_cache().invalidate_entry(query_id)
        
        elif feedback == "edited" and corrected_answer:
            # Gold standard — store with maximum confidence
            self.memory.remember_query(
                query=log["query"],
                answer=corrected_answer,
                quality="gold",
                ...
            )
```

---

# Summary: The 10 Capabilities That Define Industry-Grade Agentic AI

| Capability | What It Means | Current Status | Priority |
|---|---|---|---|
| **1. Planning** | Decomposes complex multi-part queries | ❌ Single-pass | Foundational |
| **2. Multi-round Retrieval** | Adapts retrieval strategy based on initial results | ❌ One round only | High |
| **3. Self-Critique** | Second model validates first model's answer | ❌ No verification | High |
| **4. Persistent Memory** | Learns from every interaction across sessions | ❌ In-session only | High |
| **5. Multi-Agent Panel** | Multiple agents challenge each other | ❌ Single agent | Medium |
| **6. Human-in-the-Loop** | Escalates uncertain answers for human review | ❌ Fully automated | High |
| **7. Proactive Monitoring** | Background agent watches for changes | ❌ Fully reactive | Medium |
| **8. Circuit Breakers** | Graceful degradation when components fail | ❌ Hard failures | High |
| **9. Immutable Audit Trail** | Tamper-evident, regulatorily defensible logs | ❌ JSONL only | High |
| **10. Feedback Loop** | Gets smarter from every marked answer | ❌ No learning | Medium |

> **The system you have today is a sophisticated, well-engineered RAG system.**
> **The system described above is an autonomous knowledge agent.**
> 
> The difference: a RAG system answers questions.
> An autonomous agent *manages* knowledge — monitoring it, learning from interactions with it, and proactively surfacing what matters before being asked.
