Perfect! I'll create a comprehensive implementation plan. Let me gather a bit more context first to ensure accuracy.Perfect! Now I have everything I need. Let me create the comprehensive implementation plan.Excellent! Now let me create the detailed implementation plan document:

# **IMPLEMENTATION PLAN: LATENCY OPTIMIZATION, INTEGRATION VALIDATION & PHASE 2 MODULARIZATION**

---

## **EXECUTIVE SUMMARY**

This plan addresses three critical objectives for the AMC Context Engineering platform:

1. **Complete latency optimizations** by deploying ONNX GLiNER (4-8x NER speedup expected)
2. **Validate integration health** of the three core modules (AMC Platform, Feedback Loop, Repair Engine)
3. **Execute Phase 2 modularization** to create independent, reusable microservices

**Timeline:** 6-8 weeks  
**Team:** 2-3 developers  
**Risk Level:** Medium (modularization requires careful refactoring)

---

## **PROBLEM STATEMENT**

### Current State
- ✅ AMC Platform is production-ready (8.3/10 rating)
- ✅ All three modules integrated and functional
- ✅ Most latency optimizations deployed (async, streaming, HTTP/2, indexes)
- ⚠️ **ONNX GLiNER not deployed** - NER still using slow PyTorch CPU inference (9-30s bottleneck)
- ⚠️ **Monolithic architecture** - Cannot reuse modules in other projects
- ⚠️ **Tight coupling** - Difficult to scale or deploy modules independently

### Target State
- ✅ ONNX GLiNER deployed - NER latency reduced to 0.03-0.15s (95% reduction)
- ✅ Three independent services - `amc-platform`, `amc-feedback-loop`, `amc-repair-engine`
- ✅ Clean API boundaries - Services communicate via REST/gRPC
- ✅ Plug-and-play architecture - Modules can be used standalone or composed
- ✅ Independent scaling - Each service scales based on its load characteristics

---

## **REQUIREMENTS GATHERING**

Based on our discussion, here are the clarified requirements:

### **1. ONNX GLiNER Deployment**

**Q1: What NER performance target are we aiming for?**
- **Answer:** Sub-second NER processing (currently 9-30s on CPU)
- **Target:** 0.03-0.15s per query (4-8x speedup via ONNX INT8 quantization)

**Q2: Can we accept accuracy tradeoff for speed?**
- **Answer:** Minimal accuracy loss acceptable (< 2% F1 score degradation)
- **Validation:** Benchmark on existing test queries before production deployment

**Q3: What's the fallback strategy if ONNX fails?**
- **Answer:** Graceful fallback to PyTorch GLiNER (already implemented in code)
- **Monitoring:** Log ONNX load failures and alert if fallback rate > 5%

### **2. Integration Health Validation**

**Q1: What constitutes "healthy" integration?**
- **Answer:** 
  - Feedback loop closes (corrections reach Neo4j) ✅
  - Background jobs run on schedule (SEBI polling, governance batch) ✅
  - No data loss at module boundaries ✅
  - Response times within SLA (< 2s p95) ✅

**Q2: How will we validate the feedback loop?**
- **Answer:** 
  - Submit user feedback → verify stored in SQLite
  - Trigger evaluation → verify patch created in correction layer
  - Run governance batch → verify correction promoted to Neo4j
  - Query system → verify corrected value returned

**Q3: What's the test coverage requirement?**
- **Answer:** 
  - End-to-end journey tests (user query → feedback → correction → retrieval)
  - Background job execution tests
  - Module boundary tests (data contracts)
  - Minimum 80% code coverage for new integration code

### **3. Phase 2 Modularization Strategy**

**Q1: What defines a "service" vs a "package"?**
- **Answer:**
  - **Package:** Pip-installable Python library (e.g., `pip install amc-feedback-loop`)
  - **Service:** Independent deployment with its own API, database, resources
  - **Both:** Start as packages, optionally deployable as services

**Q2: How do services communicate?**
- **Answer:**
  - **Primary:** REST APIs with JSON payloads
  - **Future:** Consider gRPC for high-throughput internal communication
  - **Auth:** JWT tokens passed between services

**Q3: Can services share databases?**
- **Answer:**
  - **Phase 2.1 (Packages):** Shared database acceptable (SQLite/PostgreSQL)
  - **Phase 2.2 (Services):** Each service gets own database schema/namespace
  - **Phase 3 (Enterprise):** Fully separate databases per service

**Q4: What happens to the current monolith?**
- **Answer:**
  - Refactored to "AMC Platform Orchestrator"
  - Imports feedback-loop and repair-engine as packages
  - Coordinates workflow across modules
  - Remains the primary deployment for MVP

**Q5: How do we handle shared dependencies (Neo4j, FAISS)?**
- **Answer:**
  - **Neo4j:** Accessed via graph adapter interface (each service can connect)
  - **FAISS:** Owned by AMC Platform, exposed via vector search API
  - **Redis:** Shared for caching (with namespaced keys per service)

---

## **BACKGROUND RESEARCH**

### **Technology Stack Decisions**

| Component | Current | Phase 2 Target | Rationale |
|-----------|---------|----------------|-----------|
| **Packaging** | Monolithic app | Pyproject.toml packages | Standard Python packaging, pip-installable |
| **Inter-service** | Direct imports | REST APIs | Language-agnostic, network boundaries |
| **Configuration** | .env files | Pydantic Settings | Type-safe, validated, documented |
| **Adapters** | Hardcoded | Interface + Impl | Dependency injection, testability |
| **Deployment** | Single container | Docker Compose | Multi-container orchestration |

### **Architecture Patterns**

**1. Adapter Pattern** - For database and external services
```python
# Interface
class DatabaseAdapter(ABC):
    @abstractmethod
    async def store_feedback(self, feedback: Feedback) -> str: ...

# Implementation
class SQLiteAdapter(DatabaseAdapter):
    async def store_feedback(self, feedback: Feedback) -> str:
        # SQLite-specific logic
        
class PostgreSQLAdapter(DatabaseAdapter):
    async def store_feedback(self, feedback: Feedback) -> str:
        # PostgreSQL-specific logic
```

**2. Facade Pattern** - For service interfaces
```python
# amc_feedback package exposes simple interface
from amc_feedback import FeedbackLoop

loop = FeedbackLoop(config=config, db_adapter=adapter)
claim = await loop.process_feedback(...)
```

**3. Circuit Breaker** - For inter-service calls
```python
from pybreaker import CircuitBreaker

breaker = CircuitBreaker(fail_max=5, timeout_duration=60)

@breaker
async def call_repair_service(patch_data):
    return await httpx.post(f"{REPAIR_SERVICE_URL}/patches", json=patch_data)
```

### **Existing Codebases to Learn From**

1. **Langchain** - Modular LLM orchestration with clean abstractions
2. **FastAPI Template (tiangolo)** - Microservices best practices
3. **Netflix Conductor** - Workflow orchestration patterns
4. **Feedback-Loop Package** - Already exists at `git+https://github.com/nusummit-spg/human-feedback-loop@v0.1.5`

---

## **PROPOSED SOLUTION**

### **High-Level Architecture**

```mermaid
graph TB
    subgraph "Phase 2: Microservices Architecture"
        CLIENT[React Frontend]
        
        subgraph "Service 1: AMC Platform Orchestrator"
            API[FastAPI Gateway]
            ORCH[Query Orchestrator]
            VECTOR[FAISS Vector Store]
            GRAPH[Neo4j Connector]
        end
        
        subgraph "Service 2: Feedback Loop Service"
            FB_API[Feedback API]
            NER[NER Pipeline<br/>ONNX GLiNER]
            MATCHER[Entity Matcher]
            DETECTOR[Dissatisfaction Detector]
        end
        
        subgraph "Service 3: Repair Engine Service"
            REPAIR_API[Repair API]
            PATCH[Correction Patch Layer]
            EVAL[Evaluation Router]
            GOV[Governance Batch]
        end
        
        subgraph "Shared Infrastructure"
            NEO4J[(Neo4j Graph)]
            REDIS[(Redis Cache)]
            POSTGRES[(PostgreSQL)]
        end
    end
    
    CLIENT -->|Query| API
    API --> ORCH
    ORCH -->|Retrieval| VECTOR
    ORCH -->|Traversal| GRAPH
    ORCH -->|Apply Patches| REPAIR_API
    
    API -->|Submit Feedback| FB_API
    FB_API --> NER
    NER --> MATCHER
    MATCHER --> DETECTOR
    DETECTOR -->|Create Patch| REPAIR_API
    
    REPAIR_API --> PATCH
    PATCH --> EVAL
    GOV -->|Promote| NEO4J
    
    ORCH --> NEO4J
    PATCH --> REDIS
    FB_API --> POSTGRES
    EVAL --> POSTGRES
```

### **Service Boundaries**

#### **Service 1: AMC Platform Orchestrator**
**Responsibilities:**
- Handle user queries
- Orchestrate retrieval (vector + graph)
- Synthesize answers with LLM
- Apply correction patches to context
- Manage caching and performance

**APIs:**
- `POST /api/query` - Submit query
- `POST /api/chat` - Multi-turn conversation
- `GET /api/query/{query_id}/status` - Query status
- `GET /api/health` - Health check

**Dependencies:**
- `amc-repair-engine` (for applying patches)
- Neo4j (graph traversal)
- FAISS (vector search)
- Groq/Claude (LLM synthesis)

#### **Service 2: Feedback Loop**
**Responsibilities:**
- Capture user feedback (active + passive)
- Extract structured corrections
- Resolve entity mentions
- Detect dissatisfaction patterns
- Build unified evaluation records

**APIs:**
- `POST /api/feedback` - Submit feedback
- `POST /api/feedback/follow-up-detection` - Auto-detect corrections
- `GET /api/feedback/{feedback_id}` - Get feedback details
- `GET /api/feedback/recent` - Recent feedback list

**Dependencies:**
- NER pipeline (spaCy + ONNX GLiNER)
- Fund master catalog
- PostgreSQL (feedback storage)

#### **Service 3: Repair Engine**
**Responsibilities:**
- Store correction patches (Redis + memory)
- Evaluate answer quality (Tier 1/2/3)
- Run governance batch (weekly)
- Promote approved corrections to Neo4j
- Provide patches for retrieval context injection

**APIs:**
- `POST /api/patches` - Create correction patch
- `GET /api/patches` - List pending patches
- `POST /api/patches/{patch_id}/approve` - Approve patch
- `POST /api/patches/batch-approve` - Batch approve
- `GET /api/patches/for-entities` - Get patches for entity list
- `POST /api/governance/run-batch` - Manual governance run

**Dependencies:**
- Redis (patch storage)
- Neo4j (graph mutations)
- PostgreSQL (evaluation records)

---

## **TASK BREAKDOWN**

### **PHASE 1: ONNX OPTIMIZATION (Week 1-2)**

#### **Task 1: Verify ONNX GLiNER Status**
**Duration:** 1 day

**Steps:**
1. Check if `streamlit_app/models/` or `backend/models/` directory exists
2. Look for `gliner_quantized.onnx` file (~95MB)
3. Review `ner_pipeline.py` ONNX loading logic (already exists)
4. Check `ENABLE_ONNX_GLINER` config flag

**Deliverables:**
- Status report: ONNX model exists (Yes/No)
- If No: Create export script
- If Yes: Verify model loads correctly

**Acceptance Criteria:**
- ✅ Know exact status of ONNX deployment
- ✅ Have working export script if needed

---

#### **Task 2: Deploy ONNX GLiNER Model**
**Duration:** 2-3 days

**Step 2.1: Create Export Script**
Create `backend/scripts/export_gliner_onnx.py`:

```python
"""
Export GLiNER to ONNX INT8 quantized format.
Run once to generate models/gliner_quantized.onnx (~95MB, down from ~380MB fp32).
"""
import torch
from pathlib import Path
from gliner import GLiNER
from onnxruntime.quantization import quantize_dynamic, QuantType

# Configuration
MODEL_ID = "urchade/gliner_medium-v2.1"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models"
OUTPUT_DIR.mkdir(exist_ok=True)

def export_to_onnx():
    """Export GLiNER to ONNX format."""
    print(f"Loading GLiNER model: {MODEL_ID}")
    model = GLiNER.from_pretrained(MODEL_ID)
    
    # Export to ONNX (FP32)
    fp32_path = OUTPUT_DIR / "gliner_medium_fp32.onnx"
    print(f"Exporting to ONNX FP32: {fp32_path}")
    
    dummy_input = {
        "input_ids": torch.randint(0, 1000, (1, 512)),
        "attention_mask": torch.ones(1, 512, dtype=torch.long),
    }
    
    torch.onnx.export(
        model.model,
        (dummy_input,),
        str(fp32_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence"},
            "attention_mask": {0: "batch_size", 1: "sequence"},
            "logits": {0: "batch_size", 1: "sequence"}
        },
        opset_version=14
    )
    
    print(f"FP32 ONNX model size: {fp32_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Quantize to INT8
    quantized_path = OUTPUT_DIR / "gliner_quantized.onnx"
    print(f"Quantizing to INT8: {quantized_path}")
    
    quantize_dynamic(
        str(fp32_path),
        str(quantized_path),
        weight_type=QuantType.QInt8,
    )
    
    print(f"Quantized ONNX model size: {quantized_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"\n✅ Export complete! ONNX model ready at: {quantized_path}")
    
    # Cleanup FP32 intermediate
    fp32_path.unlink()
    print("Cleaned up intermediate FP32 model")

if __name__ == "__main__":
    export_to_onnx()
```

**Step 2.2: Run Export**
```bash
cd backend
python scripts/export_gliner_onnx.py
```

**Expected output:**
- `backend/models/gliner_quantized.onnx` (~95MB)
- Console log showing size reduction (380MB → 95MB)

**Step 2.3: Enable ONNX in Config**
Update `backend/.env`:
```bash
ENABLE_ONNX_GLINER=true
```

**Step 2.4: Verify Loading**
The code in `ner_pipeline.py` already handles ONNX loading:
```python
onnx_path = config.PROJECT_ROOT / "models" / "gliner_quantized.onnx"
if config.ENABLE_ONNX_GLINER and onnx_path.exists():
    _gliner_model = GLiNER.from_pretrained(str(onnx_path.parent), load_onnx=True)
```

Test by running:
```bash
cd backend
python -c "from app.engine.ner_pipeline import warmup; warmup()"
```

Expected output:
```
[ner-b] Loading GLiNER…
[ner-b] ONNX Quantized GLiNER ready.
[NER Warmup] Done — both models cached in memory.
```

**Step 2.5: Benchmark Performance**
Create `backend/scripts/benchmark_onnx_ner.py`:

```python
"""
Benchmark ONNX vs PyTorch GLiNER performance.
"""
import time
from app.engine import ner_pipeline

TEST_QUERIES = [
    "What is the TER of Axis Bluechip Fund?",
    "How is HDFC Balanced Advantage Fund performing compared to its benchmark?",
    "What are SEBI regulations for debt mutual funds?",
    "Show me ESG scores for Adani Enterprises and Adani Ports",
]

def benchmark_ner(num_runs=10):
    results = []
    
    for query in TEST_QUERIES:
        times = []
        for _ in range(num_runs):
            start = time.perf_counter()
            entities = ner_pipeline.run_layers_ab(query)
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)  # Convert to ms
        
        avg_time = sum(times) / len(times)
        results.append({
            "query": query[:50] + "..." if len(query) > 50 else query,
            "avg_ms": avg_time,
            "entities_found": len(entities)
        })
    
    return results

if __name__ == "__main__":
    print("Benchmarking NER Pipeline (ONNX GLiNER)")
    print("=" * 80)
    
    results = benchmark_ner()
    
    for r in results:
        print(f"\nQuery: {r['query']}")
        print(f"  Avg Time: {r['avg_ms']:.1f}ms")
        print(f"  Entities: {r['entities_found']}")
    
    overall_avg = sum(r['avg_ms'] for r in results) / len(results)
    print(f"\n{'=' * 80}")
    print(f"Overall Average: {overall_avg:.1f}ms per query")
    
    # Target metrics
    if overall_avg < 150:
        print("✅ EXCELLENT - ONNX optimization successful (< 150ms)")
    elif overall_avg < 500:
        print("✅ GOOD - Acceptable performance (< 500ms)")
    else:
        print("⚠️ SLOW - Consider debugging ONNX configuration")
```

Run benchmark:
```bash
python scripts/benchmark_onnx_ner.py
```

**Expected Results:**
- **Before (PyTorch CPU):** 9,000-30,000ms per query
- **After (ONNX INT8):** 30-150ms per query
- **Speedup:** 60-200x (4-8x if GPU was baseline)

**Deliverables:**
- ✅ `models/gliner_quantized.onnx` file exists
- ✅ NER pipeline loads ONNX model successfully
- ✅ Benchmark results showing < 150ms average
- ✅ Documentation of export process

**Acceptance Criteria:**
- ✅ ONNX model size ~95MB (not 380MB)
- ✅ NER latency < 150ms (was 9,000-30,000ms)
- ✅ Entity extraction accuracy within 2% of PyTorch baseline
- ✅ Graceful fallback to PyTorch if ONNX fails

**Demo:**
After completion, demonstrate:
1. Submit query "What is TER of Axis Bluechip Fund?"
2. Show backend logs: `[ner-b] ONNX Quantized GLiNER ready.`
3. Show response time < 2 seconds (previously 10-30 seconds)

---

### **PHASE 2: INTEGRATION VALIDATION (Week 2-3)**

#### **Task 3: Validate Three-Module Integration**
**Duration:** 3-4 days

**Step 3.1: End-to-End Feedback Loop Test**
Create `backend/tests/integration/test_complete_feedback_loop.py`:

```python
"""
Integration test: Complete feedback loop from query to Neo4j correction.
"""
import pytest
import asyncio
from app.api.deps import get_container
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.tasks.governance_batch import run_governance_batch

@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_feedback_loop():
    """
    User journey:
    1. Submit query → Get answer
    2. Submit feedback → Create correction
    3. Run governance → Promote to Neo4j
    4. Re-query → Get corrected answer
    """
    container = get_container()
    orchestrator = container.orchestrator
    patch_layer = get_correction_patch_layer()
    
    # Step 1: Submit initial query
    query = "What is the TER of Axis Bluechip Fund?"
    intent, retrieval, context, synthesis = await orchestrator.answer(query)
    
    original_answer = synthesis.answer
    response_id = synthesis.response_id
    
    assert "TER" in original_answer or "expense" in original_answer
    print(f"✓ Step 1: Got answer with response_id={response_id}")
    
    # Step 2: Submit correction feedback
    # Simulate user saying "Actually, TER is 0.82%, not 0.79%"
    feedback_payload = {
        "response_id": response_id,
        "feedback_text": "The TER is actually 0.82%, not what you said",
        "issue_types": ["F02-Accuracy"],
        "source": "web_interface"
    }
    
    # Manually trigger feedback processing
    from app.services.feedback import trigger_feedback_loop
    feedback_id = await trigger_feedback_loop(feedback_payload)
    
    assert feedback_id is not None
    print(f"✓ Step 2: Feedback processed, feedback_id={feedback_id}")
    
    # Step 3: Verify patch created
    # Check correction patch layer has pending patch
    patches = await patch_layer.get_pending_corrections()
    assert len(patches) > 0, "No patches found after feedback"
    
    target_patch = next(
        (p for p in patches if p.get("attribute") == "TER"), 
        None
    )
    assert target_patch is not None, "TER correction patch not found"
    print(f"✓ Step 3: Correction patch created: {target_patch}")
    
    # Step 4: Run governance batch
    report = await run_governance_batch(auto_approve_threshold=0.75)
    
    assert report["total_evaluated"] > 0
    assert report["approved"] > 0 or report["needs_review"] > 0
    print(f"✓ Step 4: Governance batch complete: {report}")
    
    # Step 5: Verify correction in Neo4j (if approved)
    if report["approved"] > 0:
        # Query Neo4j directly to verify
        from app.engine.graph_store import get_driver
        driver = get_driver()
        
        async with driver.session() as session:
            result = await session.run("""
                MATCH (e:Entity {name: 'Axis Bluechip Fund'})
                RETURN e.TER as ter, e.TER_updated_at as updated
            """)
            record = await result.single()
            
            if record:
                assert record["ter"] == "0.82" or record["ter"] == 0.82
                print(f"✓ Step 5: Neo4j updated with TER={record['ter']}")
            else:
                print("⚠ Step 5: Entity not found in Neo4j (may need seed data)")
    
    # Step 6: Re-query and verify corrected value
    intent2, retrieval2, context2, synthesis2 = await orchestrator.answer(query)
    
    new_answer = synthesis2.answer
    
    # Check if correction is reflected (either from patch or Neo4j)
    assert "0.82" in new_answer or synthesis2.graph_facts
    print(f"✓ Step 6: Re-query returns corrected data: {new_answer[:100]}...")
    
    print("\n✅ COMPLETE FEEDBACK LOOP VALIDATED")
    print(f"   Query → Feedback → Patch → Governance → Neo4j → Re-query")

```

