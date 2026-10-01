# Passive Feedback System - Detailed Implementation Plan

**Document Version:** 1.0  
**Created:** January 2025  
**Status:** READY FOR IMPLEMENTATION  
**Priority:** P1 (High Business Value)  
**Estimated Timeline:** 5 days (2 developers)  
**Owner:** Backend Team

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Architecture Overview](#architecture-overview)
4. [Implementation Components](#implementation-components)
5. [Day-by-Day Implementation Plan](#day-by-day-implementation-plan)
6. [Testing Strategy](#testing-strategy)
7. [Deployment Plan](#deployment-plan)
8. [Monitoring & Observability](#monitoring--observability)
9. [Risk Assessment](#risk-assessment)
10. [Appendices](#appendices)

---

## Executive Summary

### Problem Statement

The current passive feedback implementation is **30% complete** with critical gaps:
- ✅ Manual follow-up detection API exists
- ✅ Skeleton ResponseFeedback records created
- ❌ No automatic triggering mechanism
- ❌ Timeout window (180s) configured but never enforced
- ❌ Zero automatic metrics captured in skeleton records
- ❌ No frontend integration

**Business Impact:** Capturing <5% of passive feedback opportunities. Most user corrections go undetected.

### Proposed Solution

Implement a **Session-Aware Passive Feedback Pipeline** with three automatic triggers:

| Trigger | Timeline | Action | Outcome |
|---------|----------|--------|---------|
| **New Query** | Within 180s of previous response | Auto-run follow-up detection | Correction detected or dismissed |
| **Explicit Feedback** | Anytime | User clicks feedback button | Already works ✅ |
| **Session Timeout** | After 180s with no activity | Enrich with automatic metrics | Mark as implicit satisfaction |

### Expected Outcomes

**Immediate (Week 1):**
- Passive feedback capture rate: 20-30% (from <5%)
- Automatic correction detection (no manual intervention)
- All skeleton records enriched with telemetry
- Query latency impact: <2ms

**Long-term (Month 2-3):**
- 10x increase in correction detection rate
- Rich dataset for ML training
- Implicit satisfaction signals captured
- Fully automated feedback-repair loop

### Resource Requirements

- **Team:** 2 Backend Developers (full-time, 5 days)
- **Infrastructure:** No new dependencies (Python stdlib + existing stack)
- **Testing:** 1 QA Engineer (part-time, Days 4-5)

---

## Current State Analysis

### What's Implemented (30%)

#### 1. Skeleton ResponseFeedback Creation
**Location:** `backend/app/api/routes/chat.py:258-304`

```python
# On every ContextGraph response
skeleton_feedback = ResponseFeedback(
    feedback_id=feedback_id,
    response_id=response_id,
    session_id=session_id,
    turn_number=turn_index,
    query_text=query,
    actor_id=None,              # ❌ NULL
    selected_categories=[],      # ❌ Empty
    feedback_text=None,          # ❌ NULL
    # All metric fields NULL:
    answer_relevance_score=None,
    automated_category=None,
    automated_confidence=None,
    response_text=None,
    response_summary=None,
)
```

**Status:** ✅ Works correctly  
**Gap:** No automatic metrics populated

#### 2. Manual Follow-Up Detection API
**Location:** `backend/app/api/routes/feedback.py:354-505`

**Endpoint:** `POST /api/feedback/follow-up-detection`

**Detection Pipeline:**
1. **Frustration Detection:** VADER sentiment analysis (threshold -0.35)
2. **Same Referent Check:** Entity/number/embedding match (threshold 0.75)
3. **Correction Language:** Regex patterns ("wrong", "actually", "not right")

**Decision Logic:**
```python
is_correction = (
    (is_frustrated and same_topic and has_correction_lang) 
    or 
    (has_correction_lang and same_topic and intent_confidence >= 0.70)
)
```

**Status:** ✅ Works correctly  
**Gap:** Never called automatically (requires explicit API call)

#### 3. DissatisfactionDetector
**Location:** `backend/app/feedback/dissatisfaction_detector.py:56-234`

Full correction detection logic with:
- Sentiment analysis (VADER)
- Embedding similarity (all-MiniLM-L6-v2)
- Pattern matching for correction phrases
- Structured claim extraction via CorrectionExtractor

**Status:** ✅ Production-ready  
**Gap:** Only invoked via manual API call

#### 4. Configuration
**Location:** `packages/amc-feedback-loop/src/amc_feedback/config.py:65-76`

```python
enable_passive_capture: bool = True
passive_timeout_seconds: int = 180  # ❌ Unused
```

**Status:** ✅ Defined  
**Gap:** Never enforced in any detection logic

### Critical Gaps (70%)

#### Gap 1: No Automatic Trigger Mechanism
**Impact:** 🔴 CRITICAL

**Missing:**
- Event listener on new query submission
- Background task monitoring sessions
- Integration with chat endpoint

**Required Implementation:**
- SessionManager to track query history
- Automatic detection trigger in `/api/chat`
- Non-blocking background execution

#### Gap 2: Timeout Window Not Enforced
**Impact:** 🟡 HIGH

**Missing:**
- Logic to enforce 180s detection window
- Session state tracking (last query timestamp)
- Expiration of detection eligibility

**Required Implementation:**
- Session timestamp tracking
- Age-based eligibility checks
- Cleanup of stale sessions

#### Gap 3: Zero Automatic Metrics Captured
**Impact:** 🟡 HIGH

**Missing:**
- Population of `automated_category`, `automated_confidence`
- Link to QueryEvidence telemetry (quality_score, latency, tokens)
- Implicit signals (dwell time, re-query patterns)

**Required Implementation:**
- MetricsEnricher component
- QueryEvidence → ResponseFeedback integration
- Quality categorization logic

#### Gap 4: QueryEvidence and ResponseFeedback Decoupled
**Impact:** 🟡 MEDIUM

**Current:** Two separate tables with `unified_record_ref` FK but never populated  
**Missing:** Integration pipeline to enrich ResponseFeedback with QueryEvidence data

---

## Architecture Overview

### System Components

```
┌──────────────────────────────────────────────────────────────────┐
│                     Passive Feedback Pipeline                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐      ┌──────────────────┐                     │
│  │              │      │                  │                     │
│  │  User Query  │─────▶│  Chat Endpoint   │                     │
│  │              │      │                  │                     │
│  └──────────────┘      └────────┬─────────┘                     │
│                                  │                               │
│                                  ▼                               │
│                        ┌──────────────────┐                     │
│                        │                  │                     │
│                        │ SessionManager   │                     │
│                        │  - Track queries │                     │
│                        │  - Check timeout │                     │
│                        │  - Return prev   │                     │
│                        │                  │                     │
│                        └────────┬─────────┘                     │
│                                  │                               │
│                    ┌─────────────┴─────────────┐               │
│                    │                             │               │
│               YES  ▼                             ▼  NO          │
│           ┌──────────────────┐         ┌──────────────────┐   │
│           │                  │         │                  │   │
│           │ Prev Response    │         │  First Query    │   │
│           │  Within 180s?    │         │  in Session     │   │
│           │                  │         │                  │   │
│           └────────┬─────────┘         └──────────────────┘   │
│                    │                                            │
│                    ▼                                            │
│         ┌─────────────────────┐                                │
│         │                     │                                │
│         │ Follow-Up Detection │                                │
│         │   (Background)      │                                │
│         │  - Frustration      │                                │
│         │  - Same Referent    │                                │
│         │  - Correction Lang  │                                │
│         │                     │                                │
│         └──────────┬──────────┘                                │
│                    │                                            │
│           ┌────────┴────────┐                                  │
│           │                  │                                  │
│      YES  ▼                  ▼  NO                             │
│   ┌──────────────┐    ┌──────────────┐                        │
│   │              │    │              │                        │
│   │ Correction   │    │  No Issues   │                        │
│   │  Detected    │    │   Found      │                        │
│   │              │    │              │                        │
│   └──────┬───────┘    └──────┬───────┘                        │
│          │                    │                                │
│          ▼                    ▼                                │
│   ┌──────────────┐    ┌──────────────┐                        │
│   │              │    │              │                        │
│   │ Create F08   │    │ Mark         │                        │
│   │  Feedback    │    │  Detected    │                        │
│   │              │    │              │                        │
│   │ Register     │    │              │                        │
│   │   Patch      │    │              │                        │
│   │              │    │              │                        │
│   └──────────────┘    └──────────────┘                        │
│                                                                │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │          TimeoutProcessor (Background Task)           │    │
│  │                  (Runs every 60s)                     │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │                                                        │    │
│  │  1. Find responses > 180s old                        │    │
│  │  2. Check if enriched                                │    │
│  │  3. If not:                                          │    │
│  │     - Fetch QueryEvidence telemetry                 │    │
│  │     - Calculate dwell time                          │    │
│  │     - Populate automated_category/confidence        │    │
│  │     - Link to unified_record_ref                    │    │
│  │     - Mark as enriched                              │    │
│  │                                                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌──────────────┐
│  User Query  │
│   (t=0s)     │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│  Response Generated  │
│  - ResponseFeedback  │
│    (skeleton)        │
│  - QueryEvidence     │
│    (telemetry)       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│     User Behavior (3 scenarios)      │
├──────────────────────────────────────┤
│                                      │
│  A. New Query (t=45s)               │
│     ↓                                │
│  SessionManager checks:              │
│    - Previous response exists?  ✓   │
│    - Age < 180s?  ✓                 │
│     ↓                                │
│  Trigger follow-up detection         │
│     ↓                                │
│  Update ResponseFeedback             │
│                                      │
│  B. Explicit Feedback (t=30s)       │
│     ↓                                │
│  User clicks button                  │
│     ↓                                │
│  Update ResponseFeedback (existing)  │
│                                      │
│  C. Timeout (t=200s)                │
│     ↓                                │
│  TimeoutProcessor finds response     │
│     ↓                                │
│  Enrich with QueryEvidence data      │
│     ↓                                │
│  Mark as implicit_positive           │
│                                      │
└──────────────────────────────────────┘
```

---

## Implementation Components

### Component 1: SessionManager

**Purpose:** Track session history and timestamps for timeout enforcement

**File:** `backend/app/feedback/session_manager.py`

**Responsibilities:**
- Maintain in-memory state of active sessions
- Track query timestamps per session
- Enforce 180s timeout window
- Return previous response if eligible for detection
- Background cleanup of expired sessions

**Key Classes:**

```python
@dataclass
class SessionResponse:
    response_id: str
    query_text: str
    timestamp: datetime
    detected: bool = False    # Follow-up detection run?
    enriched: bool = False    # Automatic metrics enriched?

@dataclass
class SessionState:
    session_id: str
    responses: List[SessionResponse]
    last_activity: datetime

class SessionManager:
    _sessions: Dict[str, SessionState]
    timeout_seconds: int = 180
    
    async def register_response(...) -> Optional[SessionResponse]
    async def mark_detected(...)
    async def mark_enriched(...)
    async def get_unenriched_responses(...) -> List[tuple]
```

**Memory Footprint:**
- ~1KB per session
- 10,000 sessions = ~10MB
- Cleanup removes sessions after 2× timeout (360s)

**Dependencies:**
- Python stdlib (dataclasses, asyncio, datetime)
- No external libraries

---

### Component 2: Automatic Follow-Up Detection Integration

**Purpose:** Trigger follow-up detection when new query submitted

**File:** `backend/app/api/routes/chat.py` (modifications)

**Changes Required:**

```python
# Add imports
from app.feedback.session_manager import get_session_manager

async def _run_v2_chat(request: ChatRequest, container: Container):
    # ... existing code ...
    
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    session_id = request.session_id
    query = request.query
    
    # === NEW: Register response and check for detection ===
    session_manager = get_session_manager()
    previous_response = await session_manager.register_response(
        session_id=session_id,
        response_id=response_id,
        query_text=query
    )
    
    # If previous response within timeout, run detection (background)
    if previous_response:
        asyncio.create_task(_trigger_follow_up_detection(
            session_id=session_id,
            previous_response_id=previous_response.response_id,
            previous_query=previous_response.query_text,
            follow_up_query=query,
            session_manager=session_manager
        ))
    # === END NEW ===
    
    # ... rest of existing code ...
```

**New Helper Function:**

```python
async def _trigger_follow_up_detection(
    session_id: str,
    previous_response_id: str,
    previous_query: str,
    follow_up_query: str,
    session_manager: SessionManager
):
    """Run follow-up detection in background (non-blocking)."""
    try:
        logger.info(
            "Auto follow-up detection: session=%s, prev=%s",
            session_id, previous_response_id
        )
        
        # Call existing detection logic
        from app.api.routes.feedback import run_follow_up_detection_logic
        
        result = await run_follow_up_detection_logic(
            session_id=session_id,
            previous_response_id=previous_response_id,
            follow_up_query=follow_up_query,
            original_query=previous_query
        )
        
        # Mark as detected
        await session_manager.mark_detected(session_id, previous_response_id)
        
        logger.info("Follow-up detection complete: %s", result)
    
    except Exception as exc:
        logger.warning("Follow-up detection failed: %s", exc)
```

**Latency Impact:** **0ms** (runs in background task)

---

### Component 3: MetricsEnricher

**Purpose:** Populate skeleton records with automatic metrics from QueryEvidence

**File:** `backend/app/feedback/metrics_enrichment.py`

**Responsibilities:**
- Fetch QueryEvidence telemetry for response
- Calculate dwell time from timestamps
- Map quality_score to automated_category
- Populate automated_confidence
- Link ResponseFeedback ↔ QueryEvidence via unified_record_ref

**Key Class:**

```python
class MetricsEnricher:
    async def enrich_response(
        self,
        session_id: str,
        response_id: str
    ) -> bool:
        # 1. Fetch ResponseFeedback (skeleton)
        # 2. Fetch QueryEvidence (telemetry)
        # 3. Calculate dwell time
        # 4. Map quality_score → automated_category
        # 5. Update ResponseFeedback fields
        # 6. Commit to database
```

**Quality Mapping:**

| quality_score | automated_category | automated_confidence |
|---------------|-------------------|----------------------|
| >= 8.0 | auto_high_quality | score / 10.0 |
| 5.0-7.9 | auto_medium_quality | score / 10.0 |
| < 5.0 | auto_low_quality | score / 10.0 |
| N/A + compliance HIGH/CRITICAL | auto_compliance_issue | 0.90 |
| N/A + dwell time > 180s | implicit_positive | 0.70 |

**Implicit Signals:**
- **Dwell time > 180s + no correction:** Likely satisfied → `implicit_positive`
- **Dwell time < 30s:** Quick abandon → `auto_low_engagement`

**Dependencies:**
- Access to ResponseFeedback table
- Access to QueryEvidence table
- No external libraries

---

### Component 4: TimeoutProcessor

**Purpose:** Background task to process timed-out sessions

**File:** `backend/app/feedback/timeout_processor.py`

**Responsibilities:**
- Run every 60 seconds
- Find responses older than 180s
- Check if already enriched
- Call MetricsEnricher for unenriched responses
- Mark as processed in SessionManager

**Key Class:**

```python
class TimeoutProcessor:
    check_interval: int = 60  # seconds
    _running: bool = False
    
    async def start()
    async def stop()
    async def _process_loop():
        while self._running:
            # 1. Get unenriched responses from SessionManager
            # 2. For each response:
            #    - Call MetricsEnricher.enrich_response()
            #    - Mark as enriched in SessionManager
            # 3. Sleep for check_interval
```

**Performance:**
- Processes responses in batches
- Non-blocking (runs in background)
- Minimal database load (one UPDATE per response)

---

### Component 5: Application Lifecycle Integration

**Purpose:** Start/stop background tasks with FastAPI application

**File:** `backend/app/main.py` (modifications)

**Changes Required:**

```python
from app.feedback.session_manager import (
    start_session_manager, 
    stop_session_manager
)
from app.feedback.timeout_processor import (
    start_timeout_processor, 
    stop_timeout_processor
)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AMC ContextGraph API...")
    
    # ... existing startup code ...
    
    # Start passive feedback tasks
    try:
        await start_session_manager()
        await start_timeout_processor()
        logger.info("✅ Passive feedback tasks started")
    except Exception as exc:
        logger.error("Failed to start passive feedback: %s", exc)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AMC ContextGraph API...")
    
    # Stop passive feedback tasks
    try:
        await stop_timeout_processor()
        await stop_session_manager()
        logger.info("✅ Passive feedback tasks stopped")
    except Exception as exc:
        logger.error("Failed to stop passive feedback: %s", exc)
    
    # ... existing shutdown code ...
```

---

## Day-by-Day Implementation Plan

### **Day 1: SessionManager Foundation**

**Assignee:** Developer 1  
**Effort:** 6-8 hours  
**Goal:** Session state tracking with timeout enforcement

#### Morning (4h): Core Implementation

**Tasks:**
- [ ] Create `backend/app/feedback/session_manager.py`
- [ ] Implement `SessionResponse` dataclass
- [ ] Implement `SessionState` dataclass
- [ ] Implement `SessionManager` class:
  - [ ] `__init__` with timeout configuration
  - [ ] `register_response()` method
  - [ ] `get_previous_response()` logic
  - [ ] `is_within_timeout()` check
  - [ ] `mark_detected()` method
  - [ ] `mark_enriched()` method

**Code Checklist:**
```python
# session_manager.py structure
@dataclass
class SessionResponse:
    response_id: str
    query_text: str
    timestamp: datetime
    detected: bool = False
    enriched: bool = False

@dataclass
class SessionState:
    session_id: str
    responses: List[SessionResponse] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class SessionManager:
    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
    
    async def register_response(...) -> Optional[SessionResponse]:
        # TODO: Implement
        pass
```

**Acceptance Criteria:**
- ✅ SessionManager tracks query timestamps
- ✅ `register_response()` returns previous response if within 180s
- ✅ `register_response()` returns None if first query or outside timeout
- ✅ Thread-safe with asyncio locks

#### Afternoon (3-4h): Background Cleanup + Testing

**Tasks:**
- [ ] Implement `_cleanup_expired_sessions()` background task
- [ ] Implement `start()` and `stop()` methods
- [ ] Implement `get_unenriched_responses()` method
- [ ] Create global singleton `get_session_manager()`
- [ ] Write unit tests

**Unit Tests:**
```python
# tests/test_session_manager.py

@pytest.mark.asyncio
async def test_register_first_response():
    manager = SessionManager()
    prev = await manager.register_response("sess1", "resp1", "query1")
    assert prev is None  # First query, no previous

@pytest.mark.asyncio
async def test_register_within_timeout():
    manager = SessionManager(timeout_seconds=180)
    await manager.register_response("sess1", "resp1", "query1")
    prev = await manager.register_response("sess1", "resp2", "query2")
    assert prev is not None
    assert prev.response_id == "resp1"

@pytest.mark.asyncio
async def test_register_outside_timeout():
    manager = SessionManager(timeout_seconds=1)
    await manager.register_response("sess1", "resp1", "query1")
    await asyncio.sleep(1.5)
    prev = await manager.register_response("sess1", "resp2", "query2")
    assert prev is None  # Outside timeout

@pytest.mark.asyncio
async def test_mark_detected():
    manager = SessionManager()
    await manager.register_response("sess1", "resp1", "query1")
    await manager.register_response("sess1", "resp2", "query2")
    await manager.mark_detected("sess1", "resp1")
    # Third query should skip resp1 (already detected)
    prev = await manager.register_response("sess1", "resp3", "query3")
    assert prev.response_id == "resp2"

@pytest.mark.asyncio
async def test_cleanup_expired_sessions():
    manager = SessionManager(timeout_seconds=60)
    await manager.start()
    
    await manager.register_response("sess_old", "resp1", "query1")
    
    # Manually age the session
    manager._sessions["sess_old"].last_activity = (
        datetime.now(timezone.utc) - timedelta(seconds=200)
    )
    
    await asyncio.sleep(1)  # Wait for cleanup cycle
    assert "sess_old" not in manager._sessions
    
    await manager.stop()
```

**Run Tests:**
```bash
pytest tests/test_session_manager.py -v
```

**Deliverables:**
- ✅ `session_manager.py` complete with all methods
- ✅ Background cleanup task working
- ✅ All unit tests passing
- ✅ Code reviewed and committed

---

### **Day 2: MetricsEnricher + Chat Integration**

**Morning:** Developer 2 (MetricsEnricher)  
**Afternoon:** Developer 1 (Chat Integration)

#### Morning (4h): MetricsEnricher Implementation

**Assignee:** Developer 2  
**Effort:** 4 hours

**Tasks:**
- [ ] Create `backend/app/feedback/metrics_enrichment.py`
- [ ] Implement `MetricsEnricher` class:
  - [ ] `enrich_response()` method
  - [ ] `_categorize_quality()` helper
  - [ ] QueryEvidence → ResponseFeedback mapping
- [ ] Create global singleton `get_metrics_enricher()`

**Code Checklist:**
```python
# metrics_enrichment.py structure
class MetricsEnricher:
    async def enrich_response(
        self,
        session_id: str,
        response_id: str
    ) -> bool:
        db = SessionLocal()
        try:
            # 1. Fetch ResponseFeedback
            feedback = db.query(ResponseFeedback).filter_by(...).first()
            
            # 2. Check if already enriched
            if feedback.actor_id or feedback.automated_category:
                return True
            
            # 3. Fetch QueryEvidence
            evidence = db.query(QueryEvidence).filter_by(...).first()
            
            # 4. Enrich fields
            if evidence:
                feedback.response_text = evidence.response_text
                feedback.automated_confidence = evidence.quality_score / 10.0
                feedback.automated_category = self._categorize_quality(...)
                feedback.unified_record_ref = response_id
            
            # 5. Calculate dwell time
            created_dt = datetime.fromisoformat(feedback.created_at)
            dwell_seconds = (datetime.now(timezone.utc) - created_dt).total_seconds()
            
            # 6. Implicit signals
            if dwell_seconds > 180 and not feedback.automated_category:
                feedback.automated_category = "implicit_positive"
                feedback.automated_confidence = 0.70
            
            # 7. Commit
            feedback.updated_at = datetime.now(timezone.utc).isoformat()
            db.commit()
            return True
        finally:
            db.close()
    
    def _categorize_quality(
        self,
        quality_score: Optional[float],
        compliance_severity: Optional[str]
    ) -> str:
        # TODO: Implement mapping logic
        pass
```

**Unit Tests:**
```python
# tests/test_metrics_enrichment.py

@pytest.mark.asyncio
async def test_enrich_with_query_evidence(db_session):
    # Create skeleton ResponseFeedback
    skeleton = ResponseFeedback(
        feedback_id="fb_001",
        response_id="resp_001",
        session_id="sess_001",
        # ... other fields NULL
    )
    db_session.add(skeleton)
    
    # Create QueryEvidence
    evidence = QueryEvidence(
        response_id="resp_001",
        quality_score=8.5,
        response_text="test response"
    )
    db_session.add(evidence)
    db_session.commit()
    
    # Enrich
    enricher = MetricsEnricher()
    success = await enricher.enrich_response("sess_001", "resp_001")
    
    assert success
    
    # Verify
    enriched = db_session.query(ResponseFeedback).filter_by(
        feedback_id="fb_001"
    ).first()
    assert enriched.automated_category == "auto_high_quality"
    assert enriched.automated_confidence == 0.85
    assert enriched.response_text == "test response"
```

**Acceptance Criteria:**
- ✅ Fetches QueryEvidence for given response_id
- ✅ Maps quality_score to automated_category correctly
- ✅ Calculates dwell time from timestamps
- ✅ Links ResponseFeedback ↔ QueryEvidence
- ✅ Unit tests passing

#### Afternoon (4h): Chat Endpoint Integration

**Assignee:** Developer 1  
**Effort:** 4 hours

**Tasks:**
- [ ] Modify `backend/app/api/routes/chat.py`
- [ ] Add SessionManager import and integration
- [ ] Implement `_trigger_follow_up_detection()` helper
- [ ] Extract follow-up detection logic from `feedback.py` into reusable function
- [ ] Test integration locally

**Changes to chat.py:**
```python
from app.feedback.session_manager import get_session_manager

async def _run_v2_chat(request: ChatRequest, container: Container):
    # ... existing code until response_id generation ...
    
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    
    # === NEW: Session-aware detection ===
    session_manager = get_session_manager()
    previous_response = await session_manager.register_response(
        session_id=session_id,
        response_id=response_id,
        query_text=request.query
    )
    
    # Trigger follow-up detection if eligible
    if previous_response:
        asyncio.create_task(_trigger_follow_up_detection(
            session_id=session_id,
            previous_response=previous_response,
            current_query=request.query,
            session_manager=session_manager
        ))
    # === END NEW ===
    
    # ... rest of existing code ...
```

**New Helper Function:**
```python
async def _trigger_follow_up_detection(
    session_id: str,
    previous_response: SessionResponse,
    current_query: str,
    session_manager: SessionManager
):
    """Trigger follow-up detection in background."""
    try:
        logger.info(
            "Auto follow-up detection: session=%s, prev_response=%s",
            session_id, previous_response.response_id
        )
        
        # Import detection function
        from app.api.routes.feedback import run_follow_up_detection_logic
        
        # Run detection
        result = await run_follow_up_detection_logic(
            session_id=session_id,
            previous_response_id=previous_response.response_id,
            follow_up_query=current_query,
            original_query=previous_response.query_text
        )
        
        # Mark as detected
        await session_manager.mark_detected(
            session_id, 
            previous_response.response_id
        )
        
        if result and result.get("is_correction"):
            logger.info(
                "Correction detected via passive feedback: %s",
                result.get("claim")
            )
    
    except Exception as exc:
        logger.warning("Auto follow-up detection failed: %s", exc)
```

**Refactor feedback.py:**
```python
# Extract logic from detect_follow_up_correction endpoint

async def run_follow_up_detection_logic(
    session_id: str,
    previous_response_id: str,
    follow_up_query: str,
    original_query: str
) -> Dict[str, Any]:
    """Reusable follow-up detection logic (extracted from endpoint)."""
    db = SessionLocal()
    try:
        # ... existing detection logic ...
        # (same as current detect_follow_up_correction endpoint)
        pass
    finally:
        db.close()


@router.post("/follow-up-detection")
async def detect_follow_up_correction(payload: FollowUpDetectionIn):
    """Public endpoint (calls reusable logic)."""
    return await run_follow_up_detection_logic(
        session_id=payload.session_id,
        previous_response_id=payload.previous_response_id,
        follow_up_query=payload.follow_up_query,
        original_query=payload.original_query
    )
```

**Integration Test:**
```python
# tests/integration/test_passive_detection.py

@pytest.mark.integration
def test_auto_follow_up_detection(test_client):
    # Query 1
    resp1 = test_client.post("/api/chat", json={
        "query": "What is the TER of HDFC Equity Fund?",
        "mode": "contextgraph",
        "session_id": "test_sess_001",
        "history": []
    })
    assert resp1.status_code == 200
    response_id_1 = resp1.json()["response_id"]
    
    # Query 2 (correction)
    resp2 = test_client.post("/api/chat", json={
        "query": "Actually, the TER is 2.5%, not what you said",
        "mode": "contextgraph",
        "session_id": "test_sess_001",
        "history": [...]
    })
    assert resp2.status_code == 200
    
    # Wait for background task
    import time
    time.sleep(2)
    
    # Verify follow-up detection ran
    feedback = test_client.get(f"/api/feedback?response_id={response_id_1}")
    assert feedback.status_code == 200
    data = feedback.json()
    
    # Should have detected correction automatically
    assert len(data) > 0
    assert "F08" in data[0]["selected_categories"]
```

**Deliverables:**
- ✅ Chat endpoint integrated with SessionManager
- ✅ Follow-up detection triggers automatically
- ✅ Background execution (non-blocking)
- ✅ Integration test passing

---

### **Day 3: End-to-End Testing + Fixes**

**Assignees:** Developer 1 + Developer 2  
**Effort:** 6-8 hours  
**Goal:** Validate full pipeline, fix integration issues

#### Morning (4h): Integration Testing

**Tasks:**
- [ ] Test 3 trigger scenarios:
  1. New query within timeout → follow-up detection
  2. Explicit feedback button → existing flow
  3. (Manual test) Timeout → enrichment (Day 4 implementation)
- [ ] Test edge cases:
  - First query in session
  - Query outside timeout window
  - Multiple queries in quick succession
  - Same session across multiple tabs
- [ ] Performance testing:
  - 100 concurrent sessions
  - Query latency measurement
  - Memory usage monitoring
- [ ] Run full regression test suite

**Test Scenarios:**

**Scenario 1: Happy Path (Within Timeout)**
```python
def test_happy_path_within_timeout():
    # 1. User asks query
    resp1 = post_query("What is TER of Fund X?")
    
    # 2. User submits correction within 180s
    resp2 = post_query("Actually TER is 2.5%")
    
    # 3. Wait for background detection
    time.sleep(2)
    
    # 4. Verify correction detected
    feedback = get_feedback(resp1.response_id)
    assert feedback.automated_category == "auto_correction_detected"
```

**Scenario 2: Outside Timeout Window**
```python
def test_outside_timeout_window():
    resp1 = post_query("What is NAV?")
    
    # Wait for timeout
    time.sleep(181)
    
    resp2 = post_query("NAV is wrong")
    
    # Should NOT trigger detection (too old)
    feedback = get_feedback(resp1.response_id)
    assert feedback.automated_category is None  # Not enriched yet
```

**Scenario 3: Multiple Queries**
```python
def test_multiple_queries_rapid():
    resp1 = post_query("Query 1")
    resp2 = post_query("Query 2")  # Checks resp1
    resp3 = post_query("Query 3")  # Checks resp2
    
    # All detections should complete
    time.sleep(3)
    
    # Verify all marked as detected
    # (No duplicate detection attempts)
```

**Performance Test:**
```python
import asyncio
from locust import HttpUser, task, between

class PassiveFeedbackUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def query_with_correction(self):
        session_id = f"sess_{self.client.port}"
        
        # First query
        resp1 = self.client.post("/api/chat", json={
            "query": "Test query 1",
            "session_id": session_id,
            "mode": "contextgraph",
            "history": []
        })
        
        # Correction query
        resp2 = self.client.post("/api/chat", json={
            "query": "Actually, that's wrong",
            "session_id": session_id,
            "mode": "contextgraph",
            "history": [...]
        })

# Run: locust -f tests/load/test_passive_feedback.py --users 100 --spawn-rate 10
```

**Acceptance Criteria:**
- ✅ All test scenarios pass
- ✅ Query latency P95 < 5ms increase
- ✅ SessionManager memory < 50MB for 10K sessions
- ✅ No race conditions or deadlocks

#### Afternoon (3-4h): Bug Fixes + Optimization

**Tasks:**
- [ ] Fix any integration issues found
- [ ] Optimize SessionManager memory usage
- [ ] Add logging and instrumentation
- [ ] Code review and cleanup
- [ ] Update existing tests if needed

**Common Issues to Check:**
1. **Race Condition:** Multiple queries from same session arrive simultaneously
   - **Fix:** Use asyncio locks in SessionManager
2. **Memory Leak:** Sessions not cleaned up
   - **Fix:** Verify background cleanup task runs
3. **Detection Loop:** Follow-up detection triggers itself
   - **Fix:** Mark as detected before running logic
4. **Database Deadlock:** Concurrent updates to ResponseFeedback
   - **Fix:** Use row-level locking or retry logic

**Deliverables:**
- ✅ All integration tests passing
- ✅ No performance regression
- ✅ Code reviewed and optimized
- ✅ Ready for Day 4 (timeout processor)

---

### **Day 4: TimeoutProcessor + Lifecycle**

**Assignee:** Developer 1  
**Effort:** 6-8 hours  
**Goal:** Background task for timeout enrichment

#### Morning (4h): TimeoutProcessor Implementation

**Tasks:**
- [ ] Create `backend/app/feedback/timeout_processor.py`
- [ ] Implement `TimeoutProcessor` class:
  - [ ] `start()` method
  - [ ] `stop()` method
  - [ ] `_process_loop()` background task
- [ ] Integrate with SessionManager and MetricsEnricher
- [ ] Create global singleton `get_timeout_processor()`

**Code Checklist:**
```python
# timeout_processor.py structure
class TimeoutProcessor:
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("TimeoutProcessor started")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TimeoutProcessor stopped")
    
    async def _process_loop(self):
        enricher = get_metrics_enricher()
        session_manager = get_session_manager()
        
        while self._running:
            try:
                # 1. Get unenriched responses
                unenriched = await session_manager.get_unenriched_responses()
                
                if unenriched:
                    logger.info("Processing %d timed-out responses", len(unenriched))
                    
                    # 2. Enrich each response
                    for session_id, response_id in unenriched:
                        try:
                            success = await enricher.enrich_response(
                                session_id, response_id
                            )
                            if success:
                                await session_manager.mark_enriched(
                                    session_id, response_id
                                )
                        except Exception as exc:
                            logger.error("Enrichment failed: %s", exc)
                
                # 3. Sleep
                await asyncio.sleep(self.check_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("TimeoutProcessor error: %s", exc)
```

**Unit Test:**
```python
# tests/test_timeout_processor.py

@pytest.mark.asyncio
async def test_timeout_processor_enriches_old_responses(db_session):
    # Setup: Create old response (> 180s)
    old_feedback = ResponseFeedback(
        feedback_id="fb_old",
        response_id="resp_old",
        session_id="sess_old",
        created_at=(datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat(),
        automated_category=None,  # Not enriched
    )
    db_session.add(old_feedback)
    db_session.commit()
    
    # Register in SessionManager
    session_manager = get_session_manager()
    await session_manager.register_response("sess_old", "resp_old", "old query")
    
    # Manually age it
    session_manager._sessions["sess_old"].responses[0].timestamp = (
        datetime.now(timezone.utc) - timedelta(seconds=200)
    )
    
    # Start processor
    processor = get_timeout_processor(check_interval=1)
    await processor.start()
    
    # Wait for one cycle
    await asyncio.sleep(2)
    
    # Verify enrichment
    enriched = db_session.query(ResponseFeedback).filter_by(
        feedback_id="fb_old"
    ).first()
    assert enriched.automated_category == "implicit_positive"
    assert enriched.automated_confidence == 0.70
    
    await processor.stop()
```

**Acceptance Criteria:**
- ✅ Runs every 60 seconds
- ✅ Finds responses > 180s old
- ✅ Enriches unenriched responses
- ✅ Marks as processed
- ✅ Graceful start/stop

#### Afternoon (3-4h): Application Lifecycle Integration

**Tasks:**
- [ ] Modify `backend/app/main.py`
- [ ] Add startup event handlers
- [ ] Add shutdown event handlers
- [ ] Test graceful shutdown
- [ ] Add health check endpoint for passive feedback

**Changes to main.py:**
```python
from app.feedback.session_manager import (
    start_session_manager,
    stop_session_manager,
    get_session_manager
)
from app.feedback.timeout_processor import (
    start_timeout_processor,
    stop_timeout_processor
)

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting AMC ContextGraph API...")
    
    # ... existing startup code ...
    
    # Start passive feedback background tasks
    try:
        await start_session_manager()
        logger.info("✅ SessionManager started")
        
        await start_timeout_processor()
        logger.info("✅ TimeoutProcessor started")
        
        logger.info("✅ Passive feedback system ready")
    except Exception as exc:
        logger.error("❌ Failed to start passive feedback: %s", exc)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down AMC ContextGraph API...")
    
    # Stop passive feedback tasks FIRST (before DB connections close)
    try:
        await stop_timeout_processor()
        logger.info("✅ TimeoutProcessor stopped")
        
        await stop_session_manager()
        logger.info("✅ SessionManager stopped")
    except Exception as exc:
        logger.error("❌ Failed to stop passive feedback: %s", exc)
    
    # ... existing shutdown code ...

# Health check endpoint
@app.get("/api/health/passive-feedback")
async def passive_feedback_health():
    """Health check for passive feedback system."""
    session_manager = get_session_manager()
    
    return {
        "status": "healthy",
        "session_count": len(session_manager._sessions),
        "timeout_seconds": session_manager.timeout_seconds,
    }
```

**Test Graceful Shutdown:**
```bash
# Start app
uvicorn app.main:app --reload

# Send SIGTERM
kill -TERM <pid>

# Verify logs show:
# ✅ TimeoutProcessor stopped
# ✅ SessionManager stopped
```

**Deliverables:**
- ✅ TimeoutProcessor implemented
- ✅ Application lifecycle integrated
- ✅ Graceful startup/shutdown
- ✅ Health check endpoint

---

### **Day 5: Final Testing + Documentation**

**Assignees:** Developer 1 + Developer 2 + QA Engineer  
**Effort:** 8 hours  
**Goal:** Production readiness

#### Morning (4h): Comprehensive Testing

**Tasks:**
- [ ] Run full test suite (unit + integration)
- [ ] Load testing (100-1000 concurrent sessions)
- [ ] Memory leak testing (24h simulated)
- [ ] Error handling validation
- [ ] Edge case testing

**Load Test Plan:**
```python
# tests/load/test_passive_feedback_load.py

from locust import HttpUser, task, between, events
import logging

class PassiveFeedbackLoadTest(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        """Initialize session."""
        self.session_id = f"load_sess_{self.client.port}_{id(self)}"
    
    @task(3)
    def normal_query(self):
        """Normal query without correction."""
        self.client.post("/api/chat", json={
            "query": f"Test query {time.time()}",
            "session_id": self.session_id,
            "mode": "contextgraph",
            "history": []
        })
    
    @task(1)
    def correction_query(self):
        """Query with correction attempt."""
        # First query
        resp1 = self.client.post("/api/chat", json={
            "query": "What is the TER?",
            "session_id": self.session_id,
            "mode": "contextgraph",
            "history": []
        })
        
        # Correction
        time.sleep(2)
        self.client.post("/api/chat", json={
            "query": "Actually, TER is 2.5%",
            "session_id": self.session_id,
            "mode": "contextgraph",
            "history": [...]
        })

# Run tests
# locust -f tests/load/test_passive_feedback_load.py \
#        --users 1000 \
#        --spawn-rate 50 \
#        --run-time 10m
```

**Memory Leak Test:**
```python
# tests/test_memory_leak.py

import psutil
import asyncio

@pytest.mark.slow
async def test_no_memory_leak_over_time():
    """Simulate 24 hours of operation in 5 minutes."""
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    session_manager = get_session_manager()
    await session_manager.start()
    
    # Simulate 10,000 queries
    for i in range(10000):
        session_id = f"sess_{i % 100}"  # 100 concurrent sessions
        response_id = f"resp_{i}"
        await session_manager.register_response(
            session_id, response_id, f"query {i}"
        )
        
        if i % 1000 == 0:
            await asyncio.sleep(0.1)  # Yield control
    
    # Wait for cleanup
    await asyncio.sleep(10)
    
    final_memory = process.memory_info().rss / 1024 / 1024
    memory_increase = final_memory - initial_memory
    
    # Allow 20MB increase max
    assert memory_increase < 20, f"Memory leak detected: {memory_increase}MB"
    
    await session_manager.stop()
```

**Acceptance Criteria:**
- ✅ All tests passing (100% pass rate)
- ✅ Load test: 1000 users, P95 latency < 5ms increase
- ✅ Memory: < 20MB increase over 10K queries
- ✅ No crashes or exceptions

#### Afternoon (4h): Documentation + Deployment Prep

**Tasks:**
- [ ] Update API documentation
- [ ] Write operator runbook section
- [ ] Create deployment checklist
- [ ] Update configuration guide
- [ ] Code review final pass
- [ ] Create release notes

**API Documentation Update:**
```markdown
# Passive Feedback System

## Overview
Automatic feedback capture and correction detection without user intervention.

## Features
- **Automatic Follow-Up Detection**: Detects corrections in follow-up queries
- **Session Timeout Enrichment**: Enriches responses with metrics after 180s
- **Implicit Signals**: Captures dwell time, satisfaction indicators

## Configuration
```python
# backend/.env
PASSIVE_FEEDBACK_TIMEOUT=180  # seconds
PASSIVE_FEEDBACK_ENABLED=true
```

## Endpoints

### Health Check
```http
GET /api/health/passive-feedback
```

Response:
```json
{
  "status": "healthy",
  "session_count": 142,
  "timeout_seconds": 180
}
```

## Metrics
- `passive_feedback_sessions_tracked_total`: Total sessions tracked
- `passive_feedback_detections_triggered_total`: Follow-up detections triggered
- `passive_feedback_corrections_found_total`: Corrections detected
- `passive_feedback_enrichments_completed_total`: Responses enriched
```

**Operator Runbook Section:**
```markdown
# Passive Feedback Operations

## Daily Monitoring

### Health Checks
```bash
curl http://localhost:8000/api/health/passive-feedback
```

Expected: `{"status": "healthy"}`

### Metrics Dashboard
- Grafana dashboard: "Passive Feedback Overview"
- Key metrics:
  - Session count (target: < 10,000)
  - Detection rate (target: > 20%)
  - Enrichment latency (target: < 5s)

## Troubleshooting

### Issue: SessionManager Memory High (> 100MB)
**Symptoms:** Memory usage increasing over time
**Diagnosis:**
```bash
# Check session count
curl http://localhost:8000/api/health/passive-feedback | jq '.session_count'
```
**Resolution:**
- Reduce cleanup interval
- Lower timeout window
- Restart application

### Issue: Follow-Up Detection Not Triggering
**Symptoms:** No corrections detected despite user feedback
**Diagnosis:**
```bash
# Check logs
tail -f logs/app.log | grep "Auto follow-up detection"
```
**Resolution:**
- Verify SessionManager started
- Check timeout configuration
- Review detection logic logs

### Issue: Enrichment Failures
**Symptoms:** Responses not enriched after timeout
**Diagnosis:**
```bash
# Check TimeoutProcessor logs
tail -f logs/app.log | grep "TimeoutProcessor"
```
**Resolution:**
- Verify QueryEvidence data exists
- Check database connectivity
- Review enrichment error logs
```

**Deployment Checklist:**
```markdown
# Passive Feedback Deployment Checklist

## Pre-Deployment
- [ ] All tests passing (unit + integration + load)
- [ ] Code reviewed and approved
- [ ] Documentation updated
- [ ] Configuration verified

## Deployment Steps
1. [ ] Backup database
2. [ ] Deploy code to staging
3. [ ] Verify health checks
4. [ ] Run smoke tests
5. [ ] Monitor for 24 hours
6. [ ] Deploy to production
7. [ ] Verify health checks
8. [ ] Monitor metrics

## Post-Deployment
- [ ] Session count stable
- [ ] Detection rate > 20%
- [ ] No errors in logs
- [ ] Performance baseline established

## Rollback Plan
If issues detected:
1. Set `PASSIVE_FEEDBACK_ENABLED=false`
2. Restart application
3. Verify old behavior restored
4. Investigate root cause
```

**Deliverables:**
- ✅ All documentation complete
- ✅ Deployment checklist ready
- ✅ Code reviewed and approved
- ✅ Ready for staging deployment

---

## Testing Strategy

### Test Pyramid

```
                   ┌─────────────┐
                   │   Manual    │ (5%)
                   │  Exploratory│
                   └─────────────┘
              ┌────────────────────────┐
              │    Integration Tests   │ (25%)
              │  - End-to-end flows   │
              │  - API contracts      │
              └────────────────────────┘
       ┌──────────────────────────────────────┐
       │           Unit Tests                  │ (70%)
       │  - SessionManager logic              │
       │  - MetricsEnricher mapping           │
       │  - TimeoutProcessor scheduling       │
       └──────────────────────────────────────┘
```

### Unit Tests (70%)

**Target Coverage:** 90%+

**Test Files:**
- `tests/test_session_manager.py` (15 tests)
- `tests/test_metrics_enrichment.py` (12 tests)
- `tests/test_timeout_processor.py` (8 tests)

**Key Test Cases:**

**SessionManager:**
- ✅ Register first response (no previous)
- ✅ Register within timeout window
- ✅ Register outside timeout window
- ✅ Mark as detected
- ✅ Mark as enriched
- ✅ Get unenriched responses
- ✅ Background cleanup
- ✅ Concurrent access (thread safety)

**MetricsEnricher:**
- ✅ Enrich with QueryEvidence data
- ✅ Enrich without QueryEvidence
- ✅ Quality score mapping (high/medium/low)
- ✅ Compliance severity handling
- ✅ Dwell time calculation
- ✅ Implicit positive signal
- ✅ Already enriched (idempotent)
- ✅ Database error handling

**TimeoutProcessor:**
- ✅ Start/stop lifecycle
- ✅ Process unenriched responses
- ✅ Batch processing
- ✅ Error handling (continue on failure)
- ✅ Graceful shutdown

### Integration Tests (25%)

**Test Files:**
- `tests/integration/test_passive_feedback_flow.py` (8 tests)
- `tests/integration/test_chat_endpoint_integration.py` (6 tests)

**Key Test Scenarios:**

**End-to-End Flows:**
```python
def test_e2e_correction_detection():
    # 1. User submits query
    resp1 = post_query("What is TER?")
    
    # 2. User submits correction within 180s
    resp2 = post_query("Actually, TER is 2.5%")
    
    # 3. Verify detection ran automatically
    feedback = get_feedback(resp1.response_id)
    assert "F08" in feedback.selected_categories

def test_e2e_timeout_enrichment():
    # 1. User submits query
    resp = post_query("What is NAV?")
    
    # 2. Wait for timeout
    time.sleep(181)
    
    # 3. Verify enrichment ran
    feedback = get_feedback(resp.response_id)
    assert feedback.automated_category == "implicit_positive"
```

**API Contracts:**
- ✅ Chat endpoint returns same response format
- ✅ Health check endpoint returns expected fields
- ✅ Feedback API still works (regression)

### Load Tests (Performance)

**Tool:** Locust

**Test Scenarios:**
1. **Baseline:** 100 users, 10 req/s, 5 minutes
2. **Peak Load:** 1000 users, 50 req/s, 10 minutes
3. **Sustained Load:** 500 users, 25 req/s, 30 minutes

**Success Criteria:**
- P50 latency increase: < 2ms
- P95 latency increase: < 5ms
- P99 latency increase: < 10ms
- Error rate: < 0.1%
- Memory: < 100MB for 10K sessions

### Manual Exploratory Tests (5%)

**Test Checklist:**
- [ ] Multiple tabs same session
- [ ] Browser refresh mid-query
- [ ] Network disconnection during detection
- [ ] Database deadlock scenario
- [ ] High CPU load impact
- [ ] Memory leak over 24h
- [ ] Graceful degradation (DB down)

---

## Deployment Plan

### Phase 1: Development Environment (Day 1-3)

**Goal:** Local testing and validation

**Steps:**
1. Implement components
2. Run unit tests
3. Run integration tests
4. Manual testing

**Success Criteria:**
- All tests passing
- No regressions
- Memory/performance validated

### Phase 2: Staging Deployment (Day 4-5)

**Goal:** Pre-production validation

**Steps:**
1. Deploy to staging environment
2. Run smoke tests
3. Load testing (1000 users)
4. Monitor for 24 hours
5. Fix any issues found

**Configuration:**
```bash
# staging/.env
PASSIVE_FEEDBACK_ENABLED=true
PASSIVE_FEEDBACK_TIMEOUT=180
LOG_LEVEL=DEBUG
```

**Monitoring:**
- Grafana dashboard: "Passive Feedback - Staging"
- Alert thresholds:
  - Session count > 50,000
  - Detection failure rate > 10%
  - Enrichment latency > 10s

**Success Criteria:**
- Zero crashes in 24h
- Detection rate > 15%
- Enrichment completion > 95%
- Query latency P95 < 5ms increase

### Phase 3: Production Rollout (Week 2)

**Goal:** Gradual production deployment

#### Stage 1: Canary (10% Traffic)

**Duration:** 3 days

**Steps:**
1. Deploy code to production
2. Enable for 10% of sessions (random sampling)
3. Monitor metrics vs control group
4. Compare detection rates

**Configuration:**
```python
# Canary flag in code
if hash(session_id) % 100 < 10:
    # Passive feedback enabled
else:
    # Passive feedback disabled (control)
```

**Rollback Trigger:**
- Error rate > 1%
- P95 latency > 10ms increase
- SessionManager memory > 200MB

#### Stage 2: 50% Traffic

**Duration:** 3 days

**Steps:**
1. Increase to 50% of sessions
2. Monitor for regressions
3. Validate correction detection accuracy

**Success Criteria:**
- Detection rate > 20%
- False positive rate < 10%
- User satisfaction stable

#### Stage 3: 100% Traffic

**Duration:** Ongoing

**Steps:**
1. Enable for all sessions
2. Remove canary flag
3. Establish baseline metrics
4. Set up alerts

**Final Configuration:**
```bash
# production/.env
PASSIVE_FEEDBACK_ENABLED=true
PASSIVE_FEEDBACK_TIMEOUT=180
LOG_LEVEL=INFO
```

**Monitoring Dashboard:**
- Session count (gauge)
- Detection rate (counter)
- Correction accuracy (manual validation sample)
- Enrichment latency (histogram)
- Memory usage (gauge)

---

## Monitoring & Observability

### Prometheus Metrics

**File:** `backend/app/core/metrics.py` (add these)

```python
from prometheus_client import Counter, Histogram, Gauge

# Session tracking
passive_feedback_sessions_tracked = Counter(
    "passive_feedback_sessions_tracked_total",
    "Total sessions tracked by SessionManager"
)

passive_feedback_sessions_active = Gauge(
    "passive_feedback_sessions_active",
    "Current number of active sessions in memory"
)

# Detection
passive_feedback_detections_triggered = Counter(
    "passive_feedback_detections_triggered_total",
    "Total follow-up detections triggered automatically"
)

passive_feedback_corrections_found = Counter(
    "passive_feedback_corrections_found_total",
    "Total corrections detected via passive feedback"
)

passive_feedback_detection_latency = Histogram(
    "passive_feedback_detection_seconds",
    "Time to complete follow-up detection",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Enrichment
passive_feedback_enrichments_completed = Counter(
    "passive_feedback_enrichments_completed_total",
    "Total skeleton records enriched with automatic metrics"
)

passive_feedback_enrichment_latency = Histogram(
    "passive_feedback_enrichment_seconds",
    "Time to enrich response with metrics",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0]
)

# System health
passive_feedback_timeout_processor_errors = Counter(
    "passive_feedback_timeout_processor_errors_total",
    "Total errors in TimeoutProcessor"
)

passive_feedback_session_manager_memory = Gauge(
    "passive_feedback_session_manager_memory_bytes",
    "Memory used by SessionManager"
)
```

### Instrumentation Points

**SessionManager:**
```python
async def register_response(...):
    passive_feedback_sessions_tracked.inc()
    passive_feedback_sessions_active.set(len(self._sessions))
    # ... rest of logic ...
```

**Follow-Up Detection:**
```python
async def _trigger_follow_up_detection(...):
    passive_feedback_detections_triggered.inc()
    
    start_time = time.time()
    result = await run_follow_up_detection_logic(...)
    latency = time.time() - start_time
    
    passive_feedback_detection_latency.observe(latency)
    
    if result.get("is_correction"):
        passive_feedback_corrections_found.inc()
```

**MetricsEnricher:**
```python
async def enrich_response(...):
    start_time = time.time()
    success = # ... enrichment logic ...
    latency = time.time() - start_time
    
    if success:
        passive_feedback_enrichments_completed.inc()
    
    passive_feedback_enrichment_latency.observe(latency)
```

### Grafana Dashboard

**Panels:**

1. **Sessions Overview**
   - Active sessions (gauge)
   - Sessions tracked per minute (rate)
   - Memory usage (MB)

2. **Detection Performance**
   - Detections triggered per minute
   - Corrections found per minute
   - Detection rate (corrections / detections)
   - Latency P50, P95, P99

3. **Enrichment Performance**
   - Enrichments completed per minute
   - Enrichment latency P50, P95, P99
   - Enrichment failure rate

4. **System Health**
   - TimeoutProcessor errors
   - SessionManager memory
   - Query latency impact

**Alerts:**

**Critical (PagerDuty):**
- SessionManager memory > 200MB for 5 minutes
- Detection failure rate > 50% for 10 minutes
- TimeoutProcessor not running for 5 minutes

**Warning (Slack):**
- Detection rate < 10% for 30 minutes
- Enrichment latency P95 > 10s
- Query latency P95 increase > 10ms

---

## Risk Assessment

### Risk Matrix

| Risk | Probability | Impact | Severity | Mitigation |
|------|-------------|--------|----------|------------|
| Memory leak in SessionManager | Medium | High | **HIGH** | Automated cleanup + monitoring + alerts |
| Race condition in detection | Low | Medium | **MEDIUM** | Asyncio locks + unit tests |
| Database deadlock | Low | High | **MEDIUM** | Row-level locking + retry logic |
| False positive corrections | Medium | Low | **LOW** | Tune detection thresholds + manual validation |
| Performance regression | Low | Medium | **LOW** | Load testing + gradual rollout |
| Detection loop (infinite) | Low | Critical | **MEDIUM** | Mark as detected before running logic |
| Frontend not calling API | Medium | Low | **LOW** | Not applicable (automatic now) |

### Mitigation Strategies

#### Risk 1: Memory Leak in SessionManager
**Mitigation:**
- Background cleanup task removes sessions > 360s old
- Monitor `passive_feedback_session_manager_memory` metric
- Alert if > 200MB
- LRU cache with max size (future enhancement)

**Rollback Plan:**
- Set `PASSIVE_FEEDBACK_ENABLED=false`
- Restart application
- SessionManager memory clears

#### Risk 2: Race Condition in Detection
**Mitigation:**
- Use asyncio locks in SessionManager
- Atomic mark-as-detected before running logic
- Unit tests for concurrent access

**Detection:**
- Multiple detection attempts for same response in logs
- Duplicate patches in CorrectionPatchLayer

#### Risk 3: Database Deadlock
**Mitigation:**
- Use row-level locking in ResponseFeedback updates
- Retry logic with exponential backoff
- Separate transactions for detection and enrichment

**Recovery:**
- Detection runs again on next query
- Enrichment retried in next TimeoutProcessor cycle

#### Risk 4: False Positive Corrections
**Mitigation:**
- Tune detection thresholds (0.70 minimum confidence)
- Manual validation sample (100 detections/week)
- User feedback loop to improve detector

**Monitoring:**
- Track false positive rate via manual reviews
- Adjust thresholds based on precision/recall

#### Risk 5: Detection Loop (Infinite)
**Mitigation:**
- Mark response as `detected=True` BEFORE running logic
- Check `detected` flag before triggering
- Timeout processor only enriches once

**Prevention:**
```python
# CORRECT ORDER:
1. Mark as detected
2. Run detection logic
3. Handle result

# WRONG ORDER:
1. Run detection logic
2. Mark as detected  # ❌ May loop
```

---

## Appendices

### Appendix A: Configuration Reference

**Environment Variables:**

```bash
# Passive Feedback System
PASSIVE_FEEDBACK_ENABLED=true          # Enable/disable entire system
PASSIVE_FEEDBACK_TIMEOUT=180           # Detection window (seconds)
PASSIVE_FEEDBACK_CLEANUP_INTERVAL=300  # Session cleanup frequency (seconds)
PASSIVE_FEEDBACK_PROCESSOR_INTERVAL=60 # Enrichment check frequency (seconds)

# Detection Thresholds
PASSIVE_DETECTION_CONFIDENCE_MIN=0.70  # Minimum confidence to flag correction
PASSIVE_SENTIMENT_THRESHOLD=-0.35      # Frustration threshold
PASSIVE_SIMILARITY_THRESHOLD=0.75      # Same referent threshold

# Performance
PASSIVE_SESSION_MAX_SIZE=10000         # Max sessions in memory
PASSIVE_ENRICHMENT_BATCH_SIZE=100      # Responses to enrich per cycle
```

**Python Config:**
```python
# packages/amc-feedback-loop/src/amc_feedback/config.py
class FeedbackConfig(BaseModel):
    enable_passive_capture: bool = True
    passive_timeout_seconds: int = 180
    dissatisfaction_threshold: float = 0.65
    correction_confidence_min: float = 0.60
```

### Appendix B: Database Schema Changes

**No schema changes required!**

The `ResponseFeedback` table already has all necessary fields:
- `automated_category`: Will be populated by MetricsEnricher
- `automated_confidence`: Will be populated by MetricsEnricher
- `response_text`: Will be copied from QueryEvidence
- `unified_record_ref`: Will link to QueryEvidence.response_id

### Appendix C: API Endpoints Reference

**New Endpoints:**

```http
GET /api/health/passive-feedback
```
**Response:**
```json
{
  "status": "healthy",
  "session_count": 142,
  "timeout_seconds": 180,
  "active_detections": 3,
  "pending_enrichments": 12
}
```

**Modified Endpoints:**

```http
POST /api/chat
```
**Change:** Now triggers automatic follow-up detection in background
**Impact:** None (non-blocking, no API changes)

### Appendix D: Troubleshooting Guide

**Issue:** Passive feedback not working

**Symptoms:**
- No corrections detected
- Skeleton records not enriched
- Logs show no "Auto follow-up detection" messages

**Diagnosis:**
```bash
# 1. Check if enabled
curl http://localhost:8000/api/health/passive-feedback

# 2. Check logs
tail -f logs/app.log | grep "passive\|SessionManager\|TimeoutProcessor"

# 3. Check metrics
curl http://localhost:8000/metrics | grep passive_feedback
```

**Resolution:**
1. Verify `PASSIVE_FEEDBACK_ENABLED=true` in `.env`
2. Restart application
3. Check startup logs for errors
4. Verify SessionManager and TimeoutProcessor started

---

**Issue:** High memory usage

**Symptoms:**
- SessionManager memory > 100MB
- Application OOM errors
- Slow query responses

**Diagnosis:**
```bash
# Check session count
curl http://localhost:8000/api/health/passive-feedback | jq '.session_count'

# Check memory
ps aux | grep uvicorn
```

**Resolution:**
1. Reduce timeout: `PASSIVE_FEEDBACK_TIMEOUT=120`
2. Reduce cleanup interval: `PASSIVE_FEEDBACK_CLEANUP_INTERVAL=180`
3. Restart application
4. Consider Redis-backed session storage (future)

---

**Issue:** Detection latency high

**Symptoms:**
- Follow-up detection takes > 5s
- TimeoutProcessor cycles slow
- Query latency impacted

**Diagnosis:**
```bash
# Check metrics
curl http://localhost:8000/metrics | grep passive_feedback_detection_seconds
curl http://localhost:8000/metrics | grep passive_feedback_enrichment_seconds
```

**Resolution:**
1. Check database query performance
2. Add indexes if needed:
   ```sql
   CREATE INDEX idx_response_feedback_response_id 
   ON response_feedback(response_id);
   ```
3. Reduce batch size: `PASSIVE_ENRICHMENT_BATCH_SIZE=50`
4. Profile slow queries

---

### Appendix E: Code Review Checklist

**Before Merging:**

**Code Quality:**
- [ ] All functions have docstrings
- [ ] Type hints on all public methods
- [ ] No hardcoded magic numbers (use config)
- [ ] Error handling for all external calls
- [ ] Logging at appropriate levels

**Testing:**
- [ ] Unit tests for all new functions
- [ ] Integration tests for happy path
- [ ] Edge cases covered
- [ ] Test coverage > 90%
- [ ] Load tests passing

**Performance:**
- [ ] No blocking I/O in hot path
- [ ] Asyncio used correctly
- [ ] Database queries optimized
- [ ] Memory usage acceptable

**Security:**
- [ ] No SQL injection risks
- [ ] No sensitive data in logs
- [ ] Rate limiting considered
- [ ] Input validation present

**Documentation:**
- [ ] API docs updated
- [ ] Operator runbook updated
- [ ] Configuration documented
- [ ] Deployment guide complete

**Monitoring:**
- [ ] Prometheus metrics added
- [ ] Grafana dashboard created
- [ ] Alerts configured
- [ ] Logging instrumented

---

## Summary

This implementation plan provides a complete roadmap for adding passive feedback capabilities to the AMC platform. The 5-day timeline is achievable with 2 experienced backend developers.

**Key Takeaways:**

1. **Low Risk:** Uses existing infrastructure, no schema changes
2. **High Value:** Captures 5-10x more feedback data
3. **Well-Tested:** Comprehensive test strategy (70% unit, 25% integration, 5% manual)
4. **Production-Ready:** Includes monitoring, rollback plans, and troubleshooting guides
5. **Gradual Rollout:** Canary deployment minimizes production risk

**Success Metrics:**
- Passive feedback capture rate: 20-30% (vs current <5%)
- Correction detection rate: 10x increase
- Query latency impact: < 2ms P95
- All skeleton records enriched: > 95%

**Next Steps:**
1. Review and approve plan
2. Assign 2 developers
3. Create GitHub issues for each day
4. Sprint kickoff meeting
5. Begin Day 1 implementation

---

**Document Owner:** Backend Team Lead  
**Status:** READY FOR IMPLEMENTATION  
**Last Updated:** January 2025  
**Version:** 1.0
