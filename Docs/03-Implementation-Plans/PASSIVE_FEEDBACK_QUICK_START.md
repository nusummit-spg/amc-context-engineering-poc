# Passive Feedback Implementation - Quick Start Guide

**For:** Development Team  
**Duration:** 5 Days  
**Team Size:** 2 Backend Developers

---

## 🎯 Overview

Transform passive feedback from **30% implemented → 100% production-ready** in 5 days.

**What You're Building:**
- Automatic follow-up detection when users submit new queries
- Session timeout enrichment (180s window)
- Zero manual intervention required

**Expected Outcome:**
- Passive feedback capture: 20-30% (from <5%)
- 10x increase in correction detection
- <2ms query latency impact

---

## 📋 5-Day Sprint

### Day 1: SessionManager (Developer 1)
**Goal:** Track session history and enforce timeout windows

**Create:** `backend/app/feedback/session_manager.py`

**Key Components:**
```python
@dataclass
class SessionResponse:
    response_id: str
    query_text: str
    timestamp: datetime
    detected: bool = False

class SessionManager:
    _sessions: Dict[str, SessionState] = {}
    timeout_seconds: int = 180
    
    async def register_response(...) -> Optional[SessionResponse]
    async def mark_detected(...)
    async def _cleanup_expired_sessions()
```

**Tests:** `tests/test_session_manager.py` (15 tests)

**Acceptance:**
- ✅ Tracks query timestamps
- ✅ Returns previous response if within 180s
- ✅ Background cleanup working

---

### Day 2: MetricsEnricher + Chat Integration

**Morning (Developer 2): MetricsEnricher**

**Create:** `backend/app/feedback/metrics_enrichment.py`

**Key Component:**
```python
class MetricsEnricher:
    async def enrich_response(session_id, response_id) -> bool:
        # 1. Fetch ResponseFeedback (skeleton)
        # 2. Fetch QueryEvidence (telemetry)
        # 3. Calculate dwell time
        # 4. Map quality_score → automated_category
        # 5. Update database
```

**Tests:** `tests/test_metrics_enrichment.py` (12 tests)

**Acceptance:**
- ✅ Links QueryEvidence to ResponseFeedback
- ✅ Populates automated_category/confidence
- ✅ Calculates implicit signals

---

**Afternoon (Developer 1): Chat Integration**

**Modify:** `backend/app/api/routes/chat.py`

**Add Integration:**
```python
# In _run_v2_chat()
session_manager = get_session_manager()
previous_response = await session_manager.register_response(...)

if previous_response:
    asyncio.create_task(_trigger_follow_up_detection(...))
```

**Tests:** `tests/integration/test_passive_detection.py`

**Acceptance:**
- ✅ New query triggers detection automatically
- ✅ Non-blocking (background task)
- ✅ Previous response checked if within 180s

---

### Day 3: End-to-End Testing (Both Developers)

**Morning: Integration Tests**
- Test 3 trigger scenarios (new query, explicit feedback, timeout)
- Test edge cases (first query, outside timeout, concurrent queries)
- Run full regression suite

**Afternoon: Bug Fixes + Optimization**
- Fix integration issues
- Optimize memory usage
- Add logging/instrumentation
- Code review

**Acceptance:**
- ✅ All tests passing
- ✅ No performance regression
- ✅ Ready for Day 4

---

### Day 4: TimeoutProcessor + Lifecycle (Developer 1)

**Morning: TimeoutProcessor**

**Create:** `backend/app/feedback/timeout_processor.py`

**Key Component:**
```python
class TimeoutProcessor:
    check_interval: int = 60  # seconds
    
    async def _process_loop():
        while running:
            # 1. Get responses > 180s old
            # 2. Enrich each response
            # 3. Mark as processed
            await asyncio.sleep(60)
```

**Tests:** `tests/test_timeout_processor.py` (8 tests)

---

**Afternoon: Application Lifecycle**

**Modify:** `backend/app/main.py`

**Add Lifecycle Hooks:**
```python
@app.on_event("startup")
async def startup_event():
    await start_session_manager()
    await start_timeout_processor()

@app.on_event("shutdown")
async def shutdown_event():
    await stop_timeout_processor()
    await stop_session_manager()
```

**Add Health Check:**
```python
@app.get("/api/health/passive-feedback")
async def passive_feedback_health():
    return {"status": "healthy", "session_count": ...}
```

**Acceptance:**
- ✅ Background tasks start/stop gracefully
- ✅ Timeout processing works (every 60s)
- ✅ Health check responsive

---

### Day 5: Final Testing + Documentation (All)

**Morning: Comprehensive Testing**
- Full test suite (unit + integration)
- Load testing (1000 concurrent users)
- Memory leak testing
- Error handling validation

**Afternoon: Documentation**
- Update API docs
- Write operator runbook section
- Create deployment checklist
- Code review final pass

**Acceptance:**
- ✅ All tests passing (100%)
- ✅ Load test: P95 < 5ms increase
- ✅ Memory: < 20MB increase over 10K queries
- ✅ Documentation complete

---

## 🚀 Deployment Steps