Run test:
```bash
cd backend
pytest tests/integration/test_complete_feedback_loop.py -v -s
```

**Step 3.2: Background Job Validation**
Create `backend/tests/integration/test_background_jobs.py`:

```python
"""
Validate background scheduler jobs execute correctly.
"""
import pytest
from app.tasks.scheduler import get_scheduler

@pytest.mark.integration
def test_background_jobs_registered():
    """Verify all 5 background jobs are registered."""
    scheduler = get_scheduler()
    
    expected_jobs = [
        "sebi_rss_polling",
        "regulatory_staleness_check",
        "weekly_governance_batch",
        "cache_maintenance",
        "metrics_aggregation"
    ]
    
    registered_jobs = [job.id for job in scheduler.get_jobs()]
    
    for job_id in expected_jobs:
        assert job_id in registered_jobs, f"Job {job_id} not registered"
        print(f"✓ Job registered: {job_id}")
    
    print("\n✅ All background jobs registered")

@pytest.mark.integration
async def test_governance_batch_execution():
    """Manually trigger governance batch and verify it runs."""
    from app.tasks.governance_batch import run_governance_batch
    
    report = await run_governance_batch()
    
    assert "total_evaluated" in report
    assert "approved" in report
    assert "rejected" in report
    assert "needs_review" in report
    
    print(f"✓ Governance batch executed successfully")
    print(f"  Total Evaluated: {report['total_evaluated']}")
    print(f"  Approved: {report['approved']}")
    print(f"  Rejected: {report['rejected']}")
    print(f"  Needs Review: {report['needs_review']}")
    
    print("\n✅ Governance batch working")
```

Run test:
```bash
pytest tests/integration/test_background_jobs.py -v -s
```

**Deliverables:**
- ✅ End-to-end feedback loop test passing
- ✅ Background jobs test passing
- ✅ Integration health report

**Acceptance Criteria:**
- ✅ Feedback → Patch → Governance → Neo4j flow works
- ✅ All 5 background jobs registered and executable
- ✅ No data loss at module boundaries
- ✅ Response times within SLA (< 2s p95)

**Demo:**
Show test output proving:
1. Query returns answer
2. Feedback creates patch
3. Governance promotes correction
4. Re-query returns corrected value

---

### **PHASE 3: MICROSERVICES DESIGN (Week 3-4)**

#### **Task 4: Design Phase 2 Architecture**
**Duration:** 3-4 days

**Step 4.1: Define Service Contracts**

Create `Docs/03-Implementation-Plans/phase2_service_contracts.md`:

```markdown
# Phase 2: Service Contracts

## Service 1: AMC Platform Orchestrator

### Endpoints
- POST /api/query
- POST /api/chat
- POST /api/query/{query_id}/status
- GET /api/health

### Dependencies
- Feedback Loop Service (for follow-up detection)
- Repair Engine Service (for patch application)
- Neo4j (direct connection)
- FAISS (local)

### Data Ownership
- Query history
- Session data
- FAISS indexes
- Cache (shared Redis)

---

## Service 2: Feedback Loop Service

### Endpoints
- POST /api/feedback
- POST /api/feedback/follow-up-detection
- GET /api/feedback/{feedback_id}
- GET /api/feedback/recent
- POST /api/unified-evaluation/build
- GET /api/health

### Dependencies
- Repair Engine Service (to create patches)
- PostgreSQL (feedback + evaluation tables)
- NER models (local)
- Fund master catalog (local)

### Data Ownership
- response_feedback table
- query_evidence table
- unified_evaluation_records table
- NER cache

---

## Service 3: Repair Engine Service

### Endpoints
- POST /api/patches
- GET /api/patches
- GET /api/patches/pending
- GET /api/patches/for-entities?entity_ids=...
- POST /api/patches/{patch_id}/approve
- POST /api/patches/{patch_id}/reject
- POST /api/patches/batch-approve
- POST /api/governance/run-batch
- GET /api/evaluation/evaluate
- GET /api/health

### Dependencies
- Neo4j (for graph mutations)
- Redis (patch storage)
- PostgreSQL (evaluation records)

### Data Ownership
- Correction patches (Redis + backup in PostgreSQL)
- Evaluation history
- Governance batch logs

---

## Inter-Service Authentication

### JWT Token Format
```json
{
  "sub": "service:amc-platform",
  "role": "service",
  "permissions": ["query:execute", "patches:read"],
  "exp": 1234567890
}
```

### Service-to-Service Headers
```http
Authorization: Bearer <JWT_TOKEN>
X-Request-ID: <UUID>
X-Correlation-ID: <TRACE_ID>
X-Service-Name: amc-platform
```

---

## Database Separation Strategy

### Phase 2.1 (Shared PostgreSQL)
```
PostgreSQL Database: amc_platform
├── Schema: public (AMC Platform tables)
├── Schema: feedback (Feedback Loop tables)
└── Schema: repair (Repair Engine tables)
```

### Phase 2.2 (Namespace separation)
```
PostgreSQL Database: amc_platform
├── feedback_* tables (owned by feedback service)
├── repair_* tables (owned by repair service)
└── platform_* tables (owned by platform service)
```

### Phase 3 (Separate databases)
```
PostgreSQL Instance
├── Database: amc_platform
├── Database: amc_feedback
└── Database: amc_repair
```
```

**Step 4.2: Create Architecture Diagram**

Create `Docs/09-Diagrams-and-Presentations/phase2_architecture.mermaid`:

```mermaid
graph TB
    subgraph "External"
        USER[User Browser]
        ADMIN[Admin Dashboard]
    end
    
    subgraph "API Gateway Layer"
        NGINX[NGINX Load Balancer<br/>:80, :443]
    end
    
    subgraph "Service Layer"
        direction LR
        
        subgraph "AMC Platform"
            PLATFORM_API[FastAPI<br/>:8000]
            ORCHESTRATOR[Query Orchestrator]
            VECTOR[FAISS Store]
        end
        
        subgraph "Feedback Loop"
            FB_API[FastAPI<br/>:8001]
            NER[NER Pipeline<br/>ONNX GLiNER]
            MATCHER[Entity Matcher]
        end
        
        subgraph "Repair Engine"
            REPAIR_API[FastAPI<br/>:8002]
            PATCH[Patch Layer]
            GOV[Governance]
        end
    end
    
    subgraph "Data Layer"
        NEO4J[(Neo4j<br/>:7687)]
        REDIS[(Redis<br/>:6379)]
        POSTGRES[(PostgreSQL<br/>:5432)]
    end
    
    USER --> NGINX
    ADMIN --> NGINX
    
    NGINX --> PLATFORM_API
    NGINX --> FB_API
    NGINX --> REPAIR_API
    
    PLATFORM_API -->|Query entities| FB_API
    PLATFORM_API -->|Get patches| REPAIR_API
    FB_API -->|Create patch| REPAIR_API
    
    PLATFORM_API --> NEO4J
    PLATFORM_API --> REDIS
    FB_API --> POSTGRES
    REPAIR_API --> NEO4J
    REPAIR_API --> REDIS
    REPAIR_API --> POSTGRES
```

**Step 4.3: Document Deployment Strategy**

Create `Docs/05-Operations-and-Deployment/phase2_deployment.md`:

```markdown
# Phase 2 Deployment Strategy

## Local Development (Docker Compose)

### docker-compose.yml
```yaml
version: '3.8'

services:
  # Infrastructure
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: amc_platform
      POSTGRES_USER: amc
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  neo4j:
    image: neo4j:5.13
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    volumes:
      - neo4j_data:/data
    ports:
      - "7474:7474"
      - "7687:7687"

  # Services
  amc-platform:
    build:
      context: ./backend
      dockerfile: Dockerfile.platform
    environment:
      - DATABASE_URL=postgresql://amc:${POSTGRES_PASSWORD}@postgres:5432/amc_platform
      - REDIS_URL=redis://redis:6379
      - NEO4J_URI=bolt://neo4j:7687
      - FEEDBACK_SERVICE_URL=http://feedback:8001
      - REPAIR_SERVICE_URL=http://repair:8002
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - neo4j
      - feedback
      - repair

  feedback:
    build:
      context: ./backend
      dockerfile: Dockerfile.feedback
    environment:
      - DATABASE_URL=postgresql://amc:${POSTGRES_PASSWORD}@postgres:5432/amc_platform
      - REPAIR_SERVICE_URL=http://repair:8002
    ports:
      - "8001:8001"
    depends_on:
      - postgres

  repair:
    build:
      context: ./backend
      dockerfile: Dockerfile.repair
    environment:
      - DATABASE_URL=postgresql://amc:${POSTGRES_PASSWORD}@postgres:5432/amc_platform
      - REDIS_URL=redis://redis:6379
      - NEO4J_URI=bolt://neo4j:7687
    ports:
      - "8002:8002"
    depends_on:
      - postgres
      - redis
      - neo4j

  # Frontend
  frontend:
    build:
      context: ./mf-context-engine
      dockerfile: Dockerfile
    environment:
      - VITE_API_URL=http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - amc-platform

volumes:
  postgres_data:
  redis_data:
  neo4j_data:
```

### Start services
```bash
docker-compose up -d
```

### Check health
```bash
curl http://localhost:8000/api/health  # Platform
curl http://localhost:8001/api/health  # Feedback
curl http://localhost:8002/api/health  # Repair
```

## Production Deployment (Kubernetes)

### Coming in Phase 3...
- Kubernetes manifests
- Helm charts
- Auto-scaling policies
- Monitoring (Prometheus + Grafana)
```

**Deliverables:**
- ✅ Service contracts documented
- ✅ Architecture diagram created
- ✅ Deployment strategy defined
- ✅ Database separation plan

**Acceptance Criteria:**
- ✅ Clear API boundaries between services
- ✅ Authentication/authorization strategy defined
- ✅ Data ownership clearly delineated
- ✅ Deployment plan validated by team

**Demo:**
Present architecture diagrams and service contracts to team for approval.

---

### **PHASE 4: PACKAGE EXTRACTION (Week 4-6)**

#### **Task 5: Extract amc-feedback-loop Package**
**Duration:** 5-6 days

**Step 5.1: Create Package Structure**

```bash
mkdir -p packages/amc-feedback-loop
cd packages/amc-feedback-loop
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "amc-feedback-loop"
version = "0.1.0"
description = "Reusable feedback loop for RAG systems with NER, entity resolution, and correction extraction"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Proprietary"}
authors = [
    {name = "NuSummit Technologies", email = "dev@nusummit.com"}
]
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "spacy>=3.7",
    "gliner>=0.2",
    "rapidfuzz>=3.0",
    "sentence-transformers>=3.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",  # For PostgreSQL async
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "black>=24.0",
    "ruff>=0.3",
]

[tool.hatch.build.targets.wheel]
packages = ["src/amc_feedback"]
```

**Step 5.2: Extract Core Logic**

Create package structure:
```
packages/amc-feedback-loop/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── amc_feedback/
│       ├── __init__.py
│       ├── config.py
│       ├── capture.py
│       ├── ner.py
│       ├── matcher.py
│       ├── detector.py
│       ├── extractor.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── database.py
│       │   └── evidence.py
│       └── schemas.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_ner.py
│   ├── test_matcher.py
│   ├── test_detector.py
│   └── test_extractor.py
└── examples/
    └── standalone_usage.py
```

**Step 5.3: Implement Config-Driven Design**

`src/amc_feedback/config.py`:
```python
"""
Configuration schema for feedback loop.
Allows users to customize behavior without modifying code.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class FeedbackConfig(BaseModel):
    """Configuration for feedback loop behavior."""
    
    # Domain Configuration
    domain_name: str = Field(default="amc", description="Domain identifier (amc, healthcare, etc.)")
    entity_types: List[str] = Field(
        default=["fund", "scheme", "amc", "regulation"],
        description="Entity types to recognize"
    )
    attribute_keywords: Dict[str, List[str]] = Field(
        default={
            "TER": ["ter", "expense ratio", "total expense"],
            "NAV": ["nav", "net asset value", "price"],
            "AUM": ["aum", "assets under management", "corpus"],
        },
        description="Attribute detection keywords"
    )
    
    # Entity Resolution
    entity_master_path: Optional[str] = Field(
        default=None,
        description="Path to entity catalog JSON file"
    )
    fuzzy_match_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum similarity for fuzzy matching"
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model for semantic matching"
    )
    
    # NER Configuration
    use_spacy: bool = Field(default=True, description="Enable spaCy Layer A")
    use_gliner: bool = Field(default=True, description="Enable GLiNER Layer B")
    gliner_model_id: str = Field(
        default="urchade/gliner_medium-v2.1",
        description="HuggingFace model ID for GLiNER"
    )
    enable_onnx: bool = Field(
        default=True,
        description="Use ONNX quantized GLiNER if available"
    )
    
    # Detection Thresholds
    dissatisfaction_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for correction detection"
    )
    correction_confidence_min: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to create correction patch"
    )
    
    # Passive Feedback
    enable_passive_capture: bool = Field(
        default=True,
        description="Enable automatic follow-up correction detection"
    )
    passive_timeout_seconds: int = Field(
        default=180,
        ge=30,
        description="Timeout for follow-up detection window"
    )
    
    # Storage
    database_adapter: str = Field(
        default="sqlite",
        description="Database adapter type (sqlite, postgresql, custom)"
    )
    evidence_adapter: str = Field(
        default="local",
        description="Evidence storage adapter (local, s3, custom)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "domain_name": "amc",
                "entity_types": ["fund", "scheme"],
                "fuzzy_match_threshold": 0.75,
                "enable_passive_capture": True
            }
        }
```

**Step 5.4: Create Adapter Interfaces**

`src/amc_feedback/adapters/base.py`:
```python
"""
Base adapter interfaces for dependency injection.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class DatabaseAdapter(ABC):
    """Interface for database operations."""
    
    @abstractmethod
    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        """Store feedback record and return feedback_id."""
        pass
    
    @abstractmethod
    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback by ID."""
        pass
    
    @abstractmethod
    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        """Store unified evaluation record."""
        pass
    
    @abstractmethod
    async def close(self):
        """Cleanup database connections."""
        pass


class EvidenceAdapter(ABC):
    """Interface for evidence pack storage."""
    
    @abstractmethod
    async def store_evidence(
        self,
        response_id: str,
        evidence: Dict[str, Any]
    ) -> str:
        """Store evidence pack and return storage path/ID."""
        pass
    
    @abstractmethod
    async def retrieve_evidence(self, response_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve evidence pack by response_id."""
        pass
```

`src/amc_feedback/adapters/database.py`:
```python
"""
Concrete database adapter implementations.
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional
from .base import DatabaseAdapter

class SQLiteAdapter(DatabaseAdapter):
    """SQLite implementation of database adapter."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS response_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    feedback_text TEXT NOT NULL,
                    issue_types TEXT NOT NULL,  -- JSON array
                    source TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT  -- JSON
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS unified_evaluation_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id INTEGER NOT NULL,
                    response_id TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT NOT NULL,  -- JSON
                    FOREIGN KEY (feedback_id) REFERENCES response_feedback(id)
                );
            """)
            conn.commit()
        finally:
            conn.close()
    
    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        """Store feedback and return ID."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                INSERT INTO response_feedback 
                (session_id, response_id, feedback_text, issue_types, source, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                response_id,
                feedback_text,
                json.dumps(issue_types),
                source,
                json.dumps(kwargs)
            ))
            conn.commit()
            return str(cursor.lastrowid)
        finally:
            conn.close()
    
    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT * FROM response_feedback WHERE id = ?
            """, (feedback_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "response_id": row["response_id"],
                    "feedback_text": row["feedback_text"],
                    "issue_types": json.loads(row["issue_types"]),
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                }
            return None
        finally:
            conn.close()
    
    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        """Store unified evaluation record."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                INSERT INTO unified_evaluation_records
                (feedback_id, response_id, query_text, response_text, data)
                VALUES (?, ?, ?, ?, ?)
            """, (
                record["feedback_id"],
                record["response_id"],
                record["query_text"],
                record["response_text"],
                json.dumps(record)
            ))
            conn.commit()
            return str(cursor.lastrowid)
        finally:
            conn.close()
    
    async def close(self):
        """No persistent connections in SQLite."""
        pass


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL implementation (async)."""
    
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self._pool = None
    
    async def _get_pool(self):
        """Lazy pool initialization."""
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.connection_url)
        return self._pool
    
    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        """Store feedback in PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO response_feedback
                (session_id, response_id, feedback_text, issue_types, source, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, session_id, response_id, feedback_text, issue_types, source, json.dumps(kwargs))
            return str(row["id"])
    
    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback from PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM response_feedback WHERE id = $1
            """, int(feedback_id))
            
            if row:
                return dict(row)
            return None
    
    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        """Store evaluation record in PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO unified_evaluation_records
                (feedback_id, response_id, query_text, response_text, data)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, record["feedback_id"], record["response_id"], 
            record["query_text"], record["response_text"], json.dumps(record))
            return str(row["id"])
    
    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
```

**Step 5.5: Create Main Package Interface**

`src/amc_feedback/__init__.py`:
```python
"""
AMC Feedback Loop - Reusable feedback collection and correction extraction.
"""
from .config import FeedbackConfig
from .capture import FeedbackCapture
from .ner import NERPipeline
from .matcher import EntityMatcher
from .detector import DissatisfactionDetector
from .extractor import CorrectionExtractor
from .adapters.base import DatabaseAdapter, EvidenceAdapter
from .adapters.database import SQLiteAdapter, PostgreSQLAdapter

__version__ = "0.1.0"
__all__ = [
    "FeedbackConfig",
    "FeedbackLoop",
    "DatabaseAdapter",
    "EvidenceAdapter",
    "SQLiteAdapter",
    "PostgreSQLAdapter",
]

class FeedbackLoop:
    """
    Main interface for feedback loop operations.
    
    Example:
        >>> config = FeedbackConfig(domain_name="amc")
        >>> db_adapter = SQLiteAdapter("./data.db")
        >>> loop = FeedbackLoop(config=config, db_adapter=db_adapter)
        >>> claim = await loop.process_feedback(
        ...     session_id="sess_123",
        ...     response_id="resp_456",
        ...     feedback_text="TER is 0.82%, not 0.79%",
        ...     original_query="What is TER?",
        ...     original_response="TER is 0.79%"
        ... )
    """
    
    def __init__(
        self,
        config: FeedbackConfig,
        db_adapter: DatabaseAdapter,
        evidence_adapter: Optional[EvidenceAdapter] = None
    ):
        self.config = config
        self.db = db_adapter
        self.evidence = evidence_adapter
        
        # Initialize components
        self.ner = NERPipeline(config)
        self.matcher = EntityMatcher(config)
        self.detector = DissatisfactionDetector(config)
        self.extractor = CorrectionExtractor(config, self.ner, self.matcher)
    
    async def process_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str,
        original_response: str,
        issue_types: Optional[List[str]] = None,
        source: str = "web_interface"
    ) -> Optional["CorrectionClaim"]:
        """
        Process user feedback and extract structured correction.
        
        Returns:
            CorrectionClaim if correction detected, None otherwise
        """
        # Step 1: Detect if this is a correction attempt
        is_correction, confidence, signals = self.detector.is_correction_attempt(
            feedback_text=feedback_text,
            original_query=original_query,
            original_response=original_response
        )
        
        if not is_correction or confidence < self.config.correction_confidence_min:
            return None
        
        # Step 2: Extract structured claim
        claim = self.extractor.extract_claim(
            feedback_text=feedback_text,
            original_response=original_response
        )
        
        if not claim or not claim.resolved_entity_id:
            return None
        
        # Step 3: Store feedback record
        feedback_id = await self.db.store_feedback(
            session_id=session_id,
            response_id=response_id,
            feedback_text=feedback_text,
            issue_types=issue_types or ["F02-Accuracy"],
            source=source,
            detection_confidence=confidence,
            auto_detected=False
        )
        
        # Step 4: Build unified evaluation record
        eval_record = {
            "feedback_id": feedback_id,
            "response_id": response_id,
            "query_text": original_query,
            "response_text": original_response,
            "claim": claim.to_dict(),
            "detection_confidence": confidence,
            "signals": signals
        }
        
        await self.db.store_evaluation_record(eval_record)
        
        return claim
    
    async def close(self):
        """Cleanup resources."""
        await self.db.close()
        if self.evidence:
            await self.evidence.close()
```

**Step 5.6: Write Tests**

`tests/test_feedback_loop.py`:
```python
"""
Tests for feedback loop integration.
"""
import pytest
import tempfile
from pathlib import Path
from amc_feedback import FeedbackLoop, FeedbackConfig, SQLiteAdapter

@pytest.fixture
def config():
    return FeedbackConfig(
        domain_name="amc",
        entity_master_path=None,  # Mock data in test
        fuzzy_match_threshold=0.70
    )

@pytest.fixture
def db_adapter():
    """Create temp SQLite database for testing."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    adapter = SQLiteAdapter(temp_db.name)
    yield adapter
    Path(temp_db.name).unlink()

@pytest.mark.asyncio
async def test_process_correction_feedback(config, db_adapter):
    """Test complete feedback processing flow."""
    loop = FeedbackLoop(config=config, db_adapter=db_adapter)
    
    claim = await loop.process_feedback(
        session_id="test_session",
        response_id="test_response",
        feedback_text="TER is 0.82%, not 0.79%",
        original_query="What is TER of Axis Bluechip?",
        original_response="The TER is 0.79%"
    )
    
    assert claim is not None, "Should detect correction"
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    assert claim.rejected_value == "0.79"
    
    await loop.close()

@pytest.mark.asyncio
async def test_non_correction_feedback(config, db_adapter):
    """Test that positive feedback doesn't create correction."""
    loop = FeedbackLoop(config=config, db_adapter=db_adapter)
    
    claim = await loop.process_feedback(
        session_id="test_session",
        response_id="test_response",
        feedback_text="Thank you, this is helpful!",
        original_query="What is TER?",
        original_response="TER is 0.79%"
    )
    
    assert claim is None, "Should not detect correction in positive feedback"
    
    await loop.close()
```

**Step 5.7: Create Usage Examples**

`examples/standalone_usage.py`:
```python
"""
Example: Using amc-feedback-loop standalone.
"""
import asyncio
from amc_feedback import FeedbackLoop, FeedbackConfig, SQLiteAdapter

async def main():
    # Configure for AMC domain
    config = FeedbackConfig(
        domain_name="amc",
        entity_master_path="./fund_master.json",
        fuzzy_match_threshold=0.75,
        enable_passive_capture=True
    )
    
    # Initialize with SQLite adapter
    db_adapter = SQLiteAdapter("./feedback.db")
    
    # Create feedback loop
    loop = FeedbackLoop(config=config, db_adapter=db_adapter)
    
    # Process user feedback
    claim = await loop.process_feedback(
        session_id="sess_abc123",
        response_id="resp_xyz789",
        feedback_text="The TER is actually 0.82%, not 0.79%",
        original_query="What is the TER of Axis Bluechip Fund?",
        original_response="The Total Expense Ratio (TER) of Axis Bluechip Fund is 0.79%."
    )
    
    if claim:
        print("✅ Correction detected!")
        print(f"   Entity: {claim.resolved_entity_name} ({claim.resolved_entity_id})")
        print(f"   Attribute: {claim.attribute}")
        print(f"   Asserted: {claim.asserted_value}")
        print(f"   Rejected: {claim.rejected_value}")
        print(f"   Confidence: {claim.confidence:.2%}")
        
        # Now you can send this claim to a repair service
        # repair_service.create_patch(claim)
    else:
        print("ℹ️  No correction detected in feedback")
    
    await loop.close()

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 5.8: Build and Test Package**

```bash
cd packages/amc-feedback-loop

# Install in editable mode for development
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Build distribution
python -m build

# This creates:
# - dist/amc_feedback_loop-0.1.0-py3-none-any.whl
# - dist/amc-feedback-loop-0.1.0.tar.gz
```

**Deliverables:**
- ✅ `amc-feedback-loop` package structure created
- ✅ Config-driven design implemented
- ✅ Adapter interfaces for database/evidence
- ✅ SQLite and PostgreSQL adapters
- ✅ Unit tests passing (80%+ coverage)
- ✅ Usage examples documented
- ✅ Package builds successfully

**Acceptance Criteria:**
- ✅ Can `pip install amc-feedback-loop`
- ✅ Standalone usage works without AMC platform
- ✅ Config allows domain customization
- ✅ Adapters are swappable (SQLite ↔ PostgreSQL)
- ✅ Tests pass independently

**Demo:**
Show standalone usage example running outside the AMC platform, successfully processing feedback.

---

Due to length constraints, I'll summarize the remaining tasks:

#### **Task 6: Extract amc-repair-engine Package** (5-6 days)
- Similar structure to feedback-loop
- Extract patch layer, evaluation router, governance batch
- Graph DB adapter interface (Neo4j, ArangoDB)
- Redis/Memory cache adapters

#### **Task 7: Refactor Platform to Use Packages** (3-4 days)
- Update backend imports to use packages
- Configure adapters
- Verify functionality maintained
- Update tests

#### **Task 8: Docker Composition** (2-3 days)
- Create Dockerfiles for each service
- docker-compose.yml with networking
- Health checks and dependencies
- Test multi-container deployment

#### **Task 9: Inter-Service Communication** (3-4 days)
- REST API endpoints
- JWT authentication
- Circuit breakers
- OpenAPI specs

#### **Task 10: Integration Testing** (3-4 days)
- End-to-end user journeys
- Load testing (50-500 users)
- Migration guide
- Deployment runbook

---

## **SUMMARY & NEXT STEPS**

### **What We're Building**

1. **ONNX GLiNER** - 60-200x NER speedup (9-30s → 30-150ms)
2. **Three Independent Services** - AMC Platform, Feedback Loop, Repair Engine
3. **Plug-and-Play Architecture** - Reusable across projects

### **Timeline: 6-8 Weeks**

- **Weeks 1-2:** ONNX optimization + integration validation
- **Weeks 3-4:** Microservices architecture design
- **Weeks 4-6:** Package extraction (feedback-loop + repair-engine)
- **Weeks 6-8:** Integration, testing, documentation

### **Success Metrics**

- ✅ NER latency < 150ms (was 9,000-30,000ms)
- ✅ Two pip-installable packages functional
- ✅ Services deployable independently
- ✅ End-to-end tests passing
- ✅ Load test: 50-500 concurrent users

Does this plan look good, or would you like me to adjust anything before we begin execution?

Perfect! Let me create the detailed implementation plans for the remaining tasks.

---

## **TASK 6: EXTRACT AMC-REPAIR-ENGINE PACKAGE**

**Duration:** 5-6 days  
**Priority:** High  
**Dependencies:** Task 5 (feedback-loop package) completed

### **Step 6.1: Create Package Structure**

```bash
mkdir -p packages/amc-repair-engine
cd packages/amc-repair-engine
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "amc-repair-engine"
version = "0.1.0"
description = "Self-correcting repair engine with tiered evaluation and governance for RAG systems"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Proprietary"}
authors = [
    {name = "NuSummit Technologies", email = "dev@nusummit.com"}
]
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "redis>=5.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "apscheduler>=3.10",
    "tenacity>=8.3",
    "sentence-transformers>=3.0",  # For NLI evaluator
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "black>=24.0",
    "ruff>=0.3",
]
neo4j = [
    "neo4j>=5.24",
]
arangodb = [
    "python-arango>=7.8",
]

[tool.hatch.build.targets.wheel]
packages = ["src/amc_repair"]
```

**Package Structure:**
```
packages/amc-repair-engine/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── amc_repair/
│       ├── __init__.py
│       ├── config.py
│       ├── patch_layer.py          # Correction patch layer
│       ├── evaluator.py            # Tiered evaluation router
│       ├── governance.py           # Governance batch processor
│       ├── rules.py                # Deterministic rules engine
│       ├── nli_evaluator.py        # Tier 2 NLI evaluation
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py             # Abstract interfaces
│       │   ├── cache.py            # Redis/Memory cache
│       │   ├── graph.py            # Graph DB adapter
│       │   └── database.py         # SQL database adapter
│       └── schemas.py              # Pydantic models
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_patch_layer.py
│   ├── test_evaluator.py
│   ├── test_governance.py
│   └── test_integration.py
└── examples/
    ├── standalone_usage.py
    └── custom_adapter.py
```

---

### **Step 6.2: Implement Configuration Schema**

`src/amc_repair/config.py`:

```python
"""
Configuration schema for repair engine.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal

class RepairConfig(BaseModel):
    """Configuration for repair engine behavior."""
    
    # ── Patch Layer Configuration ─────────────────────────────────
    patch_ttl_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Time-to-live for unapproved patches (days)"
    )
    patch_confidence_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept a patch"
    )
    use_redis: bool = Field(
        default=False,
        description="Use Redis for distributed caching (fallback: in-memory)"
    )
    redis_host: str = Field(default="localhost", description="Redis hostname")
    redis_port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_db: int = Field(default=0, ge=0, le=15, description="Redis database number")
    redis_key_prefix: str = Field(
        default="amc_repair:",
        description="Prefix for Redis keys (namespace isolation)"
    )
    
    # ── Evaluation Tier Configuration ─────────────────────────────
    enable_tier1_rules: bool = Field(
        default=True,
        description="Enable Tier 1A deterministic rules evaluation"
    )
    enable_tier2_nli: bool = Field(
        default=False,
        description="Enable Tier 2 NLI semantic entailment evaluation"
    )
    enable_tier3_llm: bool = Field(
        default=False,
        description="Enable Tier 3 LLM judge evaluation"
    )
    
    tier1_stop_confidence: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="STOP-1 gate confidence threshold"
    )
    tier2_nli_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="STOP-2 gate NLI confidence threshold"
    )
    tier3_llm_severity_threshold: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="HIGH",
        description="Minimum severity for STOP-3 gate"
    )
    
    nli_model: str = Field(
        default="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        description="HuggingFace model for NLI evaluation"
    )
    
    # ── Governance Batch Configuration ────────────────────────────
    governance_schedule: str = Field(
        default="0 9 * * FRI",
        description="Cron schedule for governance batch (default: Friday 9 AM UTC)"
    )
    auto_approve_confidence: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Auto-approve patches above this confidence"
    )
    require_human_review_below: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Require human review below this confidence"
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum patches to process per governance batch"
    )
    
    # ── Graph Adapter Configuration ───────────────────────────────
    graph_adapter: Literal["neo4j", "arangodb", "custom"] = Field(
        default="neo4j",
        description="Graph database adapter type"
    )
    graph_uri: Optional[str] = Field(
        default=None,
        description="Graph database connection URI"
    )
    graph_user: Optional[str] = Field(default=None, description="Graph DB username")
    graph_password: Optional[str] = Field(default=None, description="Graph DB password")
    graph_database: str = Field(
        default="neo4j",
        description="Graph database name"
    )
    
    # ── Database Configuration ────────────────────────────────────
    database_adapter: Literal["sqlite", "postgresql", "custom"] = Field(
        default="sqlite",
        description="SQL database adapter type"
    )
    database_url: Optional[str] = Field(
        default=None,
        description="SQL database connection URL"
    )
    
    # ── Rules Engine Configuration ────────────────────────────────
    rules_config: Dict[str, bool] = Field(
        default={
            "guaranteed_return": True,
            "numeric_plausibility": True,
            "date_consistency": True,
            "schema_compliance": True,
            "source_attribution": True,
            "metric_unit_match": True,
            "entity_existence": True,
            "temporal_validity": True,
            "cross_reference": True,
        },
        description="Enable/disable specific rule categories"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "patch_ttl_days": 7,
                "use_redis": True,
                "enable_tier1_rules": True,
                "enable_tier2_nli": False,
                "governance_schedule": "0 9 * * FRI",
                "auto_approve_confidence": 0.95
            }
        }
```

---

### **Step 6.3: Create Adapter Interfaces**

`src/amc_repair/adapters/base.py`:

```python
"""
Base adapter interfaces for dependency injection.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime

class CacheAdapter(ABC):
    """Interface for cache operations (Redis or in-memory)."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value by key."""
        pass
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Store value with optional TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value by key."""
        pass
    
    @abstractmethod
    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Get all keys matching pattern."""
        pass
    
    @abstractmethod
    async def close(self):
        """Cleanup connections."""
        pass


class GraphAdapter(ABC):
    """Interface for graph database operations."""
    
    @abstractmethod
    async def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entity node by ID."""
        pass
    
    @abstractmethod
    async def update_entity_attribute(
        self,
        entity_id: str,
        attribute: str,
        value: Any,
        provenance: Dict[str, Any]
    ) -> bool:
        """Update entity attribute with provenance tracking."""
        pass
    
    @abstractmethod
    async def create_audit_log(
        self,
        operation: str,
        entity_id: str,
        changes: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> str:
        """Create audit log entry and return log ID."""
        pass
    
    @abstractmethod
    async def execute_safe_cypher(
        self,
        query: str,
        parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute parameterized Cypher query safely."""
        pass
    
    @abstractmethod
    async def close(self):
        """Cleanup connections."""
        pass


class DatabaseAdapter(ABC):
    """Interface for SQL database operations."""
    
    @abstractmethod
    async def store_evaluation_result(
        self,
        response_id: str,
        verdict: str,
        tier: str,
        confidence: float,
        details: Dict[str, Any]
    ) -> str:
        """Store evaluation result and return record ID."""
        pass
    
    @abstractmethod
    async def get_evaluation_history(
        self,
        response_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve evaluation history for response."""
        pass
    
    @abstractmethod
    async def close(self):
        """Cleanup connections."""
        pass
```

---

### **Step 6.4: Implement Cache Adapters**

`src/amc_repair/adapters/cache.py`:

```python
"""
Cache adapter implementations (Redis and in-memory fallback).
"""
import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from .base import CacheAdapter

class RedisAdapter(CacheAdapter):
    """Redis implementation of cache adapter."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        key_prefix: str = "amc_repair:"
    ):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.key_prefix = key_prefix
        self._client = None
    
    async def _get_client(self):
        """Lazy Redis client initialization."""
        if self._client is None:
            import redis.asyncio as redis
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True
            )
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Add namespace prefix to key."""
        return f"{self.key_prefix}{key}"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value from Redis."""
        client = await self._get_client()
        value = await client.get(self._make_key(key))
        
        if value:
            return json.loads(value)
        return None
    
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Store value in Redis with optional TTL."""
        client = await self._get_client()
        serialized = json.dumps(value)
        
        if ttl_seconds:
            await client.setex(self._make_key(key), ttl_seconds, serialized)
        else:
            await client.set(self._make_key(key), serialized)
        
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete value from Redis."""
        client = await self._get_client()
        result = await client.delete(self._make_key(key))
        return result > 0
    
    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Get all keys matching pattern."""
        client = await self._get_client()
        full_pattern = self._make_key(pattern)
        keys = await client.keys(full_pattern)
        
        # Remove prefix from returned keys
        prefix_len = len(self.key_prefix)
        return [k[prefix_len:] for k in keys]
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()


class MemoryAdapter(CacheAdapter):
    """In-memory fallback implementation (thread-safe)."""
    
    def __init__(self):
        self._store: Dict[str, tuple[Dict[str, Any], Optional[float]]] = {}
        self._lock = asyncio.Lock()
    
    async def _cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired = [
            k for k, (_, exp) in self._store.items()
            if exp and exp < now
        ]
        for k in expired:
            del self._store[k]
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value from memory."""
        async with self._lock:
            await self._cleanup_expired()
            
            if key in self._store:
                value, expiry = self._store[key]
                if expiry is None or expiry > time.time():
                    return value
                else:
                    del self._store[key]
            
            return None
    
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Store value in memory with optional TTL."""
        async with self._lock:
            expiry = None
            if ttl_seconds:
                expiry = time.time() + ttl_seconds
            
            self._store[key] = (value, expiry)
            return True
    
    async def delete(self, key: str) -> bool:
        """Delete value from memory."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    async def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Get all keys matching pattern (simple prefix match)."""
        async with self._lock:
            await self._cleanup_expired()
            
            # Simple prefix matching (not full glob pattern)
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                return [k for k in self._store.keys() if k.startswith(prefix)]
            else:
                return [k for k in self._store.keys() if k == pattern]
    
    async def close(self):
        """No cleanup needed for in-memory."""
        pass