### Staging (Day 6)
1. Deploy to staging
2. Run smoke tests
3. Monitor for 24 hours
4. Fix any issues

### Production (Week 2)
1. **Canary (10%):** 3 days monitoring
2. **50% Traffic:** 3 days monitoring
3. **100% Traffic:** Full rollout

---

## 📊 Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Passive feedback capture rate | 20-30% | <5% |
| Correction detection rate | 10x increase | Baseline |
| Query latency impact | <2ms P95 | 0ms |
| Skeleton records enriched | >95% | 0% |

---

## 🔧 Quick Commands

**Run Tests:**
```bash
# Unit tests
pytest tests/test_session_manager.py -v
pytest tests/test_metrics_enrichment.py -v
pytest tests/test_timeout_processor.py -v

# Integration tests
pytest tests/integration/test_passive_detection.py -v

# Load tests
locust -f tests/load/test_passive_feedback.py --users 1000
```

**Check Health:**
```bash
curl http://localhost:8000/api/health/passive-feedback
```

**View Metrics:**
```bash
curl http://localhost:8000/metrics | grep passive_feedback
```

**Check Logs:**
```bash
tail -f logs/app.log | grep "passive\|SessionManager\|TimeoutProcessor"
```

---

## 🚨 Troubleshooting

**Issue: Detection not triggering**
```bash
# Check if system enabled
curl http://localhost:8000/api/health/passive-feedback

# Check logs
tail -f logs/app.log | grep "Auto follow-up detection"

# Verify config
grep PASSIVE_FEEDBACK backend/.env
```

**Issue: High memory usage**
```bash
# Check session count
curl http://localhost:8000/api/health/passive-feedback | jq '.session_count'

# Reduce timeout if needed
echo "PASSIVE_FEEDBACK_TIMEOUT=120" >> backend/.env
```

**Issue: Enrichment failures**
```bash
# Check TimeoutProcessor logs
tail -f logs/app.log | grep "TimeoutProcessor"

# Verify QueryEvidence data exists
psql -d amc -c "SELECT COUNT(*) FROM query_evidence;"
```

---

## 📦 Files to Create

**New Files (5):**
1. `backend/app/feedback/session_manager.py`
2. `backend/app/feedback/metrics_enrichment.py`
3. `backend/app/feedback/timeout_processor.py`
4. `tests/test_session_manager.py`
5. `tests/test_metrics_enrichment.py`

**Modified Files (2):**
1. `backend/app/api/routes/chat.py` (add SessionManager integration)
2. `backend/app/main.py` (add lifecycle hooks)

---

## 🎓 Reference Documents

**Detailed Plan:**
- `Docs/03-Implementation-Plans/PASSIVE_FEEDBACK_IMPLEMENTATION_PLAN.md`

**Architecture:**
- See "Architecture Overview" section in detailed plan

**API Documentation:**
- See "Appendix C: API Endpoints Reference" in detailed plan

---

## 💡 Key Design Decisions

**Why in-memory SessionManager?**
- Sufficient for most use cases (10K sessions = ~10MB)
- No external dependencies
- Can migrate to Redis later if needed

**Why 180-second timeout?**
- User research shows corrections typically happen within 3 minutes
- Balances detection window vs memory usage
- Configurable via `PASSIVE_FEEDBACK_TIMEOUT`

**Why background task for detection?**
- Zero impact on query latency (non-blocking)
- User gets response immediately
- Detection completes asynchronously

**Why separate TimeoutProcessor?**
- Decoupled from request/response cycle
- Batch processing for efficiency
- Runs every 60s (low frequency)

---

## ✅ Final Checklist

**Before Starting:**
- [ ] Read detailed implementation plan
- [ ] Set up development environment
- [ ] Review current code (chat.py, feedback.py)
- [ ] Understand existing detection logic

**During Implementation:**
- [ ] Follow day-by-day plan
- [ ] Write tests as you code (TDD)
- [ ] Run tests frequently
- [ ] Commit after each component

**Before Deployment:**
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Load tests successful
- [ ] Deployment checklist ready

---

## 🤝 Team Communication

**Daily Standup Questions:**
1. What did you complete yesterday? (reference tasks from plan)
2. What are you working on today? (reference day/component)
3. Any blockers? (technical, dependency, unclear requirements)

**Code Review Focus:**
- Thread safety (asyncio locks used correctly?)
- Error handling (try/except for all external calls?)
- Performance (no blocking I/O in hot path?)
- Testing (coverage > 90%?)

**Slack Channels:**
- `#passive-feedback-dev` - Development discussion
- `#passive-feedback-alerts` - Monitoring alerts (production)

---

## 📞 Support

**Questions?**
- Technical: Backend Team Lead
- Process: Scrum Master
- Product: Product Owner

**Documentation:**
- Full plan: `Docs/03-Implementation-Plans/PASSIVE_FEEDBACK_IMPLEMENTATION_PLAN.md`
- Architecture: See plan Section 3
- API: See plan Appendix C

---

**Last Updated:** January 2025  
**Version:** 1.0  
**Status:** READY FOR IMPLEMENTATION