```

---

### **Step 6.5: Implement Graph Adapters**

`src/amc_repair/adapters/graph.py`:

```python
"""
Graph database adapter implementations.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from .base import GraphAdapter

class Neo4jAdapter(GraphAdapter):
    """Neo4j implementation of graph adapter."""
    
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j"
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver = None
    
    def _get_driver(self):
        """Lazy driver initialization."""
        if self._driver is None:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        return self._driver
    
    async def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entity node by ID."""
        driver = self._get_driver()
        
        async with driver.session(database=self.database) as session:
            result = await session.run("""
                MATCH (e:Entity {id: $entity_id})
                RETURN e
            """, entity_id=entity_id)
            
            record = await result.single()
            if record:
                node = record["e"]
                return dict(node)
            return None
    
    async def update_entity_attribute(
        self,
        entity_id: str,
        attribute: str,
        value: Any,
        provenance: Dict[str, Any]
    ) -> bool:
        """Update entity attribute with provenance tracking."""
        driver = self._get_driver()
        
        async with driver.session(database=self.database) as session:
            result = await session.run("""
                MATCH (e:Entity {id: $entity_id})
                SET e[$attribute] = $value,
                    e[$attribute + '_updated_at'] = datetime(),
                    e[$attribute + '_provenance'] = $provenance
                RETURN e
            """, 
            entity_id=entity_id,
            attribute=attribute,
            value=value,
            provenance=provenance
            )
            
            record = await result.single()
            return record is not None
    
    async def create_audit_log(
        self,
        operation: str,
        entity_id: str,
        changes: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> str:
        """Create audit log entry."""
        driver = self._get_driver()
        
        async with driver.session(database=self.database) as session:
            result = await session.run("""
                CREATE (log:AuditLog {
                    id: randomUUID(),
                    operation: $operation,
                    entity_id: $entity_id,
                    changes: $changes,
                    metadata: $metadata,
                    timestamp: datetime()
                })
                RETURN log.id as log_id
            """,
            operation=operation,
            entity_id=entity_id,
            changes=changes,
            metadata=metadata
            )
            
            record = await result.single()
            return record["log_id"] if record else ""
    
    async def execute_safe_cypher(
        self,
        query: str,
        parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute parameterized Cypher query safely."""
        driver = self._get_driver()
        
        # Validate query is read-only or parameterized write
        if not self._is_safe_query(query):
            raise ValueError("Unsafe Cypher query detected")
        
        async with driver.session(database=self.database) as session:
            result = await session.run(query, **parameters)
            records = await result.data()
            return records
    
    def _is_safe_query(self, query: str) -> bool:
        """Basic safety check for Cypher queries."""
        # Whitelist safe operations
        safe_keywords = ["MATCH", "RETURN", "WHERE", "WITH", "SET", "CREATE"]
        
        # Blacklist dangerous operations
        dangerous_keywords = ["DELETE", "DETACH", "REMOVE", "DROP"]
        
        query_upper = query.upper()
        
        # Check for dangerous keywords
        for kw in dangerous_keywords:
            if kw in query_upper:
                return False
        
        # Ensure parameterized (contains $)
        if "$" not in query:
            return False
        
        return True
    
    async def close(self):
        """Close Neo4j driver."""
        if self._driver:
            await self._driver.close()


class ArangoDBAdapter(GraphAdapter):
    """ArangoDB implementation (placeholder for future)."""
    
    def __init__(self, hosts: str, username: str, password: str, database: str):
        self.hosts = hosts
        self.username = username
        self.password = password
        self.database = database
        self._client = None
    
    async def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("ArangoDB adapter not yet implemented")
    
    async def update_entity_attribute(
        self,
        entity_id: str,
        attribute: str,
        value: Any,
        provenance: Dict[str, Any]
    ) -> bool:
        raise NotImplementedError("ArangoDB adapter not yet implemented")
    
    async def create_audit_log(
        self,
        operation: str,
        entity_id: str,
        changes: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> str:
        raise NotImplementedError("ArangoDB adapter not yet implemented")
    
    async def execute_safe_cypher(
        self,
        query: str,
        parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError("ArangoDB adapter uses AQL, not Cypher")
    
    async def close(self):
        pass
```

---

### **Step 6.6: Implement Patch Layer**

`src/amc_repair/patch_layer.py`:

```python
"""
Correction patch layer - stores and applies corrections before Neo4j promotion.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .adapters.base import CacheAdapter
from .config import RepairConfig

class CorrectionPatch:
    """Represents a single correction patch."""
    
    def __init__(
        self,
        patch_id: str,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False,
        created_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None
    ):
        self.patch_id = patch_id
        self.entity_id = entity_id
        self.attribute = attribute
        self.canonical_value = canonical_value
        self.corrected_value = corrected_value
        self.confidence = confidence
        self.provenance = provenance
        self.approved = approved
        self.created_at = created_at or datetime.utcnow()
        self.expires_at = expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "patch_id": self.patch_id,
            "entity_id": self.entity_id,
            "attribute": self.attribute,
            "canonical_value": self.canonical_value,
            "corrected_value": self.corrected_value,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "approved": self.approved,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrectionPatch":
        """Deserialize from dictionary."""
        return cls(
            patch_id=data["patch_id"],
            entity_id=data["entity_id"],
            attribute=data["attribute"],
            canonical_value=data["canonical_value"],
            corrected_value=data["corrected_value"],
            confidence=data["confidence"],
            provenance=data["provenance"],
            approved=data.get("approved", False),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        )


class PatchLayer:
    """
    Correction patch layer - shadow graph with TTL-based trials.
    
    Features:
    - Store corrections temporarily before Neo4j promotion
    - Apply patches to retrieval context (< 50ms overhead)
    - TTL enforcement (7 days default for unapproved)
    - Redis-backed with in-memory fallback
    """
    
    def __init__(self, config: RepairConfig, cache_adapter: CacheAdapter):
        self.config = config
        self.cache = cache_adapter
        self._lock = asyncio.Lock()
    
    async def add_patch(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """
        Add correction patch to layer.
        
        Returns:
            patch_id: Unique identifier for the patch
        """
        patch_id = str(uuid4())
        
        # Calculate expiry
        expires_at = None
        if not approved:
            expires_at = datetime.utcnow() + timedelta(days=self.config.patch_ttl_days)
        
        patch = CorrectionPatch(
            patch_id=patch_id,
            entity_id=entity_id,
            attribute=attribute,
            canonical_value=canonical_value,
            corrected_value=corrected_value,
            confidence=confidence,
            provenance=provenance,
            approved=approved,
            expires_at=expires_at
        )
        
        # Store in cache
        key = f"patch:{patch_id}"
        ttl = int(self.config.patch_ttl_days * 24 * 3600) if not approved else None
        
        await self.cache.set(key, patch.to_dict(), ttl_seconds=ttl)
        
        # Index by entity for fast lookup
        entity_key = f"entity_patches:{entity_id}"
        entity_patches = await self.cache.get(entity_key) or {"patch_ids": []}
        entity_patches["patch_ids"].append(patch_id)
        await self.cache.set(entity_key, entity_patches, ttl_seconds=ttl)
        
        return patch_id
    
    async def get_patch(self, patch_id: str) -> Optional[CorrectionPatch]:
        """Retrieve patch by ID."""
        key = f"patch:{patch_id}"
        data = await self.cache.get(key)
        
        if data:
            return CorrectionPatch.from_dict(data)
        return None
    
    async def get_patches_for_entity(self, entity_id: str) -> List[CorrectionPatch]:
        """Retrieve all patches for an entity."""
        entity_key = f"entity_patches:{entity_id}"
        entity_data = await self.cache.get(entity_key)
        
        if not entity_data or "patch_ids" not in entity_data:
            return []
        
        patches = []
        for patch_id in entity_data["patch_ids"]:
            patch = await self.get_patch(patch_id)
            if patch:
                patches.append(patch)
        
        return patches
    
    async def get_all_pending(self) -> List[CorrectionPatch]:
        """Retrieve all pending (unapproved) patches."""
        # Get all patch keys
        patch_keys = await self.cache.get_keys_by_pattern("patch:*")
        
        patches = []
        for key in patch_keys:
            data = await self.cache.get(key)
            if data and not data.get("approved", False):
                patches.append(CorrectionPatch.from_dict(data))
        
        return patches
    
    async def approve_patch(self, patch_id: str) -> bool:
        """Approve patch (removes TTL, marks for governance)."""
        patch = await self.get_patch(patch_id)
        if not patch:
            return False
        
        patch.approved = True
        patch.expires_at = None
        
        # Update in cache without TTL
        key = f"patch:{patch_id}"
        await self.cache.set(key, patch.to_dict(), ttl_seconds=None)
        
        return True
    
    async def reject_patch(self, patch_id: str) -> bool:
        """Reject patch (deletes immediately)."""
        key = f"patch:{patch_id}"
        return await self.cache.delete(key)
    
    async def apply_patches_to_context(
        self,
        entity_ids: List[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply correction patches to retrieval context.
        
        This is called during query orchestration to inject corrections
        before LLM synthesis.
        
        Args:
            entity_ids: List of entity IDs mentioned in context
            context: Original retrieval context dict
        
        Returns:
            Modified context with patches applied
        """
        if not entity_ids:
            return context
        
        # Collect all patches for these entities
        all_patches = []
        for entity_id in entity_ids:
            patches = await self.get_patches_for_entity(entity_id)
            all_patches.extend(patches)
        
        if not all_patches:
            return context
        
        # Apply patches to context
        modified_context = context.copy()
        
        # Add correction notices
        if "corrections_applied" not in modified_context:
            modified_context["corrections_applied"] = []
        
        for patch in all_patches:
            if patch.confidence >= self.config.patch_confidence_threshold:
                modified_context["corrections_applied"].append({
                    "entity_id": patch.entity_id,
                    "attribute": patch.attribute,
                    "original": patch.canonical_value,
                    "corrected": patch.corrected_value,
                    "confidence": patch.confidence,
                    "source": patch.provenance.get("source", "unknown")
                })
        
        return modified_context
    
    async def close(self):
        """Cleanup resources."""
        await self.cache.close()
```

---

### **Step 6.7: Implement Main Package Interface**

`src/amc_repair/__init__.py`:

```python
"""
AMC Repair Engine - Self-correcting repair engine for RAG systems.
"""
from .config import RepairConfig
from .patch_layer import PatchLayer, CorrectionPatch
from .evaluator import EvaluationRouter, EvaluationResult
from .governance import GovernanceBatch, GovernanceReport
from .rules import RulesEngine, RuleResult
from .adapters.base import CacheAdapter, GraphAdapter, DatabaseAdapter
from .adapters.cache import RedisAdapter, MemoryAdapter
from .adapters.graph import Neo4jAdapter

__version__ = "0.1.0"
__all__ = [
    "RepairConfig",
    "RepairEngine",
    "CacheAdapter",
    "GraphAdapter",
    "DatabaseAdapter",
    "RedisAdapter",
    "MemoryAdapter",
    "Neo4jAdapter",
]

class RepairEngine:
    """
    Main interface for repair engine operations.
    
    Example:
        >>> config = RepairConfig(use_redis=False, patch_ttl_days=7)
        >>> cache_adapter = MemoryAdapter()
        >>> graph_adapter = Neo4jAdapter("bolt://localhost:7687", "neo4j", "password")
        >>> engine = RepairEngine(config=config, cache_adapter=cache_adapter, graph_adapter=graph_adapter)
        >>> 
        >>> # Add correction
        >>> patch_id = await engine.add_correction(
        ...     entity_id="INF846K01DP5",
        ...     attribute="TER",
        ...     canonical_value="0.79",
        ...     corrected_value="0.82",
        ...     confidence=0.88,
        ...     provenance={"source": "user_feedback"}
        ... )
        >>> 
        >>> # Apply patches to context
        >>> corrected_context = await engine.apply_patches(
        ...     entities=["INF846K01DP5"],
        ...     retrieval_context=original_context
        ... )
        >>> 
        >>> # Run governance batch
        >>> report = await engine.run_governance_batch()
    """
    
    def __init__(
        self,
        config: RepairConfig,
        cache_adapter: CacheAdapter,
        graph_adapter: GraphAdapter,
        db_adapter: Optional[DatabaseAdapter] = None
    ):
        self.config = config
        self.patch_layer = PatchLayer(config, cache_adapter)
        self.graph = graph_adapter
        self.db = db_adapter
        
        # Initialize components
        self.rules_engine = RulesEngine(config)
        self.evaluator = EvaluationRouter(config, self.rules_engine)
        self.governance = GovernanceBatch(
            config,
            self.patch_layer,
            self.graph,
            self.evaluator
        )
    
    # ── Patch Layer Operations ────────────────────────────────────
    
    async def add_correction(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """Add correction patch to layer."""
        return await self.patch_layer.add_patch(
            entity_id=entity_id,
            attribute=attribute,
            canonical_value=canonical_value,
            corrected_value=corrected_value,
            confidence=confidence,
            provenance=provenance,
            approved=approved
        )
    
    async def get_pending_corrections(self) -> List[CorrectionPatch]:
        """Get all pending (unapproved) patches."""
        return await self.patch_layer.get_all_pending()
    
    async def approve_correction(self, patch_id: str) -> bool:
        """Approve a correction patch."""
        return await self.patch_layer.approve_patch(patch_id)
    
    async def reject_correction(self, patch_id: str) -> bool:
        """Reject a correction patch."""
        return await self.patch_layer.reject_patch(patch_id)
    
    async def apply_patches(
        self,
        entities: List[str],
        retrieval_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply correction patches to retrieval context."""
        return await self.patch_layer.apply_patches_to_context(
            entity_ids=entities,
            context=retrieval_context
        )
    
    # ── Evaluation Operations ─────────────────────────────────────
    
    async def evaluate_answer(
        self,
        response_id: str,
        response_text: str,
        retrieved_context: str,
        query: str,
        intent: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """Evaluate answer quality using tiered evaluation."""
        evidence_pack = {
            "response_id": response_id,
            "response_text": response_text,
            "retrieved_context": retrieved_context,
            "query": query,
            "intent": intent
        }
        
        return await self.evaluator.evaluate(response_id, evidence_pack)
    
    # ── Governance Operations ─────────────────────────────────────
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None
    ) -> GovernanceReport:
        """
        Run governance batch to promote approved corrections to Neo4j.
        
        Args:
            auto_approve_threshold: Override config threshold for auto-approval
        
        Returns:
            GovernanceReport with summary of actions taken
        """
        return await self.governance.execute(
            auto_approve_threshold=auto_approve_threshold
        )
    
    async def close(self):
        """Cleanup all resources."""
        await self.patch_layer.close()
        await self.graph.close()
        if self.db:
            await self.db.close()
```

---

### **Step 6.8: Write Tests**

`tests/test_patch_layer.py`:

```python
"""
Tests for correction patch layer.
"""
import pytest
from datetime import datetime, timedelta
from amc_repair import RepairConfig, PatchLayer
from amc_repair.adapters.cache import MemoryAdapter

@pytest.fixture
def config():
    return RepairConfig(patch_ttl_days=7, use_redis=False)

@pytest.fixture
def cache_adapter():
    return MemoryAdapter()

@pytest.fixture
def patch_layer(config, cache_adapter):
    return PatchLayer(config, cache_adapter)

@pytest.mark.asyncio
async def test_add_and_retrieve_patch(patch_layer):
    """Test adding and retrieving a patch."""
    patch_id = await patch_layer.add_patch(
        entity_id="test_entity",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "test"},
        approved=False
    )
    
    assert patch_id is not None
    
    # Retrieve patch
    patch = await patch_layer.get_patch(patch_id)
    assert patch is not None
    assert patch.entity_id == "test_entity"
    assert patch.attribute == "TER"
    assert patch.corrected_value == "0.82"
    assert patch.confidence == 0.88

@pytest.mark.asyncio
async def test_get_patches_for_entity(patch_layer):
    """Test retrieving all patches for an entity."""
    entity_id = "test_entity"
    
    # Add multiple patches
    await patch_layer.add_patch(
        entity_id=entity_id,
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "test"}
    )
    
    await patch_layer.add_patch(
        entity_id=entity_id,
        attribute="NAV",
        canonical_value="100.5",
        corrected_value="101.2",
        confidence=0.92,
        provenance={"source": "test"}
    )
    
    # Retrieve patches
    patches = await patch_layer.get_patches_for_entity(entity_id)
    assert len(patches) == 2
    
    attributes = {p.attribute for p in patches}
    assert "TER" in attributes
    assert "NAV" in attributes

@pytest.mark.asyncio
async def test_approve_patch(patch_layer):
    """Test approving a patch removes TTL."""
    patch_id = await patch_layer.add_patch(
        entity_id="test_entity",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "test"},
        approved=False
    )
    
    # Initially not approved
    patch = await patch_layer.get_patch(patch_id)
    assert not patch.approved
    assert patch.expires_at is not None
    
    # Approve
    await patch_layer.approve_patch(patch_id)
    
    # Now approved
    patch = await patch_layer.get_patch(patch_id)
    assert patch.approved
    assert patch.expires_at is None

@pytest.mark.asyncio
async def test_apply_patches_to_context(patch_layer):
    """Test applying patches to retrieval context."""
    entity_id = "test_entity"
    
    # Add correction
    await patch_layer.add_patch(
        entity_id=entity_id,
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "user_feedback"}
    )
    
    # Apply to context
    original_context = {"entities": [entity_id], "text": "TER is 0.79%"}
    modified_context = await patch_layer.apply_patches_to_context(
        entity_ids=[entity_id],
        context=original_context
    )
    
    # Verify corrections applied
    assert "corrections_applied" in modified_context
    assert len(modified_context["corrections_applied"]) == 1
    
    correction = modified_context["corrections_applied"][0]
    assert correction["attribute"] == "TER"
    assert correction["corrected"] == "0.82"
    assert correction["confidence"] == 0.88

@pytest.mark.asyncio
async def test_reject_patch(patch_layer):
    """Test rejecting a patch deletes it."""
    patch_id = await patch_layer.add_patch(
        entity_id="test_entity",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "test"}
    )
    
    # Verify exists
    patch = await patch_layer.get_patch(patch_id)
    assert patch is not None
    
    # Reject
    await patch_layer.reject_patch(patch_id)
    
    # Verify deleted
    patch = await patch_layer.get_patch(patch_id)
    assert patch is None
```

---

### **Step 6.9: Create Usage Examples**

`examples/standalone_usage.py`:

```python
"""
Example: Using amc-repair-engine standalone.
"""
import asyncio
from amc_repair import RepairEngine, RepairConfig
from amc_repair.adapters.cache import MemoryAdapter
from amc_repair.adapters.graph import Neo4jAdapter

async def main():
    # Configure repair engine
    config = RepairConfig(
        patch_ttl_days=7,
        use_redis=False,  # Use in-memory for local dev
        enable_tier1_rules=True,
        governance_schedule="0 9 * * FRI",
        auto_approve_confidence=0.95
    )
    
    # Initialize adapters
    cache_adapter = MemoryAdapter()
    graph_adapter = Neo4jAdapter(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password"
    )
    
    # Create repair engine
    engine = RepairEngine(
        config=config,
        cache_adapter=cache_adapter,
        graph_adapter=graph_adapter
    )
    
    # ── Example 1: Add Correction ────────────────────────────────
    print("=" * 60)
    print("Example 1: Add correction patch")
    print("=" * 60)
    
    patch_id = await engine.add_correction(
        entity_id="INF846K01DP5",  # Axis Bluechip Fund
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={
            "source": "user_feedback",
            "feedback_id": "fb_12345",
            "timestamp": "2025-01-15T10:30:00Z"
        },
        approved=False
    )
    
    print(f"✅ Correction patch created: {patch_id}")
    print(f"   Entity: INF846K01DP5")
    print(f"   Attribute: TER")
    print(f"   0.79% → 0.82%")
    print()
    
    # ── Example 2: Apply Patches to Context ──────────────────────
    print("=" * 60)
    print("Example 2: Apply patches to retrieval context")
    print("=" * 60)
    
    original_context = {
        "query": "What is TER of Axis Bluechip?",
        "entities": ["INF846K01DP5"],
        "chunks": [
            {
                "text": "Axis Bluechip Fund has TER of 0.79% as of December 2024",
                "source": "scheme_document_2024"
            }
        ]
    }
    
    corrected_context = await engine.apply_patches(
        entities=["INF846K01DP5"],
        retrieval_context=original_context
    )
    
    if "corrections_applied" in corrected_context:
        print("✅ Patches applied to context:")
        for correction in corrected_context["corrections_applied"]:
            print(f"   • {correction['attribute']}: {correction['original']} → {correction['corrected']}")
            print(f"     Confidence: {correction['confidence']:.0%}")
            print(f"     Source: {correction['source']}")
    print()
    
    # ── Example 3: Get Pending Corrections ───────────────────────
    print("=" * 60)
    print("Example 3: Get pending corrections for governance")
    print("=" * 60)
    
    pending = await engine.get_pending_corrections()
    
    print(f"✅ Found {len(pending)} pending corrections:")
    for patch in pending:
        print(f"   • Patch {patch.patch_id[:8]}...")
        print(f"     Entity: {patch.entity_id}")
        print(f"     {patch.attribute}: {patch.canonical_value} → {patch.corrected_value}")
        print(f"     Confidence: {patch.confidence:.0%}")
        print(f"     Expires: {patch.expires_at}")
    print()
    
    # ── Example 4: Run Governance Batch ──────────────────────────
    print("=" * 60)
    print("Example 4: Run governance batch")
    print("=" * 60)
    
    report = await engine.run_governance_batch()
    
    print("✅ Governance batch complete:")
    print(f"   Total Evaluated: {report.total_evaluated}")
    print(f"   Approved: {report.approved}")
    print(f"   Rejected: {report.rejected}")
    print(f"   Needs Review: {report.needs_review}")
    print(f"   Deployed to Neo4j: {report.deployed}")
    print()
    
    # Cleanup
    await engine.close()
    print("✅ Repair engine closed")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### **Step 6.10: Build and Test Package**

```bash
cd packages/amc-repair-engine

# Install in editable mode
pip install -e ".[dev,neo4j]"

# Run tests
pytest tests/ -v --cov=amc_repair

# Build distribution
python -m build

# This creates:
# - dist/amc_repair_engine-0.1.0-py3-none-any.whl
# - dist/amc-repair-engine-0.1.0.tar.gz
```

---

### **Deliverables for Task 6**

- ✅ `amc-repair-engine` package structure created
- ✅ Config-driven design with RepairConfig
- ✅ Adapter interfaces (Cache, Graph, Database)
- ✅ Redis and Memory cache adapters
- ✅ Neo4j graph adapter (ArangoDB placeholder)
- ✅ Correction patch layer fully implemented
- ✅ Main RepairEngine interface
- ✅ Unit tests (>80% coverage)
- ✅ Standalone usage examples
- ✅ Package builds successfully

---

**Would you like me to continue with Task 7, 9, and 10 now?**

Perfect! Let me continue with the detailed implementation plans for Tasks 7, 9, and 10.

---

## **TASK 7: REFACTOR PLATFORM TO USE PACKAGES**

**Duration:** 3-4 days  
**Priority:** High  
**Dependencies:** Tasks 5 & 6 (both packages extracted)

### **Step 7.1: Install Packages in Backend**

Update `backend/requirements.txt`:

```txt
# ... existing dependencies ...

# ── Phase 2: Modular Packages ──────────────────────────────────
# Install from local packages during development
-e ../packages/amc-feedback-loop
-e ../packages/amc-repair-engine

# Or install from private PyPI/Git in production:
# amc-feedback-loop @ git+https://github.com/nusummit/amc-feedback-loop@v0.1.0
# amc-repair-engine @ git+https://github.com/nusummit/amc-repair-engine@v0.1.0
```

Install packages:
```bash
cd backend
pip install -r requirements.txt
```

---

### **Step 7.2: Create Adapter Configuration Module**

Create `backend/app/adapters_config.py`:

```python
"""
Adapter configuration and initialization for modular packages.
Wires amc-feedback-loop and amc-repair-engine with backend infrastructure.
"""
import logging
from typing import Optional

from amc_feedback import FeedbackConfig, DatabaseAdapter as FeedbackDBAdapter
from amc_feedback.adapters.database import SQLiteAdapter as FeedbackSQLiteAdapter, PostgreSQLAdapter as FeedbackPostgreSQLAdapter

from amc_repair import RepairConfig, CacheAdapter, GraphAdapter, DatabaseAdapter as RepairDBAdapter
from amc_repair.adapters.cache import RedisAdapter, MemoryAdapter
from amc_repair.adapters.graph import Neo4jAdapter

from app.config import get_settings
from app.engine import config as engine_config

logger = logging.getLogger("adapters")


# ── Feedback Loop Configuration ────────────────────────────────

def create_feedback_config() -> FeedbackConfig:
    """Create feedback loop configuration from backend settings."""
    settings = get_settings()
    
    return FeedbackConfig(
        domain_name="amc",
        entity_types=["fund", "scheme", "amc", "regulation", "company"],
        attribute_keywords={
            "TER": ["ter", "expense ratio", "total expense"],
            "NAV": ["nav", "net asset value", "price"],
            "AUM": ["aum", "assets under management", "corpus"],
            "RETURNS": ["returns", "performance", "cagr"],
            "EBITDA": ["ebitda", "earnings"],
            "REVENUE": ["revenue", "sales", "turnover"],
        },
        entity_master_path=str(settings.base_dir / "app" / "data" / "fund_master.json"),
        fuzzy_match_threshold=0.70,
        embedding_model="all-MiniLM-L6-v2",
        use_spacy=True,
        use_gliner=True,
        gliner_model_id=engine_config.GLINER_MODEL_ID,
        enable_onnx=engine_config.ENABLE_ONNX_GLINER,
        dissatisfaction_threshold=0.65,
        correction_confidence_min=0.60,
        enable_passive_capture=True,
        passive_timeout_seconds=180,
        database_adapter="sqlite" if "sqlite" in settings.database_url.lower() else "postgresql",
        evidence_adapter="local",
    )


def create_feedback_db_adapter() -> FeedbackDBAdapter:
    """Create feedback database adapter based on current backend database."""
    settings = get_settings()
    
    if "sqlite" in settings.database_url.lower():
        # Extract path from sqlite:///path/to/db.db
        db_path = settings.database_url.replace("sqlite:///", "")
        logger.info(f"Using SQLite adapter for feedback: {db_path}")
        return FeedbackSQLiteAdapter(db_path)
    else:
        logger.info(f"Using PostgreSQL adapter for feedback")
        return FeedbackPostgreSQLAdapter(settings.database_url)


# ── Repair Engine Configuration ────────────────────────────────

def create_repair_config() -> RepairConfig:
    """Create repair engine configuration from backend settings."""
    settings = get_settings()
    
    # Check if Redis is available
    use_redis = settings.redis_url is not None
    redis_host = "localhost"
    redis_port = 6379
    redis_password = None
    
    if use_redis and settings.redis_url:
        # Parse redis://host:port or redis://:password@host:port
        from urllib.parse import urlparse
        parsed = urlparse(settings.redis_url)
        redis_host = parsed.hostname or "localhost"
        redis_port = parsed.port or 6379
        redis_password = parsed.password
    
    return RepairConfig(
        # Patch Layer
        patch_ttl_days=7,
        patch_confidence_threshold=0.70,
        use_redis=use_redis,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_password=redis_password,
        redis_key_prefix="amc_repair:",
        
        # Evaluation Tiers
        enable_tier1_rules=True,
        enable_tier2_nli=getattr(settings, "enable_tier2_nli_evaluation", False),
        enable_tier3_llm=getattr(settings, "enable_tier3_llm_judge", False),
        tier1_stop_confidence=0.90,
        tier2_nli_threshold=0.85,
        tier3_llm_severity_threshold="HIGH",
        nli_model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        
        # Governance
        governance_schedule="0 9 * * FRI",
        auto_approve_confidence=0.95,
        require_human_review_below=0.70,
        batch_size=100,
        
        # Graph
        graph_adapter="neo4j",
        graph_uri=engine_config.NEO4J_URI,
        graph_user=engine_config.NEO4J_USER,
        graph_password=engine_config.NEO4J_PASSWORD,
        graph_database=engine_config.NEO4J_DATABASE,
        
        # Database
        database_adapter="sqlite" if "sqlite" in settings.database_url.lower() else "postgresql",
        database_url=settings.database_url,
        
        # Rules
        rules_config={
            "guaranteed_return": True,
            "numeric_plausibility": True,
            "date_consistency": True,
            "schema_compliance": True,
            "source_attribution": True,
            "metric_unit_match": True,
            "entity_existence": True,
            "temporal_validity": True,
            "cross_reference": True,
        }
    )


def create_repair_cache_adapter() -> CacheAdapter:
    """Create cache adapter for repair engine (Redis or in-memory fallback)."""
    config = create_repair_config()
    
    if config.use_redis:
        try:
            logger.info(f"Using Redis cache adapter: {config.redis_host}:{config.redis_port}")
            return RedisAdapter(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password,
                db=config.redis_db,
                key_prefix=config.redis_key_prefix
            )
        except Exception as exc:
            logger.warning(f"Redis connection failed: {exc}, falling back to in-memory cache")
            return MemoryAdapter()
    else:
        logger.info("Using in-memory cache adapter for repair engine")
        return MemoryAdapter()


def create_repair_graph_adapter() -> GraphAdapter:
    """Create graph adapter for repair engine."""
    config = create_repair_config()
    
    if config.graph_adapter == "neo4j":
        logger.info(f"Using Neo4j graph adapter: {config.graph_uri}")
        return Neo4jAdapter(
            uri=config.graph_uri,
            user=config.graph_user,
            password=config.graph_password,
            database=config.graph_database
        )
    else:
        raise ValueError(f"Unsupported graph adapter: {config.graph_adapter}")


def create_repair_db_adapter() -> Optional[RepairDBAdapter]:
    """Create database adapter for repair engine (optional for evaluation storage)."""
    # For now, repair engine can work without dedicated DB adapter
    # Evaluation results can be stored in main backend database
    return None


# ── Singleton Instances ────────────────────────────────────────

_feedback_loop = None
_repair_engine = None

def get_feedback_loop():
    """Get singleton FeedbackLoop instance."""
    global _feedback_loop
    
    if _feedback_loop is None:
        from amc_feedback import FeedbackLoop
        
        config = create_feedback_config()
        db_adapter = create_feedback_db_adapter()
        
        _feedback_loop = FeedbackLoop(
            config=config,
            db_adapter=db_adapter,
            evidence_adapter=None  # Use local file storage
        )
        
        logger.info("Feedback loop initialized")
    
    return _feedback_loop


def get_repair_engine():
    """Get singleton RepairEngine instance."""
    global _repair_engine
    
    if _repair_engine is None:
        from amc_repair import RepairEngine
        
        config = create_repair_config()
        cache_adapter = create_repair_cache_adapter()
        graph_adapter = create_repair_graph_adapter()
        db_adapter = create_repair_db_adapter()
        
        _repair_engine = RepairEngine(
            config=config,
            cache_adapter=cache_adapter,
            graph_adapter=graph_adapter,
            db_adapter=db_adapter
        )
        
        logger.info("Repair engine initialized")
    
    return _repair_engine


async def cleanup_adapters():
    """Cleanup all adapter resources on shutdown."""
    global _feedback_loop, _repair_engine
    
    if _feedback_loop:
        await _feedback_loop.close()
        _feedback_loop = None
        logger.info("Feedback loop closed")
    
    if _repair_engine:
        await _repair_engine.close()
        _repair_engine = None
        logger.info("Repair engine closed")
```

---

### **Step 7.3: Update Main Application Lifespan**

Update `backend/app/main.py`:

```python
# ... existing imports ...
from app.adapters_config import cleanup_adapters, get_feedback_loop, get_repair_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(...)
    
    # ... existing initialization ...
    
    # Initialize modular packages
    try:
        logger.info("Initializing feedback loop package...")
        feedback_loop = get_feedback_loop()
        logger.info("✓ Feedback loop ready")
        
        logger.info("Initializing repair engine package...")
        repair_engine = get_repair_engine()
        logger.info("✓ Repair engine ready")
    except Exception as exc:
        logger.error(f"Failed to initialize packages: {exc}")
        # Continue with degraded functionality
    
    # ... existing warmup code ...
    
    yield
    
    # Shutdown: cleanup package resources
    logger.info("Shutting down modular packages...")
    await cleanup_adapters()
    logger.info("✓ Packages cleaned up")
```

---

### **Step 7.4: Refactor Feedback API Routes**

Update `backend/app/api/routes/feedback.py`:

```python
"""
Feedback routes - now using amc-feedback-loop package.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.adapters_config import get_feedback_loop
from app.api.deps import get_current_user_optional
from app.schemas.feedback_schemas import FeedbackSubmission

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
logger = logging.getLogger("api.feedback")


@router.post("")
async def submit_feedback(
    feedback: FeedbackSubmission,
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Submit user feedback - now powered by amc-feedback-loop package.
    """
    try:
        feedback_loop = get_feedback_loop()
        
        # Process feedback through package
        claim = await feedback_loop.process_feedback(
            session_id=feedback.session_id,
            response_id=feedback.response_id,
            feedback_text=feedback.feedback_text,
            original_query=feedback.original_query or "",
            original_response=feedback.original_response or "",
            issue_types=feedback.issue_types or ["general"],
            source=feedback.source or "web_interface"
        )
        
        # If correction detected, create patch in repair engine
        if claim and claim.resolved_entity_id:
            from app.adapters_config import get_repair_engine
            repair_engine = get_repair_engine()
            
            patch_id = await repair_engine.add_correction(
                entity_id=claim.resolved_entity_id,
                attribute=claim.attribute,
                canonical_value=claim.rejected_value or "unknown",
                corrected_value=claim.asserted_value,
                confidence=claim.confidence,
                provenance={
                    "source": "user_feedback",
                    "feedback_text": feedback.feedback_text,
                    "timestamp": feedback.timestamp.isoformat() if feedback.timestamp else None
                },
                approved=False
            )
            
            logger.info(f"Created correction patch {patch_id} from feedback")
            
            return {
                "status": "correction_detected",
                "message": "Thank you! We've detected a correction and will review it.",
                "claim": claim.to_dict(),
                "patch_id": patch_id
            }
        else:
            return {
                "status": "feedback_recorded",
                "message": "Thank you for your feedback!",
                "claim": None
            }
    
    except Exception as exc:
        logger.error(f"Feedback submission error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/follow-up-detection")
async def detect_follow_up_correction(
    request: dict,
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Automatically detect if follow-up query is a correction.
    Uses passive feedback detection from amc-feedback-loop.
    """
    try:
        feedback_loop = get_feedback_loop()
        
        # Check if this is a correction
        is_correction, confidence, signals = feedback_loop.detector.is_correction_attempt(
            feedback_text=request.get("follow_up_query", ""),
            original_query=request.get("original_query", ""),
            original_response=request.get("original_response", "")
        )
        
        if is_correction and confidence >= 0.70:
            # Auto-create feedback record
            claim = await feedback_loop.process_feedback(
                session_id=request.get("session_id", ""),
                response_id=request.get("previous_response_id", ""),
                feedback_text=request.get("follow_up_query", ""),
                original_query=request.get("original_query", ""),
                original_response=request.get("original_response", ""),
                issue_types=["F02-Accuracy"],
                source="passive_followup"
            )
            
            return {
                "is_correction": True,
                "confidence": confidence,
                "signals": signals,
                "claim": claim.to_dict() if claim else None,
                "auto_created": True
            }
        else:
            return {
                "is_correction": False,
                "confidence": confidence,
                "signals": signals,
                "claim": None,
                "auto_created": False
            }
    
    except Exception as exc:
        logger.error(f"Follow-up detection error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
```

---

### **Step 7.5: Refactor Governance Routes**

Update `backend/app/api/routes/governance.py`:

```python
"""
Governance routes - now using amc-repair-engine package.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.adapters_config import get_repair_engine
from app.api.deps import get_current_user
from app.auth.roles import require_role, UserRole

router = APIRouter(prefix="/api/governance", tags=["governance"])
logger = logging.getLogger("api.governance")


@router.get("/pending-corrections")
async def get_pending_corrections(
    current_user: dict = Depends(require_role(UserRole.REVIEWER))
):
    """
    Get all pending correction patches for governance review.
    Now powered by amc-repair-engine package.
    """
    try:
        repair_engine = get_repair_engine()
        
        pending_patches = await repair_engine.get_pending_corrections()
        
        return {
            "total": len(pending_patches),
            "patches": [
                {
                    "patch_id": p.patch_id,
                    "entity_id": p.entity_id,
                    "attribute": p.attribute,
                    "canonical_value": p.canonical_value,
                    "corrected_value": p.corrected_value,
                    "confidence": p.confidence,
                    "provenance": p.provenance,
                    "created_at": p.created_at.isoformat(),
                    "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                    "risk_level": _calculate_risk_level(p.confidence, p.attribute)
                }
                for p in pending_patches
            ]
        }
    
    except Exception as exc:
        logger.error(f"Get pending corrections error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/patches/{patch_id}/approve")
async def approve_patch(
    patch_id: str,
    current_user: dict = Depends(require_role(UserRole.REVIEWER))
):
    """Approve a correction patch."""
    try:
        repair_engine = get_repair_engine()
        
        success = await repair_engine.approve_correction(patch_id)
        
        if success:
            logger.info(f"Patch {patch_id} approved by {current_user.get('username')}")
            return {"status": "approved", "patch_id": patch_id}
        else:
            raise HTTPException(status_code=404, detail="Patch not found")
    
    except Exception as exc:
        logger.error(f"Approve patch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/patches/{patch_id}/reject")
async def reject_patch(
    patch_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(require_role(UserRole.REVIEWER))
):
    """Reject a correction patch."""
    try:
        repair_engine = get_repair_engine()
        
        success = await repair_engine.reject_correction(patch_id)
        
        if success:
            logger.info(f"Patch {patch_id} rejected by {current_user.get('username')}: {reason}")
            return {"status": "rejected", "patch_id": patch_id}
        else:
            raise HTTPException(status_code=404, detail="Patch not found")
    
    except Exception as exc:
        logger.error(f"Reject patch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/batch-approve")
async def batch_approve_patches(
    patch_ids: List[str],
    current_user: dict = Depends(require_role(UserRole.ADMIN))
):
    """Batch approve multiple patches."""
    try:
        repair_engine = get_repair_engine()
        
        results = {"approved": [], "failed": []}
        
        for patch_id in patch_ids:
            success = await repair_engine.approve_correction(patch_id)
            if success:
                results["approved"].append(patch_id)
            else:
                results["failed"].append(patch_id)
        
        logger.info(f"Batch approve by {current_user.get('username')}: {len(results['approved'])} approved")
        
        return results
    
    except Exception as exc:
        logger.error(f"Batch approve error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/run-batch")
async def run_governance_batch(
    auto_approve_threshold: Optional[float] = None,
    current_user: dict = Depends(require_role(UserRole.ADMIN))
):
    """
    Manually trigger governance batch execution.
    Promotes approved corrections to Neo4j.
    """
    try:
        repair_engine = get_repair_engine()
        
        logger.info(f"Governance batch triggered by {current_user.get('username')}")
        
        report = await repair_engine.run_governance_batch(
            auto_approve_threshold=auto_approve_threshold
        )
        
        return {
            "status": "completed",
            "total_evaluated": report.total_evaluated,
            "approved": report.approved,
            "rejected": report.rejected,
            "needs_review": report.needs_review,
            "deployed": report.deployed,
            "executed_by": current_user.get("username"),
            "timestamp": report.timestamp.isoformat()
        }
    
    except Exception as exc:
        logger.error(f"Governance batch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def _calculate_risk_level(confidence: float, attribute: str) -> str:
    """Calculate risk level for UI display."""
    # Critical attributes (financial data)
    critical_attrs = {"NAV", "TER", "RETURNS", "AUM", "EBITDA", "REVENUE"}
    
    if attribute.upper() in critical_attrs:
        if confidence < 0.75:
            return "HIGH"
        elif confidence < 0.90:
            return "MEDIUM"
        else:
            return "LOW"
    else:
        if confidence < 0.70:
            return "MEDIUM"
        else:
            return "LOW"
```

---

### **Step 7.6: Update Query Orchestrator to Apply Patches**

Update `backend/app/retrieval/orchestrator.py`:

```python
# ... existing imports ...
from app.adapters_config import get_repair_engine

class RetrievalOrchestrator:
    # ... existing code ...
    
    async def answer(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        namespace: Optional[str] = None,
    ) -> OrchestratorResponse:
        """
        Execute complete retrieval pipeline with correction patches applied.
        """
        # ... existing code through retrieval ...
        
        # Step 7.5: Apply correction patches (NEW - from repair engine)
        if resolved_entities and retrieval_result.chunks:
            try:
                repair_engine = get_repair_engine()
                entity_ids = [e.id for e in resolved_entities if hasattr(e, 'id')]
                
                # Apply patches to context before assembly
                patched_context = await repair_engine.apply_patches(
                    entities=entity_ids,
                    retrieval_context={
                        "chunks": [c.dict() for c in retrieval_result.chunks],
                        "graph_facts": [f.dict() for f in retrieval_result.graph_facts] if retrieval_result.graph_facts else []
                    }
                )
                
                # Update retrieval result with patched data
                if "corrections_applied" in patched_context:
                    retrieval_result.corrections_applied = patched_context["corrections_applied"]
                    logger.info(f"Applied {len(patched_context['corrections_applied'])} correction patches")
            
            except Exception as exc:
                logger.warning(f"Failed to apply correction patches: {exc}")
                # Continue without patches on error
        
        # Step 8: Assemble context (with patches now included)
        context = await self._assembler.assemble(...)
        
        # ... rest of synthesis ...
```

---

### **Step 7.7: Update Background Scheduler for Governance**

Update `backend/app/tasks/scheduler.py`:

```python
# ... existing imports ...
from app.adapters_config import get_repair_engine

def register_jobs(scheduler):
    """Register all background jobs."""
    
    # ... existing jobs ...
    
    # Job 3: Weekly Governance Batch (uses repair engine package)
    @scheduler.scheduled_job("cron", day_of_week="fri", hour=9, minute=0, id="weekly_governance_batch")
    async def weekly_governance_batch():
        """Run governance batch to promote approved corrections to Neo4j."""
        logger.info("Starting weekly governance batch...")
        
        try:
            repair_engine = get_repair_engine()
            report = await repair_engine.run_governance_batch()
            
            logger.info(f"Governance batch complete: {report.approved} approved, {report.deployed} deployed")
        except Exception as exc:
            logger.error(f"Governance batch failed: {exc}")
    
    # ... rest of jobs ...
```

---

### **Step 7.8: Remove Old Monolithic Code**

After verifying packages work, remove old implementations:

```bash
# Backup old code first
mkdir -p backend/app/_legacy
mv backend/app/feedback backend/app/_legacy/
mv backend/app/graph/correction_patch_layer.py backend/app/_legacy/
mv backend/app/evaluation/evaluation_router.py backend/app/_legacy/
mv backend/app/tasks/governance_batch.py backend/app/_legacy/

# Update imports across codebase
# Use find & replace to update import statements
```

---

### **Step 7.9: Update Tests**

Update `backend/tests/integration/test_packages_integration.py`:

```python
"""
Integration tests for modular packages.
Verify feedback-loop and repair-engine work with backend.
"""
import pytest
from app.adapters_config import (
    get_feedback_loop,
    get_repair_engine,
    cleanup_adapters
)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_feedback_loop_package_integration():
    """Verify feedback loop package works with backend infrastructure."""
    feedback_loop = get_feedback_loop()
    
    # Submit test feedback
    claim = await feedback_loop.process_feedback(
        session_id="test_session",
        response_id="test_response",
        feedback_text="TER is 0.82%, not 0.79%",
        original_query="What is TER of Axis Bluechip?",
        original_response="TER is 0.79%"
    )
    
    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    
    print("✓ Feedback loop package integration working")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repair_engine_package_integration():
    """Verify repair engine package works with backend infrastructure."""
    repair_engine = get_repair_engine()
    
    # Add test correction
    patch_id = await repair_engine.add_correction(
        entity_id="test_entity",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.88,
        provenance={"source": "test"}
    )
    
    assert patch_id is not None
    
    # Retrieve patch
    pending = await repair_engine.get_pending_corrections()
    assert len(pending) > 0
    
    print("✓ Repair engine package integration working")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_package_workflow():
    """Test complete workflow: feedback → patch → governance."""
    feedback_loop = get_feedback_loop()
    repair_engine = get_repair_engine()
    
    # Step 1: Submit feedback
    claim = await feedback_loop.process_feedback(
        session_id="workflow_test",
        response_id="resp_123",
        feedback_text="TER is 0.82%",
        original_query="What is TER?",
        original_response="TER is 0.79%"
    )
    
    assert claim is not None
    
    # Step 2: Create patch from claim
    patch_id = await repair_engine.add_correction(
        entity_id=claim.resolved_entity_id or "test_entity",
        attribute=claim.attribute,
        canonical_value=claim.rejected_value,
        corrected_value=claim.asserted_value,
        confidence=claim.confidence,
        provenance={"source": "workflow_test"}
    )
    
    assert patch_id is not None
    
    # Step 3: Approve patch
    success = await repair_engine.approve_correction(patch_id)
    assert success
    
    # Step 4: Run governance (would deploy to Neo4j in real scenario)
    report = await repair_engine.run_governance_batch()
    assert report.total_evaluated >= 0
    
    print("✓ Complete package workflow tested")


@pytest.fixture(scope="session", autouse=True)
async def cleanup_after_tests():
    """Cleanup package resources after all tests."""
    yield
    await cleanup_adapters()
```

---

### **Deliverables for Task 7**

- ✅ Packages installed in backend
- ✅ Adapter configuration module created
- ✅ Singleton instances for feedback-loop and repair-engine
- ✅ Feedback API routes refactored to use packages
- ✅ Governance API routes refactored to use packages
- ✅ Query orchestrator applies patches from repair engine
- ✅ Background scheduler uses repair engine for governance
- ✅ Old monolithic code removed/archived
- ✅ Integration tests passing
- ✅ All existing functionality maintained

---

## **TASK 9: IMPLEMENT INTER-SERVICE COMMUNICATION**

**Duration:** 3-4 days  
**Priority:** High  
**Dependencies:** Tasks 5-8 (packages extracted, refactored, containerized)

### **Step 9.1: Design Service-to-Service API Contracts**

Create `backend/app/services/client_base.py`:

```python
"""
Base client for inter-service HTTP communication with retry logic.
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("service_client")


class ServiceClient:
    """Base class for service-to-service HTTP clients."""
    
    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self.max_retries = max_retries
        
        # HTTP/2 persistent connection
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    
    def _get_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build request headers with auth and tracing."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": "amc-platform",  # Calling service
            "X-Target-Service": self.service_name,
            # Add JWT token here when auth is enabled
            # "Authorization": f"Bearer {self._get_service_token()}"
        }
        
        if extra_headers:
            headers.update(extra_headers)
        
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with automatic retry."""
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        request_headers = self._get_headers(headers)
        
        logger.debug(f"{method} {url}")
        
        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=request_headers
            )
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as exc:
            logger.error(f"{self.service_name} HTTP {exc.response.status_code}: {exc}")
            raise ServiceError(f"{self.service_name} error: {exc.response.text}")
        
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(f"{self.service_name} connection error: {exc}")
            raise
        
        except Exception as exc:
            logger.error(f"{self.service_name} unexpected error: {exc}")
            raise ServiceError(f"{self.service_name} failed: {str(exc)}")
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """HTTP GET request."""
        return await self._request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """HTTP POST request."""
        return await self._request("POST", endpoint, json_data=data)
    
    async def put(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """HTTP PUT request."""
        return await self._request("PUT", endpoint, json_data=data)
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """HTTP DELETE request."""
        return await self._request("DELETE", endpoint)
    
    async def health_check(self) -> bool:
        """Check if service is healthy."""
        try:
            response = await self.get("/api/health")
            return response.get("status") == "healthy"
        except Exception:
            return False
    
    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


class ServiceError(Exception):
    """Service communication error."""
    pass
```

---

### **Step 9.2: Create Feedback Service Client**

Create `backend/app/services/feedback_client.py`:

```python
"""
Client for Feedback Loop Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("feedback_client")


class FeedbackServiceClient(ServiceClient):
    """
    Client for communicating with Feedback Loop Service.
    
    Used when feedback and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="feedback-loop",
            timeout=30.0
        )
    
    async def submit_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str,
        original_response: str,
        issue_types: Optional[List[str]] = None,
        source: str = "web_interface"
    ) -> Dict[str, Any]:
        """
        Submit user feedback to feedback service.
        
        Returns:
            Response with status, message, and optional correction claim
        """
        payload = {
            "session_id": session_id,
            "response_id": response_id,
            "feedback_text": feedback_text,
            "original_query": original_query,
            "original_response": original_response,
            "issue_types": issue_types or ["general"],
            "source": source
        }
        
        logger.info(f"Submitting feedback to service: response_id={response_id}")
        
        return await self.post("/api/feedback", payload)
    
    async def detect_follow_up_correction(
        self,
        session_id: str,
        previous_response_id: str,
        original_query: str,
        original_response: str,
        follow_up_query: str,
        session_history: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect if follow-up query is a correction attempt.
        
        Returns:
            Detection result with is_correction flag and confidence
        """
        payload = {
            "session_id": session_id,
            "previous_response_id": previous_response_id,
            "original_query": original_query,
            "original_response": original_response,
            "follow_up_query": follow_up_query,
            "session_history": session_history or []
        }
        
        return await self.post("/api/feedback/follow-up-detection", payload)
    
    async def get_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """Retrieve feedback record by ID."""
        return await self.get(f"/api/feedback/{feedback_id}")
    
    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent feedback submissions."""
        params = {"limit": limit}
        if issue_type:
            params["issue_type"] = issue_type
        
        response = await self.get("/api/feedback/recent", params=params)
        return response.get("feedback", [])
```

---

### **Step 9.3: Create Repair Service Client**

Create `backend/app/services/repair_client.py`:

```python
"""
Client for Repair Engine Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("repair_client")


class RepairServiceClient(ServiceClient):
    """
    Client for communicating with Repair Engine Service.
    
    Used when repair engine and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="repair-engine",
            timeout=30.0
        )
    
    async def create_correction_patch(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """
        Create correction patch in repair engine.
        
        Returns:
            patch_id: Unique identifier for the patch
        """
        payload = {
            "entity_id": entity_id,
            "attribute": attribute,
            "canonical_value": canonical_value,
            "corrected_value": corrected_value,
            "confidence": confidence,
            "provenance": provenance,
            "approved": approved
        }
        
        logger.info(f"Creating correction patch: {entity_id}.{attribute}")
        
        response = await self.post("/api/patches", payload)
        return response["patch_id"]
    
    async def get_patches_for_entities(
        self,
        entity_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Get all patches for specified entities.
        
        Used during query orchestration to apply corrections.
        """
        params = {"entity_ids": ",".join(entity_ids)}
        response = await self.get("/api/patches/for-entities", params=params)
        return response.get("patches", [])
    
    async def get_pending_corrections(self) -> List[Dict[str, Any]]:
        """Get all pending (unapproved) corrections."""
        response = await self.get("/api/patches/pending")
        return response.get("patches", [])
    
    async def approve_patch(self, patch_id: str) -> bool:
        """Approve a correction patch."""
        response = await self.post(f"/api/patches/{patch_id}/approve", {})
        return response.get("status") == "approved"
    
    async def reject_patch(self, patch_id: str, reason: Optional[str] = None) -> bool:
        """Reject a correction patch."""
        payload = {"reason": reason} if reason else {}
        response = await self.post(f"/api/patches/{patch_id}/reject", payload)
        return response.get("status") == "rejected"
    
    async def batch_approve_patches(self, patch_ids: List[str]) -> Dict[str, List[str]]:
        """Batch approve multiple patches."""
        payload = {"patch_ids": patch_ids}
        return await self.post("/api/patches/batch-approve", payload)
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Trigger governance batch execution."""
        payload = {}
        if auto_approve_threshold:
            payload["auto_approve_threshold"] = auto_approve_threshold
        
        logger.info("Triggering governance batch on repair service")
        
        return await self.post("/api/governance/run-batch", payload)
    
    async def evaluate_answer(
        self,
        response_id: str,
        response_text: str,
        retrieved_context: str,
        query: str,
        intent: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Evaluate answer quality using tiered evaluation."""
        payload = {
            "response_id": response_id,
            "response_text": response_text,
            "retrieved_context": retrieved_context,
            "query": query,
            "intent": intent
        }
        
        return await self.post("/api/evaluation/evaluate", payload)
```

---

### **Step 9.4: Add Circuit Breaker Pattern**

Create `backend/app/services/circuit_breaker.py`:

```python
"""
Circuit breaker pattern for inter-service calls.
Prevents cascading failures when services are down.
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Service failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for service calls.
    
    States:
    - CLOSED: Normal operation, allow all calls
    - OPEN: Service failing, reject calls immediately
    - HALF_OPEN: Testing recovery, allow limited calls
    """
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpen: When circuit is open (service unavailable)
        """
        async with self._lock:
            # Check if we should transition to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if self.last_failure_time and (time.time() - self.last_failure_time) >= self.recovery_timeout:
                    logger.info(f"Circuit breaker {self.service_name}: OPEN -> HALF_OPEN (recovery timeout)")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpen(f"{self.service_name} circuit breaker is OPEN")
        
        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except Exception as exc:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logger.info(f"Circuit breaker {self.service_name}: HALF_OPEN -> CLOSED (recovery successful)")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = max(0, self.failure_count - 1)
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit breaker {self.service_name}: HALF_OPEN -> OPEN (recovery failed)")
                self.state = CircuitState.OPEN
                self.success_count = 0
            
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(f"Circuit breaker {self.service_name}: CLOSED -> OPEN (threshold reached: {self.failure_count} failures)")
                    self.state = CircuitState.OPEN
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN
    
    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
```

---

### **Step 9.5: Update Orchestrator with Service Clients**

Update `backend/app/retrieval/orchestrator.py`:

```python
# ... existing imports ...
from app.services.repair_client import RepairServiceClient
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

class RetrievalOrchestrator:
    def __init__(self, ...):
        # ... existing initialization ...
        
        # Service clients (only if microservices mode enabled)
        self._repair_client = None
        self._repair_circuit_breaker = None
        
        if self._settings.microservices_mode:
            self._repair_client = RepairServiceClient(
                base_url=self._settings.repair_service_url
            )
            self._repair_circuit_breaker = CircuitBreaker(
                service_name="repair-engine",
                failure_threshold=5,
                recovery_timeout=60.0
            )
    
    async def _apply_correction_patches(
        self,
        entity_ids: List[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply correction patches (microservices-aware)."""
        
        # Microservices mode: call repair service
        if self._settings.microservices_mode and self._repair_client:
            try:
                # Use circuit breaker for resilience
                patches = await self._repair_circuit_breaker.call(
                    self._repair_client.get_patches_for_entities,
                    entity_ids
                )
                
                # Apply patches to context
                if patches:
                    context["corrections_applied"] = [
                        {
                            "entity_id": p["entity_id"],
                            "attribute": p["attribute"],
                            "original": p["canonical_value"],
                            "corrected": p["corrected_value"],
                            "confidence": p["confidence"]
                        }
                        for p in patches
                        if p["confidence"] >= 0.70
                    ]
                
                logger.info(f"Applied {len(patches)} patches from repair service")
            
            except CircuitBreakerOpen:
                logger.warning("Repair service circuit breaker OPEN, skipping patches")
            
            except Exception as exc:
                logger.error(f"Failed to apply patches from repair service: {exc}")
        
        # Monolithic mode: use local repair engine
        else:
            from app.adapters_config import get_repair_engine
            repair_engine = get_repair_engine()
            context = await repair_engine.apply_patches(entity_ids, context)
        
        return context
```

---

### **Step 9.6: Add Service Discovery & Configuration**

Update `backend/app/config.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # ── Microservices Configuration ──────────────────────────────
    microservices_mode: bool = Field(
        default=False,
        description="Enable microservices mode (separate service communication)"
    )
    
    feedback_service_url: Optional[str] = Field(
        default=None,
        description="Feedback Loop Service URL (e.g., http://feedback:8001)"
    )
    
    repair_service_url: Optional[str] = Field(
        default=None,
        description="Repair Engine Service URL (e.g., http://repair:8002)"
    )
    
    service_auth_enabled: bool = Field(
        default=False,
        description="Enable JWT authentication for service-to-service calls"
    )
    
    service_jwt_secret: Optional[str] = Field(
        default=None,
        description="JWT secret for service authentication"
    )
```

---

### **Step 9.7: Create Health Check Aggregator**

Create `backend/app/api/routes/health.py`:

```python
"""
Health check endpoint with service dependency checks.
"""
import asyncio
from typing import Dict, Any

from fastapi import APIRouter
from app.config import get_settings
from app.services.feedback_client import FeedbackServiceClient
from app.services.repair_client import RepairServiceClient

router = APIRouter()


@router.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint with dependency status.
    
    Returns overall health and status of each dependency.
    """
    settings = get_settings()
    
    health_status = {
        "status": "healthy",
        "service": "amc-platform",
        "mode": "microservices" if settings.microservices_mode else "monolithic",
        "dependencies": {}
    }
    
    # Check dependencies in parallel
    dependency_checks = [
        _check_neo4j(),
        _check_redis(),
        _check_faiss(),
    ]
    
    # If microservices mode, check service dependencies
    if settings.microservices_mode:
        if settings.feedback_service_url:
            dependency_checks.append(_check_feedback_service(settings.feedback_service_url))
        if settings.repair_service_url:
            dependency_checks.append(_check_repair_service(settings.repair_service_url))
    
    results = await asyncio.gather(*dependency_checks, return_exceptions=True)
    
    # Aggregate results
    for result in results:
        if isinstance(result, dict):
            health_status["dependencies"].update(result)
        elif isinstance(result, Exception):
            health_status["status"] = "degraded"
            health_status["dependencies"]["error"] = str(result)
    
    # Overall status based on critical dependencies
    critical_deps = ["neo4j", "faiss"]
    if any(
        health_status["dependencies"].get(dep, {}).get("status") == "unhealthy"
        for dep in critical_deps
    ):
        health_status["status"] = "unhealthy"
    
    return health_status


async def _check_neo4j() -> Dict[str, Any]:
    """Check Neo4j connectivity."""
    try:
        from app.engine.graph_store import get_driver
        driver = get_driver()
        await driver.verify_connectivity()
        return {"neo4j": {"status": "healthy"}}
    except Exception as exc:
        return {"neo4j": {"status": "unhealthy", "error": str(exc)}}


async def _check_redis() -> Dict[str, Any]:
    """Check Redis connectivity."""
    settings = get_settings()
    if not settings.redis_url:
        return {"redis": {"status": "not_configured"}}
    
    try:
        import redis.asyncio as redis
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.close()
        return {"redis": {"status": "healthy"}}
    except Exception as exc:
        return {"redis": {"status": "unhealthy", "error": str(exc)}}


async def _check_faiss() -> Dict[str, Any]:
    """Check FAISS index loaded."""
    try:
        from app.vector.client import get_vector_store
        store = get_vector_store()
        # Simple check that index exists
        return {"faiss": {"status": "healthy", "index_size": store.get_index_size()}}
    except Exception as exc:
        return {"faiss": {"status": "unhealthy", "error": str(exc)}}


async def _check_feedback_service(url: str) -> Dict[str, Any]:
    """Check Feedback Service health."""
    try:
        client = FeedbackServiceClient(url)
        is_healthy = await client.health_check()
        await client.close()
        
        return {
            "feedback_service": {
                "status": "healthy" if is_healthy else "unhealthy",
                "url": url
            }
        }
    except Exception as exc:
        return {
            "feedback_service": {
                "status": "unhealthy",
                "url": url,
                "error": str(exc)
            }
        }


async def _check_repair_service(url: str) -> Dict[str, Any]:
    """Check Repair Service health."""
    try:
        client = RepairServiceClient(url)
        is_healthy = await client.health_check()
        await client.close()
        
        return {
            "repair_service": {
                "status": "healthy" if is_healthy else "unhealthy",
                "url": url
            }
        }
    except Exception as exc:
        return {
            "repair_service": {
                "status": "unhealthy",
                "url": url,
                "error": str(exc)
            }
        }
```

---

### **Deliverables for Task 9**

- ✅ Base service client with retry logic
- ✅ Feedback service client
- ✅ Repair service client
- ✅ Circuit breaker pattern implemented
- ✅ Service discovery configuration
- ✅ Health check aggregator with dependency status
- ✅ Orchestrator updated for microservices mode
- ✅ Graceful degradation when services unavailable

---

**Would you like me to continue with Task 10 (Integration Testing & Documentation)?**

Perfect! Let me complete the detailed implementation plan with Task 10.

---

## **TASK 10: END-TO-END INTEGRATION TESTING & DOCUMENTATION**

**Duration:** 3-4 days  
**Priority:** Critical  
**Dependencies:** All previous tasks (1-9) completed

### **Step 10.1: Create Comprehensive Integration Test Suite**

Create `backend/tests/integration/test_complete_microservices_flow.py`:

```python
"""
Complete end-to-end integration tests for microservices architecture.
Tests user journeys across all three services.
"""
import asyncio
import pytest
from typing import List, Dict, Any
import httpx
from datetime import datetime

# Service URLs (configured via environment or docker-compose)
PLATFORM_URL = "http://localhost:8000"
FEEDBACK_URL = "http://localhost:8001"
REPAIR_URL = "http://localhost:8002"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_complete_user_journey_query_to_correction():
    """
    Test Case 1: Complete user journey from query to correction deployment.
    
    Flow:
    1. User submits query → AMC Platform
    2. Platform retrieves answer (with potential inaccuracy)
    3. User submits correction feedback → Feedback Service
    4. Feedback Service detects correction → creates patch in Repair Service
    5. Reviewer approves patch → Repair Service
    6. Governance batch deploys to Neo4j → Repair Service
    7. User re-queries → gets corrected answer
    """
    async with httpx.AsyncClient() as client:
        
        # ── Step 1: Submit Query ──────────────────────────────────
        print("\n[Step 1] User submits query to AMC Platform...")
        
        query_payload = {
            "query": "What is the TER of Axis Bluechip Fund?",
            "session_id": "test_e2e_session",
        }
        
        response = await client.post(
            f"{PLATFORM_URL}/api/query",
            json=query_payload,
            timeout=30.0
        )
        
        assert response.status_code == 200
        query_result = response.json()
        
        response_id = query_result.get("response_id")
        original_answer = query_result.get("answer", "")
        
        assert response_id is not None
        assert "TER" in original_answer or "expense" in original_answer.lower()
        
        print(f"✓ Query successful: response_id={response_id}")
        print(f"  Answer: {original_answer[:100]}...")
        
        # ── Step 2: Submit Correction Feedback ───────────────────
        print("\n[Step 2] User submits correction feedback...")
        
        feedback_payload = {
            "session_id": "test_e2e_session",
            "response_id": response_id,
            "feedback_text": "The TER is actually 0.82%, not 0.79%",
            "original_query": query_payload["query"],
            "original_response": original_answer,
            "issue_types": ["F02-Accuracy"],
            "source": "web_interface"
        }
        
        response = await client.post(
            f"{FEEDBACK_URL}/api/feedback",
            json=feedback_payload,
            timeout=30.0
        )
        
        assert response.status_code == 200
        feedback_result = response.json()
        
        assert feedback_result.get("status") == "correction_detected"
        claim = feedback_result.get("claim")
        patch_id = feedback_result.get("patch_id")
        
        assert claim is not None
        assert claim["attribute"] == "TER"
        assert claim["asserted_value"] == "0.82"
        assert patch_id is not None
        
        print(f"✓ Correction detected and patch created: patch_id={patch_id}")
        print(f"  Entity: {claim.get('resolved_entity_name')} ({claim.get('resolved_entity_id')})")
        print(f"  Correction: {claim['rejected_value']} → {claim['asserted_value']}")
        
        # ── Step 3: Verify Patch Created in Repair Service ──────
        print("\n[Step 3] Verify patch in Repair Service...")
        
        response = await client.get(
            f"{REPAIR_URL}/api/patches/pending",
            timeout=10.0
        )
        
        assert response.status_code == 200
        pending_patches = response.json()
        
        patch = next((p for p in pending_patches["patches"] if p["patch_id"] == patch_id), None)
        assert patch is not None
        assert patch["approved"] == False
        
        print(f"✓ Patch found in pending queue")
        print(f"  Confidence: {patch['confidence']:.0%}")
        print(f"  Expires: {patch['expires_at']}")
        
        # ── Step 4: Approve Patch (as Reviewer) ─────────────────
        print("\n[Step 4] Reviewer approves patch...")
        
        # Note: In production, this would require authentication
        response = await client.post(
            f"{REPAIR_URL}/api/patches/{patch_id}/approve",
            json={},
            timeout=10.0
        )
        
        assert response.status_code == 200
        approval_result = response.json()
        assert approval_result["status"] == "approved"
        
        print(f"✓ Patch approved successfully")
        
        # ── Step 5: Run Governance Batch ─────────────────────────
        print("\n[Step 5] Run governance batch to deploy corrections...")
        
        response = await client.post(
            f"{REPAIR_URL}/api/governance/run-batch",
            json={},
            timeout=60.0  # Governance batch may take longer
        )
        
        assert response.status_code == 200
        governance_report = response.json()
        
        assert governance_report["status"] == "completed"
        assert governance_report["approved"] >= 1
        assert governance_report["deployed"] >= 1
        
        print(f"✓ Governance batch complete")
        print(f"  Approved: {governance_report['approved']}")
        print(f"  Deployed to Neo4j: {governance_report['deployed']}")
        
        # ── Step 6: Re-Query to Verify Correction ───────────────
        print("\n[Step 6] User re-queries to verify correction...")
        
        # Wait a bit for Neo4j to propagate changes
        await asyncio.sleep(2)
        
        response = await client.post(
            f"{PLATFORM_URL}/api/query",
            json={
                "query": query_payload["query"],
                "session_id": "test_e2e_session_requery"
            },
            timeout=30.0
        )
        
        assert response.status_code == 200
        requery_result = response.json()
        
        new_answer = requery_result.get("answer", "")
        
        # Verify correction is reflected (either from patch or Neo4j)
        assert "0.82" in new_answer or requery_result.get("corrections_applied")
        
        print(f"✓ Re-query successful with corrected data")
        print(f"  Answer: {new_answer[:100]}...")
        
        if requery_result.get("corrections_applied"):
            print(f"  Corrections applied: {len(requery_result['corrections_applied'])}")
        
        print("\n" + "="*80)
        print("✅ COMPLETE USER JOURNEY TEST PASSED")
        print("   Query → Feedback → Patch → Approval → Governance → Corrected Answer")
        print("="*80)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_passive_feedback_detection():
    """
    Test Case 2: Passive feedback detection via follow-up queries.
    
    Flow:
    1. User submits initial query
    2. User submits follow-up with correction (different session turn)
    3. System auto-detects correction without explicit feedback
    4. Patch created automatically
    """
    async with httpx.AsyncClient() as client:
        
        print("\n[Test Case 2] Passive feedback detection...")
        
        # Step 1: Initial query
        initial_response = await client.post(
            f"{PLATFORM_URL}/api/query",
            json={
                "query": "What is HDFC Balanced Advantage Fund's AUM?",
                "session_id": "passive_test_session"
            },
            timeout=30.0
        )
        
        assert initial_response.status_code == 200
        initial_result = initial_response.json()
        response_id = initial_result["response_id"]
        original_answer = initial_result["answer"]
        
        print(f"✓ Initial query: response_id={response_id}")
        
        # Step 2: Follow-up with implicit correction
        follow_up_response = await client.post(
            f"{FEEDBACK_URL}/api/feedback/follow-up-detection",
            json={
                "session_id": "passive_test_session",
                "previous_response_id": response_id,
                "original_query": "What is HDFC Balanced Advantage Fund's AUM?",
                "original_response": original_answer,
                "follow_up_query": "Actually, the AUM is ₹50,000 Cr, not ₹48,000 Cr"
            },
            timeout=20.0
        )
        
        assert follow_up_response.status_code == 200
        detection_result = follow_up_response.json()
        
        assert detection_result["is_correction"] == True
        assert detection_result["confidence"] >= 0.65
        assert detection_result["auto_created"] == True
        
        claim = detection_result.get("claim")
        assert claim is not None
        assert claim["attribute"] == "AUM"
        
        print(f"✓ Passive correction detected")
        print(f"  Confidence: {detection_result['confidence']:.0%}")
        print(f"  Attribute: {claim['attribute']}")
        print(f"  Correction: {claim['rejected_value']} → {claim['asserted_value']}")
        
        print("\n✅ PASSIVE FEEDBACK DETECTION TEST PASSED")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_service_health_checks():
    """
    Test Case 3: Verify all services are healthy and communicating.
    """
    async with httpx.AsyncClient() as client:
        
        print("\n[Test Case 3] Service health checks...")
        
        services = {
            "AMC Platform": f"{PLATFORM_URL}/api/health",
            "Feedback Service": f"{FEEDBACK_URL}/api/health",
            "Repair Service": f"{REPAIR_URL}/api/health"
        }
        
        for service_name, health_url in services.items():
            response = await client.get(health_url, timeout=10.0)
            
            assert response.status_code == 200
            health = response.json()
            
            assert health.get("status") in ["healthy", "degraded"]
            
            print(f"✓ {service_name}: {health['status']}")
            
            if "dependencies" in health:
                for dep_name, dep_status in health["dependencies"].items():
                    status = dep_status.get("status", "unknown")
                    print(f"    - {dep_name}: {status}")
        
        print("\n✅ ALL SERVICES HEALTHY")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_circuit_breaker_resilience():
    """
    Test Case 4: Verify system resilience when repair service is unavailable.
    
    Simulates repair service failure to test circuit breaker and graceful degradation.
    """
    from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
    
    print("\n[Test Case 4] Circuit breaker resilience test...")
    
    circuit_breaker = CircuitBreaker(
        service_name="test_service",
        failure_threshold=3,
        recovery_timeout=5.0,
        success_threshold=2
    )
    
    # Simulate failures
    async def failing_service():
        raise Exception("Service unavailable")
    
    # Trigger failures to open circuit
    failure_count = 0
    for i in range(5):
        try:
            await circuit_breaker.call(failing_service)
        except Exception:
            failure_count += 1
    
    assert failure_count >= 3
    assert circuit_breaker.is_open()
    print(f"✓ Circuit breaker opened after {failure_count} failures")
    
    # Verify circuit breaker rejects calls
    try:
        await circuit_breaker.call(failing_service)
        assert False, "Should have raised CircuitBreakerOpen"
    except CircuitBreakerOpen:
        print("✓ Circuit breaker correctly rejects calls when OPEN")
    
    # Wait for recovery timeout
    print("  Waiting for recovery timeout (5s)...")
    await asyncio.sleep(6)
    
    # Simulate successful recovery
    async def healthy_service():
        return "success"
    
    # Circuit should transition to HALF_OPEN and allow test calls
    result1 = await circuit_breaker.call(healthy_service)
    result2 = await circuit_breaker.call(healthy_service)
    
    assert result1 == "success"
    assert result2 == "success"
    assert not circuit_breaker.is_open()
    
    print("✓ Circuit breaker recovered and closed after successful calls")
    print("\n✅ CIRCUIT BREAKER RESILIENCE TEST PASSED")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_concurrent_user_load():
    """
    Test Case 5: Concurrent load testing with 10 simultaneous users.
    """
    async with httpx.AsyncClient() as client:
        
        print("\n[Test Case 5] Concurrent load test (10 users)...")
        
        queries = [
            "What is the TER of Axis Bluechip Fund?",
            "Show me ESG scores for Adani Group companies",
            "What are SEBI regulations for debt mutual funds?",
            "How is HDFC Balanced Advantage Fund performing?",
            "What is the NAV of ICICI Prudential Equity Fund?"
        ] * 2  # 10 queries total
        
        async def submit_query(query: str, user_id: int):
            start_time = asyncio.get_event_loop().time()
            
            response = await client.post(
                f"{PLATFORM_URL}/api/query",
                json={
                    "query": query,
                    "session_id": f"load_test_user_{user_id}"
                },
                timeout=60.0
            )
            
            elapsed = asyncio.get_event_loop().time() - start_time
            
            return {
                "user_id": user_id,
                "status_code": response.status_code,
                "elapsed_ms": elapsed * 1000,
                "success": response.status_code == 200
            }
        
        # Execute all queries concurrently
        start_time = asyncio.get_event_loop().time()
        
        tasks = [
            submit_query(query, i)
            for i, query in enumerate(queries)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_elapsed = asyncio.get_event_loop().time() - start_time
        
        # Analyze results
        successful = sum(1 for r in results if not isinstance(r, Exception) and r.get("success"))
        failed = len(results) - successful
        
        latencies = [r["elapsed_ms"] for r in results if not isinstance(r, Exception)]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        
        print(f"\n✓ Concurrent load test complete:")
        print(f"  Total Users: {len(queries)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Total Time: {total_elapsed:.2f}s")
        print(f"  Avg Latency: {avg_latency:.0f}ms")
        print(f"  P95 Latency: {p95_latency:.0f}ms")
        
        # Assert success criteria
        assert successful >= len(queries) * 0.9, "At least 90% queries should succeed"
        assert avg_latency < 5000, "Average latency should be under 5 seconds"
        assert p95_latency < 10000, "P95 latency should be under 10 seconds"
        
        print("\n✅ CONCURRENT LOAD TEST PASSED")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_data_consistency_across_services():
    """
    Test Case 6: Verify data consistency across services.
    
    Ensures that feedback recorded in Feedback Service is accessible
    and correctly integrated with Repair Service patches.
    """
    async with httpx.AsyncClient() as client:
        
        print("\n[Test Case 6] Data consistency test...")
        
        # Submit feedback
        feedback_payload = {
            "session_id": "consistency_test",
            "response_id": "resp_consistency_123",
            "feedback_text": "TER should be 0.85%",
            "original_query": "What is TER?",
            "original_response": "TER is 0.79%",
            "issue_types": ["F02-Accuracy"],
            "source": "test"
        }
        
        fb_response = await client.post(
            f"{FEEDBACK_URL}/api/feedback",
            json=feedback_payload,
            timeout=20.0
        )
        
        assert fb_response.status_code == 200
        fb_result = fb_response.json()
        patch_id = fb_result.get("patch_id")
        
        assert patch_id is not None
        print(f"✓ Feedback submitted: patch_id={patch_id}")
        
        # Verify patch exists in Repair Service
        repair_response = await client.get(
            f"{REPAIR_URL}/api/patches/pending",
            timeout=10.0
        )
        
        assert repair_response.status_code == 200
        patches = repair_response.json()["patches"]
        
        patch = next((p for p in patches if p["patch_id"] == patch_id), None)
        assert patch is not None
        assert patch["provenance"].get("source") == "user_feedback"
        
        print(f"✓ Patch verified in Repair Service")
        print(f"  Provenance: {patch['provenance']}")
        
        print("\n✅ DATA CONSISTENCY TEST PASSED")
```

---

### **Step 10.2: Create Performance Benchmarking Suite**

Create `backend/tests/performance/benchmark_microservices.py`:

```python
"""
Performance benchmarking for microservices architecture.
Compares monolithic vs microservices performance.
"""
import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx

PLATFORM_URL = "http://localhost:8000"


async def benchmark_query_latency(num_queries: int = 50) -> Dict[str, Any]:
    """Benchmark query latency across multiple requests."""
    
    queries = [
        "What is the TER of Axis Bluechip Fund?",
        "Show me ESG scores for Adani Enterprises",
        "What are SEBI regulations for mutual funds?",
        "How is HDFC Equity Fund performing?",
        "What is NAV of ICICI Prudential Fund?"
    ]
    
    latencies: List[float] = []
    errors = 0
    
    async with httpx.AsyncClient() as client:
        for i in range(num_queries):
            query = queries[i % len(queries)]
            
            start = time.perf_counter()
            
            try:
                response = await client.post(
                    f"{PLATFORM_URL}/api/query",
                    json={"query": query, "session_id": f"bench_{i}"},
                    timeout=30.0
                )
                
                elapsed = (time.perf_counter() - start) * 1000
                
                if response.status_code == 200:
                    latencies.append(elapsed)
                else:
                    errors += 1
            
            except Exception as exc:
                errors += 1
    
    if not latencies:
        return {"error": "All queries failed"}
    
    return {
        "total_queries": num_queries,
        "successful": len(latencies),
        "failed": errors,
        "latency_ms": {
            "min": min(latencies),
            "max": max(latencies),
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95)],
            "p99": sorted(latencies)[int(len(latencies) * 0.99)],
        }
    }


async def benchmark_feedback_submission(num_submissions: int = 20) -> Dict[str, Any]:
    """Benchmark feedback submission latency."""
    
    latencies: List[float] = []
    errors = 0
    
    async with httpx.AsyncClient() as client:
        for i in range(num_submissions):
            start = time.perf_counter()
            
            try:
                response = await client.post(
                    f"{PLATFORM_URL}/api/feedback",
                    json={
                        "session_id": f"bench_{i}",
                        "response_id": f"resp_{i}",
                        "feedback_text": "TER is 0.82%",
                        "original_query": "What is TER?",
                        "original_response": "TER is 0.79%",
                        "issue_types": ["F02-Accuracy"]
                    },
                    timeout=20.0
                )
                
                elapsed = (time.perf_counter() - start) * 1000
                
                if response.status_code == 200:
                    latencies.append(elapsed)
                else:
                    errors += 1
            
            except Exception:
                errors += 1
    
    if not latencies:
        return {"error": "All submissions failed"}
    
    return {
        "total_submissions": num_submissions,
        "successful": len(latencies),
        "failed": errors,
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95)],
        }
    }


async def run_all_benchmarks():
    """Run complete benchmark suite."""
    
    print("="*80)
    print("MICROSERVICES PERFORMANCE BENCHMARK")
    print("="*80)
    
    # Benchmark 1: Query latency
    print("\n[Benchmark 1] Query latency (50 queries)...")
    query_results = await benchmark_query_latency(50)
    
    print(f"\nResults:")
    print(f"  Successful: {query_results['successful']}/{query_results['total_queries']}")
    print(f"  Mean latency: {query_results['latency_ms']['mean']:.0f}ms")
    print(f"  Median latency: {query_results['latency_ms']['median']:.0f}ms")
    print(f"  P95 latency: {query_results['latency_ms']['p95']:.0f}ms")
    print(f"  P99 latency: {query_results['latency_ms']['p99']:.0f}ms")
    print(f"  Min: {query_results['latency_ms']['min']:.0f}ms")
    print(f"  Max: {query_results['latency_ms']['max']:.0f}ms")
    
    # Benchmark 2: Feedback submission
    print("\n[Benchmark 2] Feedback submission (20 submissions)...")
    feedback_results = await benchmark_feedback_submission(20)
    
    print(f"\nResults:")
    print(f"  Successful: {feedback_results['successful']}/{feedback_results['total_submissions']}")
    print(f"  Mean latency: {feedback_results['latency_ms']['mean']:.0f}ms")
    print(f"  Median latency: {feedback_results['latency_ms']['median']:.0f}ms")
    print(f"  P95 latency: {feedback_results['latency_ms']['p95']:.0f}ms")
    
    # Success criteria
    print("\n" + "="*80)
    print("SUCCESS CRITERIA")
    print("="*80)
    
    criteria = [
        ("Query P95 latency < 3000ms", query_results['latency_ms']['p95'] < 3000),
        ("Query success rate > 95%", query_results['successful'] / query_results['total_queries'] > 0.95),
        ("Feedback P95 latency < 1000ms", feedback_results['latency_ms']['p95'] < 1000),
    ]
    
    for criterion, passed in criteria:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {criterion}")
    
    all_passed = all(passed for _, passed in criteria)
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ ALL BENCHMARKS PASSED - System meets performance targets")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("⚠️  SOME BENCHMARKS FAILED - Review performance optimization")
        print("="*80)
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
```

---

### **Step 10.3: Create Migration Guide**

Create `Docs/05-Operations-and-Deployment/PHASE2_MIGRATION_GUIDE.md`:

```markdown
# Phase 2 Migration Guide: Monolithic → Microservices

**Version:** 1.0  
**Date:** January 2025  
**Audience:** DevOps, Backend Engineers

---

## Overview

This guide walks through migrating the AMC Context Engineering platform from a monolithic architecture to a microservices architecture.

**Timeline:** 1-2 weeks for staged rollout  
**Downtime:** Zero (blue-green deployment)  
**Rollback:** < 5 minutes

---

## Pre-Migration Checklist

### ✅ Infrastructure Ready

- [ ] Docker and Docker Compose installed
- [ ] PostgreSQL 15+ available (or continue with SQLite for dev)
- [ ] Redis 7+ available (or use in-memory fallback)
- [ ] Neo4j 5.13+ running and accessible
- [ ] Sufficient resources:
  - CPU: 4+ cores
  - RAM: 8GB+ (12GB recommended)
  - Disk: 50GB+ free space

### ✅ Code Preparation

- [ ] All packages built and tested:
  - `amc-feedback-loop` v0.1.0
  - `amc-repair-engine` v0.1.0
- [ ] Docker images built:
  - `amc-platform:latest`
  - `amc-feedback:latest`
  - `amc-repair:latest`
- [ ] Integration tests passing (95%+ success rate)
- [ ] Performance benchmarks acceptable

### ✅ Backup & Rollback Plan

- [ ] Database backed up (SQLite: `data.db`, PostgreSQL: pg_dump)
- [ ] Neo4j graph exported (`export_neo4j_dump.py`)
- [ ] FAISS indexes backed up (`faiss_indexes/`)
- [ ] Environment variables documented
- [ ] Monolithic deployment preserved for rollback

---

## Migration Paths

### Path A: Development/Staging (Recommended First)

**Strategy:** Direct cut-over with docker-compose

**Steps:**
1. Stop monolithic deployment
2. Deploy microservices stack
3. Smoke test
4. If successful → proceed to production
5. If issues → rollback (< 5 min)

**Downtime:** 2-5 minutes

### Path B: Production (Blue-Green)

**Strategy:** Run both architectures in parallel, gradual traffic shift

**Steps:**
1. Deploy microservices stack (green)
2. Route 10% traffic to green
3. Monitor for 24 hours
4. Gradually increase to 50% → 100%
5. Deprecate monolithic stack (blue)

**Downtime:** Zero

---

## Step-by-Step Migration

### Phase 1: Pre-Migration Validation (1 day)

#### 1.1 Verify Current System Health

```bash
# Check monolithic deployment
curl http://localhost:8000/api/health

# Run integration tests
cd backend
pytest tests/integration/ -v

# Verify data integrity
python scripts/verify_data_integrity.py
```

#### 1.2 Backup Everything

```bash
# Backup SQLite database
cp backend/data.db backend/data.db.backup_$(date +%Y%m%d)

# Export Neo4j graph
cd backend
python export_neo4j_dump.py

# Backup FAISS indexes
tar -czf faiss_indexes_backup_$(date +%Y%m%d).tar.gz faiss_indexes/

# Backup configuration
cp backend/.env backend/.env.backup_$(date +%Y%m%d)
```

#### 1.3 Build Docker Images

```bash
# Build all service images
cd context-engineering

# Platform service
docker build -t amc-platform:latest -f backend/Dockerfile.platform backend/

# Feedback service
docker build -t amc-feedback:latest -f backend/Dockerfile.feedback backend/

# Repair service
docker build -t amc-repair:latest -f backend/Dockerfile.repair backend/

# Verify images
docker images | grep amc-
```

---

### Phase 2: Deploy Microservices Stack (2-4 hours)

#### 2.1 Create docker-compose.yml

Already created in Task 8. Verify configuration:

```bash
cd context-engineering
cat docker-compose.yml

# Update environment variables if needed
cp .env.example .env
nano .env  # Edit service URLs, passwords, etc.
```

#### 2.2 Start Infrastructure Services

```bash
# Start databases first
docker-compose up -d postgres redis neo4j

# Wait for services to be ready
docker-compose logs -f postgres redis neo4j

# Verify connectivity
docker-compose exec postgres pg_isready
docker-compose exec redis redis-cli ping
docker-compose exec neo4j cypher-shell "RETURN 1"
```

#### 2.3 Migrate Data to PostgreSQL (if applicable)

If migrating from SQLite to PostgreSQL:

```bash
# Export SQLite data
python backend/scripts/export_sqlite_to_sql.py > data_export.sql

# Import to PostgreSQL
docker-compose exec -T postgres psql -U amc -d amc_platform < data_export.sql

# Verify row counts match
python backend/scripts/verify_migration.py
```

#### 2.4 Start Application Services

```bash
# Start all application services
docker-compose up -d amc-platform feedback repair frontend

# Check service health
docker-compose ps

# Follow logs
docker-compose logs -f amc-platform feedback repair
```

#### 2.5 Smoke Test

```bash
# Test Platform service
curl http://localhost:8000/api/health

# Test Feedback service
curl http://localhost:8001/api/health

# Test Repair service
curl http://localhost:8002/api/health

# Test Frontend
curl http://localhost:3000

# Run quick integration test
cd backend
pytest tests/integration/test_microservices_smoke.py -v
```

---

### Phase 3: Validation & Monitoring (24-48 hours)

#### 3.1 Run Full Integration Tests

```bash
cd backend

# Complete E2E tests
pytest tests/integration/test_complete_microservices_flow.py -v -s

# Performance benchmarks
python tests/performance/benchmark_microservices.py

# Load test (50 concurrent users)
locust -f tests/load/locustfile.py --host=http://localhost:8000 --users=50 --spawn-rate=5 --run-time=5m --headless
```

#### 3.2 Monitor Key Metrics

**Service Health:**
```bash
# Check all services every 5 minutes
watch -n 300 "curl -s http://localhost:8000/api/health | jq '.dependencies'"
```

**Database Performance:**
```bash
# Monitor PostgreSQL connections
docker-compose exec postgres psql -U amc -d amc_platform -c "SELECT count(*) FROM pg_stat_activity;"

# Monitor Redis memory
docker-compose exec redis redis-cli info memory
```

**Application Logs:**
```bash
# Follow critical errors
docker-compose logs -f | grep -i error

# Monitor latency
docker-compose logs -f amc-platform | grep "elapsed_ms"
```

#### 3.3 Validation Checklist

- [ ] All health checks passing
- [ ] Query latency P95 < 3 seconds
- [ ] Feedback submission working
- [ ] Governance batch executed successfully
- [ ] No critical errors in logs (24 hours)
- [ ] Database connections stable
- [ ] Memory usage stable (no leaks)
- [ ] Neo4j query performance acceptable

---

### Phase 4: Traffic Migration (Production Only)

#### 4.1 Setup Load Balancer

```nginx
# /etc/nginx/conf.d/amc-platform.conf

upstream amc_monolithic {
    server localhost:8000 weight=9;  # 90% traffic
}

upstream amc_microservices {
    server localhost:8080 weight=1;  # 10% traffic
}

server {
    listen 80;
    server_name amc-platform.yourcompany.com;
    
    location / {
        # Split traffic between old and new
        proxy_pass http://amc_microservices;
        
        # Fallback to monolithic on error
        proxy_next_upstream error timeout invalid_header http_500;
        proxy_next_upstream_tries 1;
    }
}
```

#### 4.2 Gradual Traffic Shift

**Day 1:** 10% traffic
```bash
# Update nginx config: weight=1 (microservices), weight=9 (monolithic)
sudo nginx -s reload

# Monitor error rates
# If error rate < 1% → proceed
# If error rate > 1% → rollback
```

**Day 2:** 50% traffic
```bash
# Update nginx config: weight=5, weight=5
sudo nginx -s reload
```

**Day 3:** 100% traffic
```bash
# Update nginx config: weight=10, weight=0
sudo nginx -s reload
```

---

### Phase 5: Decommission Monolith

#### 5.1 Final Validation

```bash
# Verify 100% traffic on microservices
docker-compose logs amc-platform | grep "query" | wc -l

# Check monolithic has no traffic
# (old deployment should show zero requests)

# Run full test suite one more time
cd backend
pytest tests/ -v --cov=app
```

#### 5.2 Archive Monolithic Deployment

```bash
# Stop monolithic service
# (Do NOT delete yet - keep for 30 days as rollback insurance)

# Archive code
cd /path/to/monolithic
git tag monolithic-final-$(date +%Y%m%d)
git push --tags

# Archive database
# (Already backed up in Phase 1)

# Document lessons learned
# Update wiki/confluence with migration notes
```

---

## Rollback Procedures

### Emergency Rollback (< 5 minutes)

**Trigger:** Critical error, system unavailable

```bash
# 1. Stop microservices
docker-compose down

# 2. Restore monolithic deployment
cd /path/to/monolithic
docker-compose up -d  # Or systemctl start amc-platform

# 3. Verify health
curl http://localhost:8000/api/health

# 4. Update DNS/load balancer to point to monolithic

# 5. Notify team via Slack/PagerDuty
```

### Data Rollback (if data corruption detected)

```bash
# 1. Stop all services
docker-compose down

# 2. Restore database from backup
cp backend/data.db.backup_YYYYMMDD backend/data.db
# Or for PostgreSQL:
# docker-compose exec postgres psql -U amc -d amc_platform < backup.sql

# 3. Restore Neo4j graph
cd backend
python import_neo4j_dump.py --file=graph_dump_YYYYMMDD.cypher

# 4. Restore FAISS indexes
tar -xzf faiss_indexes_backup_YYYYMMDD.tar.gz

# 5. Restart services
docker-compose up -d
```

---

## Troubleshooting

### Issue 1: Service Won't Start

**Symptoms:** `docker-compose up` fails, container exits immediately

**Solution:**
```bash
# Check logs
docker-compose logs <service-name>

# Common causes:
# - Missing environment variables
# - Database connection failed
# - Port already in use

# Fix environment
nano .env
docker-compose up -d <service-name>
```

### Issue 2: High Latency (> 5s)

**Symptoms:** Queries taking longer than monolithic

**Solution:**
```bash
# Check inter-service latency
docker-compose exec amc-platform curl -w "%{time_total}" http://feedback:8001/api/health
docker-compose exec amc-platform curl -w "%{time_total}" http://repair:8002/api/health

# If > 100ms, check network:
docker network inspect context-engineering_default

# Optimize:
# - Enable HTTP/2 keep-alive (already done)
# - Add Redis caching
# - Increase connection pools
```

### Issue 3: Data Inconsistency

**Symptoms:** Feedback not creating patches, patches not deploying

**Solution:**
```bash
# Verify service communication
cd backend
pytest tests/integration/test_data_consistency_across_services.py -v

# Check logs for errors
docker-compose logs feedback | grep ERROR
docker-compose logs repair | grep ERROR

# Manually test flow:
curl -X POST http://localhost:8001/api/feedback -d '{"session_id":"test",...}'
# Verify patch created:
curl http://localhost:8002/api/patches/pending
```

---

## Post-Migration Checklist

### Day 1
- [ ] All services healthy for 24 hours
- [ ] No critical errors logged
- [ ] Performance meets SLA
- [ ] User feedback: no complaints

### Week 1
- [ ] Governance batch ran successfully (Friday)
- [ ] Feedback loop closed (corrections deployed)
- [ ] Load test passed (50-100 users)
- [ ] Memory usage stable

### Month 1
- [ ] Zero unplanned downtime
- [ ] Cost tracking (infrastructure)
- [ ] Team trained on microservices debugging
- [ ] Documentation updated
- [ ] Monolithic deployment archived

---

## Support & Escalation

**Tier 1:** DevOps team (deployment issues)  
**Tier 2:** Backend team (service errors)  
**Tier 3:** Architecture team (design decisions)

**On-Call Rotation:** See wiki.yourcompany.com/oncall  
**Runbook:** Docs/05-Operations-and-Deployment/runbook.md

---

## Conclusion

Migrating to microservices requires careful planning but enables:
- ✅ Independent service scaling
- ✅ Technology flexibility (different databases per service)
- ✅ Fault isolation (one service failure doesn't crash system)
- ✅ Faster deployments (deploy one service at a time)

**Estimated ROI:** 40% faster feature delivery, 60% fewer production incidents
```

---

### **Step 10.4: Create Deployment Runbook**

Create `Docs/05-Operations-and-Deployment/MICROSERVICES_RUNBOOK.md`:

```markdown
# Microservices Operations Runbook

**Quick Reference for Common Operations**

---

## Daily Operations

### Start Services

```bash
cd context-engineering
docker-compose up -d
docker-compose ps  # Verify all running
```

### Stop Services

```bash
docker-compose down
# Or for graceful shutdown:
docker-compose stop
```

### Restart Single Service

```bash
# Restart feedback service only
docker-compose restart feedback

# Rebuild and restart
docker-compose up -d --build feedback
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f amc-platform

# Last 100 lines
docker-compose logs --tail=100 amc-platform

# Follow errors only
docker-compose logs -f | grep ERROR
```

---

## Monitoring & Alerts

### Health Checks

```bash
# Quick health check all services
curl http://localhost:8000/api/health | jq
curl http://localhost:8001/api/health | jq
curl http://localhost:8002/api/health | jq

# Automated monitoring (run every 5 min)
watch -n 300 "./scripts/health_check_all_services.sh"
```

### Key Metrics to Monitor

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Query P95 Latency | < 3s | > 5s |
| API Error Rate | < 1% | > 5% |
| Database Connections | < 80% | > 90% |
| Memory Usage | < 70% | > 85% |
| Disk Usage | < 75% | > 90% |

### Check Resource Usage

```bash
# Container stats
docker stats

# Database connections
docker-compose exec postgres psql -U amc -d amc_platform \
  -c "SELECT count(*) FROM pg_stat_activity;"

# Redis memory
docker-compose exec redis redis-cli info memory | grep used_memory_human

# Neo4j stats
docker-compose exec neo4j cypher-shell \
  "CALL dbms.queryJmx('org.neo4j:*') YIELD name, attributes"
```

---

## Common Issues & Fixes

### Issue: Service Won't Start

```bash
# Check logs
docker-compose logs <service>

# Common fixes:
# 1. Port conflict
sudo lsof -i :8000  # Check what's using port
# Kill or change port in docker-compose.yml

# 2. Database not ready
# Wait 30s and retry
docker-compose up -d <service>

# 3. Environment variables missing
docker-compose config  # Validate config
```

### Issue: High Memory Usage

```bash
# Check which service
docker stats --no-stream

# Restart heavy service
docker-compose restart <service>

# If persistent, scale down
docker-compose up -d --scale amc-platform=1
```

### Issue: Database Connection Pool Exhausted

```bash
# Check active connections
docker-compose exec postgres psql -U amc -d amc_platform \
  -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Kill idle connections
docker-compose exec postgres psql -U amc -d amc_platform \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
      WHERE state = 'idle' AND state_change < now() - interval '1 hour';"

# Increase pool size in .env:
# DATABASE_POOL_SIZE=50
docker-compose restart <service>
```

### Issue: Circuit Breaker Open

```bash
# Check circuit breaker status
curl http://localhost:8000/api/health | jq '.dependencies'

# Find which service is down
curl http://localhost:8001/api/health  # Feedback
curl http://localhost:8002/api/health  # Repair

# Restart failed service
docker-compose restart <failed-service>

# Circuit should close after 2 successful requests (60s timeout)
```

---

## Maintenance Tasks

### Weekly Tasks

```bash
# Monday: Review logs for errors
docker-compose logs --since=168h | grep -i error > weekly_errors.log

# Wednesday: Check disk space
df -h
docker system df  # Docker disk usage

# Friday: Run governance batch (automatic at 9 AM, but verify)
curl -X POST http://localhost:8002/api/governance/run-batch
```

### Monthly Tasks

```bash
# Backup databases
./scripts/backup_databases.sh

# Prune old Docker images
docker image prune -a --filter "until=720h"  # 30 days

# Rotate logs
docker-compose logs --since=720h > archive/logs_$(date +%Y%m).log
```

### Quarterly Tasks

```bash
# Update dependencies
cd backend
pip install --upgrade -r requirements.txt

# Rebuild images
docker-compose build --no-cache

# Run full test suite
pytest tests/ -v --cov=app

# Performance benchmark
python tests/performance/benchmark_microservices.py
```

---

## Emergency Procedures

### Complete System Failure

```bash
# 1. Stop everything
docker-compose down

# 2. Check system resources
df -h  # Disk
free -h  # Memory
top  # CPU

# 3. Restart infrastructure
docker-compose up -d postgres redis neo4j

# 4. Verify infrastructure
# (wait 30s for services to be ready)

# 5. Restart application
docker-compose up -d amc-platform feedback repair frontend

# 6. Verify
curl http://localhost:8000/api/health
```

### Database Corruption

```bash
# 1. Stop services
docker-compose stop amc-platform feedback repair

# 2. Restore from backup
cp backups/data.db.latest backend/data.db
# Or for PostgreSQL:
docker-compose exec postgres psql -U amc -d amc_platform < backups/latest.sql

# 3. Restart
docker-compose up -d

# 4. Verify data integrity
python scripts/verify_data_integrity.py
```

### Security Incident

```bash
# 1. Isolate affected service
docker-compose stop <compromised-service>

# 2. Review access logs
docker-compose logs <service> | grep -E "401|403|500"

# 3. Rotate secrets
# Update .env with new passwords/tokens
docker-compose up -d --force-recreate

# 4. Notify security team
```

---

## Scaling Operations

### Horizontal Scaling (Multiple Instances)

```bash
# Scale platform service to 3 instances
docker-compose up -d --scale amc-platform=3

# Verify load distribution
docker-compose ps

# Note: Requires load balancer (nginx/haproxy)
```

### Vertical Scaling (More Resources)

```yaml
# Edit docker-compose.yml
services:
  amc-platform:
    deploy:
      resources:
        limits:
          cpus: '2.0'      # Increase from 1.0
          memory: 4G       # Increase from 2G
```

```bash
# Apply changes
docker-compose up -d --force-recreate amc-platform
```

---

## Useful Commands

### Database Operations

```bash
# PostgreSQL shell
docker-compose exec postgres psql -U amc -d amc_platform

# Run SQL file
docker-compose exec -T postgres psql -U amc -d amc_platform < script.sql

# Backup database
docker-compose exec postgres pg_dump -U amc amc_platform > backup_$(date +%Y%m%d).sql

# Restore database
docker-compose exec -T postgres psql -U amc -d amc_platform < backup.sql

# Neo4j Cypher shell
docker-compose exec neo4j cypher-shell -u neo4j -p password

# Redis CLI
docker-compose exec redis redis-cli
```

### Docker Cleanup

```bash
# Remove stopped containers
docker-compose rm -f

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Complete cleanup (CAUTION: deletes data)
docker-compose down -v
```

### Performance Profiling

```bash
# CPU profiling (10 seconds)
docker stats --no-stream

# Memory snapshot
docker-compose exec amc-platform python -c "
import psutil
process = psutil.Process()
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB')
"

# Network latency between services
docker-compose exec amc-platform ping -c 5 feedback
docker-compose exec amc-platform ping -c 5 repair
```

---

## Contact Information

**On-Call Engineer:** See PagerDuty schedule  
**DevOps Team:** devops@yourcompany.com  
**Backend Team:** backend@yourcompany.com  
**Slack Channel:** #amc-platform-ops

**Escalation Matrix:**
1. On-call engineer (immediate)
2. Team lead (< 1 hour)
3. Engineering manager (< 2 hours)
4. CTO (critical only)
```

---

### **Deliverables for Task 10**

- ✅ Comprehensive E2E integration tests (6 test cases)
- ✅ Performance benchmarking suite
- ✅ Migration guide (monolithic → microservices)
- ✅ Operations runbook
- ✅ Troubleshooting procedures
- ✅ Emergency response procedures
- ✅ Scaling guidelines
- ✅ Monitoring best practices

---

## **COMPLETE IMPLEMENTATION PLAN SUMMARY**

### **Timeline: 6-8 Weeks**

| Week | Tasks | Deliverables |
|------|-------|--------------|
| **1-2** | Tasks 1-3 | ONNX GLiNER deployed, Integration validated |
| **3-4** | Task 4-5 | Architecture designed, Feedback package extracted |
| **4-6** | Task 6-7 | Repair package extracted, Platform refactored |
| **6-8** | Tasks 8-10 | Docker composition, Inter-service communication, Testing & documentation |

### **Success Metrics**

| Metric | Target | Current | After Implementation |
|--------|--------|---------|---------------------|
| NER Latency | < 150ms | 9,000-30,000ms | 30-150ms ✅ |
| Query P95 Latency | < 3s | 1.6-1.8s | 1.2-2.0s ✅ |
| Module Independence | 3 services | 1 monolith | 3 independent ✅ |
| Deployment Flexibility | Per-service | All-or-nothing | Independent ✅ |
| Test Coverage | > 80% | ~70% | 85%+ ✅ |
| Documentation | Complete | Partial | Comprehensive ✅ |

### **Risk Mitigation**

| Risk | Mitigation |
|------|------------|
| Service communication overhead | HTTP/2 keep-alive, circuit breakers |
| Data inconsistency | Comprehensive integration tests, transactions |
| Deployment complexity | docker-compose, detailed runbooks |
| Performance regression | Benchmarking suite, load tests |
| Team knowledge gap | Migration guide, training sessions |

---

**This completes the detailed implementation plan for all tasks!** 

The plan is now ready for execution. Would you like me to:
1. Create a summary document
2. Generate a project timeline (Gantt chart format)
3. Create task tickets for your project management tool
4. Something else?