# Detailed Implementation Plan: AMC Context Engineering
## Addressing Chief Architect Concerns & Recommendations

**Date**: September 8, 2026  
**Scope**: All recommended improvements (excluding feedback/repair mechanism - being handled separately)  
**Total Timeline**: 8-9 weeks (Phase 0 → Phase 1 → Phase 2)  
**Team Size**: 3-4 engineers + 1 DevOps

---

## Table of Contents

1. **Phase 0: Pre-Production (8-9 Days)**
2. **Phase 1: Post-Production (1-2 Weeks)**
3. **Phase 2: Scale & Enterprise (Weeks 3-4)**
4. **Technical Implementation Details**
5. **Testing & QA Strategy**
6. **Deployment Checklist**
7. **Monitoring & SLAs**

---

## PHASE 0: Pre-Production (8-9 Days) — BLOCKING

### Goal
Ship production-ready system with all blocking issues resolved.

### Team Allocation
- **Backend Lead**: Multi-round orchestration + scheduler
- **Frontend Lead**: Review queue UI
- **ML Engineer**: NLI evaluator training (parallel)
- **DevOps**: Input validation + rate limiting setup

---

## Task 0.1: Human Review Queue Implementation
**Effort**: 2-3 days  
**Owner**: Frontend Lead + Backend Lead  
**Dependency**: None  
**Blocking**: YES

### 0.1.1 Database Schema
**File**: `backend/app/schemas/review_queue.py` (NEW)

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional, List

class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"

class ReviewReason(str, Enum):
    CONFIDENCE_LOW = "confidence_low"
    HALLUCINATION_DETECTED = "hallucination_detected"
    INCOMPLETE_ANSWER = "incomplete_answer"
    REGULATORY_CONCERN = "regulatory_concern"
    FACTUAL_ERROR = "factual_error"
    OTHER = "other"

class ReviewQueueItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    response_id: str
    query: str
    user_answer: str
    reason: ReviewReason
    confidence_score: float = Field(ge=0, le=1)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_to: Optional[str] = None  # User ID of reviewer
    assigned_at: Optional[datetime] = None
    status: ReviewStatus = ReviewStatus.PENDING
    notes: Optional[str] = None
    resolution_at: Optional[datetime] = None
    priority: int = Field(default=5, ge=1, le=10)  # 1=highest, 10=lowest

class ReviewApproval(BaseModel):
    item_id: str
    verdict: str  # "confirmed", "partially_correct", "needs_correction", "rejected"
    reviewer_notes: str
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    reviewer_id: str
```

### 0.1.2 Database Repository
**File**: `backend/app/db/review_queue_repository.py` (NEW)

```python
from datetime import datetime, timedelta
from typing import List, Optional
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.schemas.review_queue import ReviewQueueItem, ReviewStatus

logger = logging.getLogger("review_queue")

class ReviewQueueRepository:
    def __init__(self, db_client: AsyncIOMotorClient):
        self.db = db_client.amc_db.review_queue
        # Ensure indexes
        self.db.create_index("created_at", expireAfterSeconds=2592000)  # 30-day TTL
        self.db.create_index([("status", 1), ("priority", -1)])
        self.db.create_index("assigned_to")

    async def enqueue(self, item: ReviewQueueItem) -> str:
        """Add item to review queue."""
        result = await self.db.insert_one(item.dict(by_alias=True))
        logger.info(f"Review queued: {item.response_id}, reason: {item.reason}")
        return str(result.inserted_id)

    async def get_pending_for_user(self, user_id: str, limit: int = 20) -> List[ReviewQueueItem]:
        """Get pending reviews assigned to user."""
        cursor = self.db.find({
            "assigned_to": user_id,
            "status": ReviewStatus.PENDING.value
        }).sort([("priority", -1), ("created_at", 1)]).limit(limit)
        
        items = []
        async for doc in cursor:
            items.append(ReviewQueueItem(**doc))
        return items

    async def get_unassigned(self, limit: int = 20) -> List[ReviewQueueItem]:
        """Get unassigned reviews (for assignment UI)."""
        cursor = self.db.find({
            "assigned_to": None,
            "status": ReviewStatus.PENDING.value
        }).sort([("priority", -1), ("created_at", 1)]).limit(limit)
        
        items = []
        async for doc in cursor:
            items.append(ReviewQueueItem(**doc))
        return items

    async def assign_to_user(self, item_id: str, user_id: str) -> bool:
        """Assign review to specific user."""
        result = await self.db.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {
                "assigned_to": user_id,
                "assigned_at": datetime.utcnow()
            }}
        )
        return result.modified_count > 0

    async def approve(self, item_id: str, verdict: str, notes: str, reviewer_id: str):
        """Approve/resolve review."""
        result = await self.db.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {
                "status": ReviewStatus.APPROVED.value,
                "verdict": verdict,
                "notes": notes,
                "resolved_by": reviewer_id,
                "resolved_at": datetime.utcnow()
            }}
        )
        return result.modified_count > 0

    async def reject(self, item_id: str, reason: str, reviewer_id: str):
        """Reject/return to queue."""
        result = await self.db.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {
                "status": ReviewStatus.PENDING.value,
                "assigned_to": None,  # Unassign
                "rejection_reason": reason,
                "rejected_by": reviewer_id,
                "rejected_at": datetime.utcnow()
            }}
        )
        return result.modified_count > 0

    async def get_by_response_id(self, response_id: str) -> Optional[ReviewQueueItem]:
        """Look up review by response ID."""
        doc = await self.db.find_one({"response_id": response_id})
        return ReviewQueueItem(**doc) if doc else None

    async def get_stats(self, time_range_days: int = 7) -> dict:
        """Get review queue statistics."""
        since = datetime.utcnow() - timedelta(days=time_range_days)
        
        stats = await self.db.aggregate([
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "avg_resolution_time": {
                    "$avg": {"$subtract": ["$resolved_at", "$created_at"]}
                }
            }}
        ]).to_list(None)
        
        return {s["_id"]: s for s in stats}
```

### 0.1.3 Backend API Endpoints
**File**: `backend/app/api/routes/review_queue.py` (NEW)

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from app.auth.security import get_current_user
from app.db.review_queue_repository import ReviewQueueRepository
from app.schemas.review_queue import ReviewQueueItem, ReviewStatus, ReviewReason
from app.schemas.auth import User

router = APIRouter(prefix="/api/review-queue", tags=["review"])

def get_review_repo(db) -> ReviewQueueRepository:
    return ReviewQueueRepository(db)

@router.post("/escalate")
async def escalate_answer(
    response_id: str,
    reason: ReviewReason,
    confidence_score: float,
    query: str,
    answer: str,
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Escalate low-confidence answer to review queue."""
    item = ReviewQueueItem(
        response_id=response_id,
        query=query,
        user_answer=answer,
        reason=reason,
        confidence_score=confidence_score,
        metadata={"escalated_by": current_user.id}
    )
    item_id = await repo.enqueue(item)
    return {"item_id": item_id, "status": "queued"}

@router.get("/pending")
async def get_pending_reviews(
    limit: int = Query(20, le=100),
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Get pending reviews assigned to current user."""
    if not current_user.can_review():  # Check permission
        raise HTTPException(status_code=403, detail="Not authorized to review")
    
    items = await repo.get_pending_for_user(current_user.id, limit)
    return {"count": len(items), "items": items}

@router.get("/unassigned")
async def get_unassigned(
    limit: int = Query(20, le=100),
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Get unassigned reviews (for manual assignment)."""
    if not current_user.can_manage_reviews():
        raise HTTPException(status_code=403, detail="Not authorized")
    
    items = await repo.get_unassigned(limit)
    return {"count": len(items), "items": items}

@router.post("/{item_id}/assign")
async def assign_review(
    item_id: str,
    user_id: str,
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Assign review to user."""
    if not current_user.can_manage_reviews():
        raise HTTPException(status_code=403)
    
    success = await repo.assign_to_user(item_id, user_id)
    if not success:
        raise HTTPException(status_code=404)
    return {"status": "assigned"}

@router.post("/{item_id}/approve")
async def approve_review(
    item_id: str,
    verdict: str,  # "confirmed", "partially_correct", "needs_correction"
    notes: str,
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Approve review and record verdict."""
    success = await repo.approve(item_id, verdict, notes, current_user.id)
    if not success:
        raise HTTPException(status_code=404)
    
    # Trigger feedback loop if correction needed
    if verdict == "needs_correction":
        # Enqueue to governance batch
        await trigger_governance_for_item(item_id)
    
    return {"status": "approved", "verdict": verdict}

@router.post("/{item_id}/reject")
async def reject_review(
    item_id: str,
    reason: str,
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Reject/return review to queue."""
    success = await repo.reject(item_id, reason, current_user.id)
    if not success:
        raise HTTPException(status_code=404)
    return {"status": "rejected"}

@router.get("/stats")
async def get_review_stats(
    days: int = Query(7, ge=1, le=90),
    repo: ReviewQueueRepository = Depends(get_review_repo),
    current_user: User = Depends(get_current_user),
):
    """Get review queue statistics."""
    if not current_user.can_manage_reviews():
        raise HTTPException(status_code=403)
    
    stats = await repo.get_stats(days)
    return stats
```

### 0.1.4 Frontend Streamlit UI
**File**: `streamlit_app/review_queue_view.py` (NEW)

```python
import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from typing import List, Dict

def render_review_queue_tab():
    """Render the review queue management interface."""
    
    st.title("📋 Review Queue")
    
    # Tab: My Reviews | All Reviews | Statistics
    tab1, tab2, tab3 = st.tabs(["My Reviews", "All Reviews", "Statistics"])
    
    with tab1:
        render_my_reviews()
    
    with tab2:
        render_all_reviews()
    
    with tab3:
        render_queue_stats()

def render_my_reviews():
    """Show reviews assigned to current user."""
    st.subheader("My Assigned Reviews")
    
    # Fetch pending reviews
    response = requests.get(
        f"{st.session_state.backend_url}/api/review-queue/pending",
        headers={"Authorization": f"Bearer {st.session_state.token}"}
    )
    
    if response.status_code != 200:
        st.error("Failed to fetch reviews")
        return
    
    data = response.json()
    items = data.get("items", [])
    
    if not items:
        st.info("No reviews assigned to you")
        return
    
    # Display each review
    for item in items:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Query**: {item['query']}")
                st.write(f"**Answer**: {item['user_answer'][:200]}...")
                st.write(f"**Reason**: {item['reason']} (Confidence: {item['confidence_score']:.2f})")
                st.write(f"**Created**: {item['created_at']}")
            
            with col2:
                priority_color = "🔴" if item['priority'] <= 3 else "🟡" if item['priority'] <= 6 else "🟢"
                st.write(f"Priority: {priority_color} {item['priority']}/10")
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("✅ Approve", key=f"approve_{item['id']}", use_container_width=True):
                    verdict = st.selectbox(
                        "Verdict",
                        ["confirmed", "partially_correct"],
                        key=f"verdict_{item['id']}"
                    )
                    notes = st.text_area(
                        "Notes",
                        key=f"notes_{item['id']}",
                        placeholder="Any observations?"
                    )
                    
                    if st.button("Submit Approval", key=f"submit_approve_{item['id']}"):
                        approve_response = requests.post(
                            f"{st.session_state.backend_url}/api/review-queue/{item['id']}/approve",
                            json={"verdict": verdict, "notes": notes},
                            headers={"Authorization": f"Bearer {st.session_state.token}"}
                        )
                        
                        if approve_response.status_code == 200:
                            st.success("Review approved!")
                            st.rerun()
                        else:
                            st.error("Failed to approve")
            
            with col2:
                if st.button("❌ Reject", key=f"reject_{item['id']}", use_container_width=True):
                    reason = st.text_area(
                        "Reason for rejection",
                        key=f"reject_reason_{item['id']}"
                    )
                    
                    if st.button("Submit Rejection", key=f"submit_reject_{item['id']}"):
                        reject_response = requests.post(
                            f"{st.session_state.backend_url}/api/review-queue/{item['id']}/reject",
                            json={"reason": reason},
                            headers={"Authorization": f"Bearer {st.session_state.token}"}
                        )
                        
                        if reject_response.status_code == 200:
                            st.info("Review returned to queue")
                            st.rerun()
            
            with col3:
                if st.button("📝 Edit", key=f"edit_{item['id']}", use_container_width=True):
                    st.write("Edit functionality placeholder")

def render_all_reviews():
    """Show all unassigned reviews (for admins)."""
    st.subheader("Unassigned Reviews")
    
    response = requests.get(
        f"{st.session_state.backend_url}/api/review-queue/unassigned",
        headers={"Authorization": f"Bearer {st.session_state.token}"}
    )
    
    if response.status_code != 200:
        st.error("Access denied or fetch failed")
        return
    
    data = response.json()
    items = data.get("items", [])
    
    if not items:
        st.info("No unassigned reviews")
        return
    
    # Convert to DataFrame for display
    df_data = []
    for item in items:
        df_data.append({
            "ID": item["id"][:8],
            "Query": item["query"][:50],
            "Reason": item["reason"],
            "Confidence": f"{item['confidence_score']:.2f}",
            "Priority": item["priority"],
            "Created": item["created_at"]
        })
    
    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True)
    
    # Bulk assign
    st.subheader("Bulk Assignment")
    selected_ids = st.multiselect("Select reviews to assign", [item["id"] for item in items])
    
    if selected_ids:
        assignee = st.selectbox("Assign to user", ["User1", "User2", "User3"])
        
        if st.button("Assign Selected"):
            for item_id in selected_ids:
                requests.post(
                    f"{st.session_state.backend_url}/api/review-queue/{item_id}/assign",
                    json={"user_id": assignee},
                    headers={"Authorization": f"Bearer {st.session_state.token}"}
                )
            st.success(f"Assigned {len(selected_ids)} reviews")
            st.rerun()

def render_queue_stats():
    """Show queue statistics."""
    st.subheader("Review Queue Statistics")
    
    response = requests.get(
        f"{st.session_state.backend_url}/api/review-queue/stats",
        headers={"Authorization": f"Bearer {st.session_state.token}"}
    )
    
    if response.status_code == 200:
        stats = response.json()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            pending = stats.get("pending", {}).get("count", 0)
            st.metric("Pending", pending)
        with col2:
            approved = stats.get("approved", {}).get("count", 0)
            st.metric("Approved", approved)
        with col3:
            rejected = stats.get("rejected", {}).get("count", 0)
            st.metric("Rejected", rejected)
        
        # Time to resolution
        st.write("### Average Resolution Times")
        for status, data in stats.items():
            if "avg_resolution_time" in data:
                avg_ms = data["avg_resolution_time"] / 1000
                st.write(f"{status}: {avg_ms:.1f} seconds")
```

### 0.1.5 Integration into Orchestrator
**File**: `backend/app/retrieval/orchestrator.py` (MODIFIED)

```python
# After synthesis, before returning response:

# Step 9: Review queue escalation
if synthesis.confidence in ["low", "medium"]:
    try:
        from app.db.review_queue_repository import ReviewQueueRepository
        from app.schemas.review_queue import ReviewQueueItem, ReviewReason
        
        repo = ReviewQueueRepository(get_db_client())
        
        # Determine reason
        reason = ReviewReason.CONFIDENCE_LOW if synthesis.confidence == "low" else ReviewReason.INCOMPLETE_ANSWER
        
        item = ReviewQueueItem(
            response_id=req_id,
            query=effective_query,
            user_answer=synthesis.answer,
            reason=reason,
            confidence_score=context.quality_score,
            metadata={
                "intent": intent.query_type.value if intent else "unknown",
                "entities": list(resolved_map.keys()),
                "graph_edges": len(facts)
            }
        )
        
        await repo.enqueue(item)
        logger.info(f"Answer escalated to review queue: {req_id}")
        
        # Add to response metadata
        trace.review_queue_escalated = True
        trace.escalation_reason = reason.value
        
    except Exception as exc:
        logger.warning(f"Failed to escalate to review queue: {exc}")
```

### 0.1.6 Testing
**File**: `backend/test_review_queue.py` (NEW)

```python
import pytest
import asyncio
from app.db.review_queue_repository import ReviewQueueRepository
from app.schemas.review_queue import ReviewQueueItem, ReviewReason

@pytest.fixture
async def repo():
    # Setup test DB
    return ReviewQueueRepository(test_db_client)

@pytest.mark.asyncio
async def test_enqueue_review(repo):
    """Test adding item to queue."""
    item = ReviewQueueItem(
        response_id="test_123",
        query="Test query",
        user_answer="Test answer",
        reason=ReviewReason.CONFIDENCE_LOW,
        confidence_score=0.45
    )
    
    item_id = await repo.enqueue(item)
    assert item_id is not None

@pytest.mark.asyncio
async def test_get_pending_for_user(repo):
    """Test retrieving user's pending reviews."""
    # Setup
    item = ReviewQueueItem(
        response_id="test_456",
        query="Test query",
        user_answer="Test answer",
        reason=ReviewReason.HALLUCINATION_DETECTED,
        confidence_score=0.30
    )
    item_id = await repo.enqueue(item)
    await repo.assign_to_user(item_id, "user_123")
    
    # Test
    pending = await repo.get_pending_for_user("user_123")
    assert len(pending) > 0
    assert pending[0].query == "Test query"

@pytest.mark.asyncio
async def test_approve_review(repo):
    """Test approving a review."""
    item = ReviewQueueItem(
        response_id="test_789",
        query="Test query",
        user_answer="Test answer",
        reason=ReviewReason.FACTUAL_ERROR,
        confidence_score=0.25
    )
    item_id = await repo.enqueue(item)
    
    success = await repo.approve(
        item_id,
        verdict="confirmed",
        notes="Looks good",
        reviewer_id="user_456"
    )
    assert success
```

---

## Task 0.2: NLI (Natural Language Inference) Evaluator
**Effort**: 3 days  
**Owner**: ML Engineer  
**Dependency**: None (parallel to 0.1)  
**Blocking**: YES

### 0.2.1 Model Selection & Training Strategy

**Approach**: Use lightweight fine-tuned BERT model for entailment scoring

```python
# backend/app/evaluation/nli_model_selector.py (NEW)

"""
NLI Model Strategy:
- Primary: BERTweet-base (Vietnamese + English, ~110M params)
- Secondary: DistilBERT (distilled, ~66M params)
- Lightweight: TinyBERT (33M params) for edge deployment

Task: Evaluate if LLM response entails the retrieved context
Labels: ENTAILMENT (0), NEUTRAL (1), CONTRADICTION (2)

Performance targets:
- Accuracy: >85% on held-out test set
- Latency: <200ms per evaluation (batch 16)
- F1 (contradiction class): >90% (important for catching errors)
"""

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
from typing import Tuple
import logging

logger = logging.getLogger("nli_evaluator")

class NLIEvaluator:
    def __init__(self, model_name: str = "bert-base-uncased"):
        """Initialize NLI model."""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=3  # ENTAILMENT, NEUTRAL, CONTRADICTION
        ).to(self.device)
        self.model.eval()
        
        self.label_map = {
            0: "entailment",
            1: "neutral",
            2: "contradiction"
        }
        logger.info(f"NLI evaluator initialized with {model_name} on {self.device}")
    
    @torch.no_grad()
    def evaluate(self, premise: str, hypothesis: str) -> Tuple[str, float]:
        """
        Evaluate if hypothesis is entailed by premise.
        
        Args:
            premise: Retrieved context/evidence
            hypothesis: LLM-generated answer
            
        Returns:
            (label, confidence_score)
            label: "entailment", "neutral", or "contradiction"
            confidence_score: 0-1 probability
        """
        inputs = self.tokenizer(
            premise,
            hypothesis,
            truncation=True,
            max_length=512,
            return_tensors="pt",
            padding=True
        ).to(self.device)
        
        outputs = self.model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1)
        
        label_idx = torch.argmax(probs, dim=-1).item()
        confidence = probs[0][label_idx].item()
        
        label = self.label_map[label_idx]
        
        return label, confidence
    
    @torch.no_grad()
    def batch_evaluate(self, premises: list, hypotheses: list) -> list:
        """Batch evaluate multiple premise-hypothesis pairs."""
        results = []
        for premise, hypothesis in zip(premises, hypotheses):
            label, conf = self.evaluate(premise, hypothesis)
            results.append({"label": label, "confidence": conf})
        return results
```

### 0.2.2 Fine-Tuning Script

**File**: `backend/scripts/finetune_nli_model.py` (NEW)

```python
"""
Fine-tune NLI model on AMC compliance domain.

Dataset: 
- Positive pairs (entailment): Correct answers + context
- Negative pairs (contradiction): Common hallucinations + context
- Neutral pairs: Related but not entailed context

This script generates training data and fine-tunes the model.
"""

import json
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding
)
import torch

# 1. Generate training data
def create_nli_training_data():
    """Create NLI training dataset from known Q&A + hallucinations."""
    
    training_examples = [
        # Format: {premise: context, hypothesis: answer, label: 0=entailment, 1=neutral, 2=contradiction}
        
        # Entailment examples (CORRECT)
        {
            "premise": "SEBI circular specifies minimum AUM of Rs. 10 crore for equity fund launch",
            "hypothesis": "The minimum AUM requirement for launching an equity fund is Rs. 10 crore",
            "label": 0  # entailment
        },
        {
            "premise": "AMCs must maintain solvency ratio of 1.0 as per Regulation 30",
            "hypothesis": "Regulation 30 requires a minimum solvency ratio of 1.0",
            "label": 0
        },
        
        # Contradiction examples (HALLUCINATIONS)
        {
            "premise": "SEBI circular specifies minimum AUM of Rs. 10 crore for equity fund launch",
            "hypothesis": "AMCs can launch equity funds with any AUM amount",
            "label": 2  # contradiction
        },
        {
            "premise": "SEBI prohibits guaranteed returns on mutual fund schemes",
            "hypothesis": "Mutual funds can guarantee returns of 15% per annum",
            "label": 2
        },
        {
            "premise": "Fund manager tenure minimum is 2 years for managing a mutual fund scheme",
            "hypothesis": "Fund managers must have at least 5 years tenure",
            "label": 2
        },
        
        # Neutral examples (NOT RELEVANT)
        {
            "premise": "NSE is the primary stock exchange in India",
            "hypothesis": "Fund managers must follow Section 45 of SEBI Act",
            "label": 1  # neutral
        },
    ]
    
    return training_examples

# 2. Prepare dataset
def prepare_dataset(examples):
    """Convert to HuggingFace dataset format."""
    dataset = Dataset.from_list(examples)
    return dataset

# 3. Tokenization
def tokenize_function(tokenizer, examples):
    return tokenizer(
        examples["premise"],
        examples["hypothesis"],
        truncation=True,
        max_length=512,
        padding=True
    )

# 4. Fine-tuning
def finetune_nli_model():
    """Fine-tune NLI model."""
    
    # Setup
    model_name = "bert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=3
    )
    
    # Create dataset
    examples = create_nli_training_data()
    dataset = prepare_dataset(examples)
    
    # Split
    train_test = dataset.train_test_split(test_size=0.2)
    train_dataset = train_test["train"]
    eval_dataset = train_test["test"]
    
    # Tokenize
    tokenize_fn = lambda ex: tokenize_function(tokenizer, ex)
    train_tokenized = train_dataset.map(tokenize_fn, batched=True)
    eval_tokenized = eval_dataset.map(tokenize_fn, batched=True)
    
    # Training
    training_args = TrainingArguments(
        output_dir="./nli_model",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        num_train_epochs=3,
        weight_decay=0.01,
        eval_strategy="epoch",
        logging_steps=10,
        save_strategy="epoch",
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_tokenized,
        eval_dataset=eval_tokenized,
        data_collator=DataCollatorWithPadding(tokenizer),
    )
    
    # Train
    trainer.train()
    
    # Save
    model.save_pretrained("backend/app/evaluation/nli_model")
    tokenizer.save_pretrained("backend/app/evaluation/nli_model")

if __name__ == "__main__":
    finetune_nli_model()
    print("✅ NLI model fine-tuned and saved")
```

### 0.2.3 Verdict Generation Service
**File**: `backend/app/evaluation/verdict_generator.py` (NEW)

```python
"""
Generate verdicts for feedback items using tiered evaluation.
Tier 0-1: Rule-based + NLI (fast)
Tier 2: LLM judge (expensive)
"""

from enum import Enum
from typing import Dict, Tuple
import logging
from app.evaluation.nli_evaluator import NLIEvaluator

logger = logging.getLogger("verdict_generator")

class Verdict(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CORRECT = "partially_correct"
    NEEDS_CORRECTION = "needs_correction"
    AMBIGUOUS = "ambiguous"

class VerdictGenerator:
    def __init__(self):
        self.nli_evaluator = NLIEvaluator("backend/app/evaluation/nli_model")
        
        # Common error patterns (rule-based tier)
        self.error_patterns = {
            "numeric_mismatch": r"(\d+)\s*(?:%|crore|lakh|percent)",
            "guaranteed_return": r"(guarantee|guaranteed|assured|promise).*\d+%",
            "superseded_circular": r"(superseded|amended|replaced by)",
        }
    
    async def generate_verdict(
        self,
        query: str,
        retrieved_context: str,
        llm_answer: str,
        user_feedback: str,
        confidence_score: float
    ) -> Tuple[Verdict, Dict]:
        """
        Generate verdict using multi-tier evaluation.
        
        Returns:
            (verdict, confidence_dict)
        """
        
        logger.info(f"Generating verdict for response (confidence: {confidence_score:.2f})")
        
        # Tier 0: Rule-based checks
        tier0_result = self._tier0_rule_check(llm_answer, user_feedback)
        if tier0_result["is_definitive"]:
            logger.info(f"Tier 0 (rules) detected: {tier0_result['issue']}")
            return tier0_result["verdict"], tier0_result
        
        # Tier 1: NLI Semantic Entailment
        nli_label, nli_conf = self.nli_evaluator.evaluate(retrieved_context, llm_answer)
        tier1_result = self._tier1_nli_check(nli_label, nli_conf)
        
        if tier1_result["is_definitive"]:
            logger.info(f"Tier 1 (NLI) detected: {nli_label} ({nli_conf:.2f})")
            return tier1_result["verdict"], tier1_result
        
        # Tier 2: Lightweight heuristic (no LLM)
        tier2_result = self._tier2_heuristic(
            query, retrieved_context, llm_answer, confidence_score
        )
        
        return tier2_result["verdict"], tier2_result
    
    def _tier0_rule_check(self, answer: str, feedback: str) -> Dict:
        """Rule-based checks for obvious errors."""
        
        # Check for guaranteed returns claim
        if "guarantee" in answer.lower() and "%" in answer:
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "issue": "Guaranteed return claim detected",
                "tier": 0,
                "confidence": 0.95
            }
        
        # Check if user flagged hallucination
        if "hallucination" in feedback.lower() or "wrong" in feedback.lower():
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "issue": "User flagged as hallucination",
                "tier": 0,
                "confidence": 0.90
            }
        
        return {"is_definitive": False}
    
    def _tier1_nli_check(self, nli_label: str, nli_conf: float) -> Dict:
        """NLI-based semantic checking."""
        
        if nli_label == "contradiction" and nli_conf > 0.85:
            # High-confidence contradiction = error
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "issue": f"NLI contradiction ({nli_conf:.2f})",
                "tier": 1,
                "confidence": nli_conf
            }
        
        elif nli_label == "entailment" and nli_conf > 0.90:
            # High-confidence entailment = correct
            return {
                "is_definitive": True,
                "verdict": Verdict.CONFIRMED,
                "issue": "NLI confirmed entailment",
                "tier": 1,
                "confidence": nli_conf
            }
        
        return {"is_definitive": False}
    
    def _tier2_heuristic(self, query: str, context: str, answer: str, conf: float) -> Dict:
        """Heuristic-based verdict when tiers 0-1 inconclusive."""
        
        # Simple heuristic: if confidence high and no contradictions found
        if conf > 0.75:
            return {
                "verdict": Verdict.CONFIRMED,
                "issue": "Heuristic: high confidence, no contradictions",
                "tier": 2,
                "confidence": conf
            }
        
        elif conf < 0.45:
            return {
                "verdict": Verdict.AMBIGUOUS,
                "issue": "Low confidence, needs human review",
                "tier": 2,
                "confidence": conf
            }
        
        else:
            return {
                "verdict": Verdict.PARTIALLY_CORRECT,
                "issue": "Medium confidence, partial correctness likely",
                "tier": 2,
                "confidence": conf
            }

# Global instance
_verdict_generator = None

def get_verdict_generator() -> VerdictGenerator:
    global _verdict_generator
    if _verdict_generator is None:
        _verdict_generator = VerdictGenerator()
    return _verdict_generator
```

---

## Task 0.3: Background Scheduler Setup
**Effort**: 1 day  
**Owner**: DevOps Lead  
**Dependency**: None  
**Blocking**: YES

### 0.3.1 APScheduler Integration

**File**: `backend/app/tasks/scheduler.py` (NEW)

```python
"""
Background task scheduler for autonomous system monitoring.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime

logger = logging.getLogger("scheduler")

class TaskScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(daemon=True)
        self._setup_tasks()
    
    def _setup_tasks(self):
        """Register all background tasks."""
        
        # Task 1: SEBI RSS Feed Polling (Daily 3 AM UTC)
        self.scheduler.add_job(
            self._poll_sebi_feeds,
            CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="sebi_polling",
            name="SEBI RSS Feed Polling",
            coalesce=True,
            misfire_grace_time=600
        )
        logger.info("Scheduled: SEBI polling at 03:00 UTC daily")
        
        # Task 2: Staleness Detection (Daily 6 AM UTC)
        self.scheduler.add_job(
            self._check_regulatory_staleness,
            CronTrigger(hour=6, minute=0, timezone="UTC"),
            id="staleness_check",
            name="Regulatory Staleness Check",
            coalesce=True,
            misfire_grace_time=600
        )
        logger.info("Scheduled: Staleness check at 06:00 UTC daily")
        
        # Task 3: Governance Batch Processing (Weekly Friday 9 AM UTC)
        self.scheduler.add_job(
            self._process_governance_batch,
            CronTrigger(day_of_week="fri", hour=9, minute=0, timezone="UTC"),
            id="governance_batch",
            name="Governance Batch Processing",
            coalesce=True,
            misfire_grace_time=600
        )
        logger.info("Scheduled: Governance batch at Fri 09:00 UTC")
        
        # Task 4: Cache Maintenance (Daily 2 AM UTC)
        self.scheduler.add_job(
            self._maintain_caches,
            CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="cache_maintenance",
            name="Cache TTL Cleanup",
            coalesce=True,
            misfire_grace_time=600
        )
        logger.info("Scheduled: Cache maintenance at 02:00 UTC daily")
        
        # Task 5: Performance Metrics Aggregation (Hourly)
        self.scheduler.add_job(
            self._aggregate_metrics,
            CronTrigger(minute=0, timezone="UTC"),
            id="metrics_aggregation",
            name="Metrics Aggregation",
            coalesce=True,
            misfire_grace_time=300
        )
        logger.info("Scheduled: Metrics aggregation hourly")
    
    async def _poll_sebi_feeds(self):
        """Poll SEBI RSS feeds for new circulars."""
        try:
            logger.info("Starting SEBI feed polling...")
            from app.engine.sebi_feed_ingester import SEBIFeedIngester
            
            ingester = SEBIFeedIngester()
            new_docs = await ingester.poll_and_ingest()
            
            logger.info(f"✅ SEBI polling complete: {len(new_docs)} new documents ingested")
            
            # Record in metrics
            from app.core.metrics import get_metrics_store
            store = get_metrics_store()
            store.record_background_task("sebi_polling", len(new_docs), status="success")
            
        except Exception as exc:
            logger.error(f"❌ SEBI polling failed: {exc}")
            from app.core.metrics import get_metrics_store
            store = get_metrics_store()
            store.record_background_task("sebi_polling", 0, status="failed", error=str(exc))
    
    async def _check_regulatory_staleness(self):
        """Check for stale regulatory documents."""
        try:
            logger.info("Starting staleness check...")
            from app.engine.staleness_monitor import StalenessMonitor
            
            monitor = StalenessMonitor()
            stale_docs = await monitor.detect_staleness()
            
            if stale_docs:
                logger.warning(f"⚠️  Found {len(stale_docs)} potentially stale documents")
                await self._alert_admins(f"{len(stale_docs)} documents may be stale")
            else:
                logger.info("✅ No staleness detected")
            
            from app.core.metrics import get_metrics_store
            store = get_metrics_store()
            store.record_background_task("staleness_check", len(stale_docs), status="success")
            
        except Exception as exc:
            logger.error(f"❌ Staleness check failed: {exc}")
    
    async def _process_governance_batch(self):
        """Process approved feedback patches."""
        try:
            logger.info("Starting governance batch...")
            from app.tasks.governance_batch import GovernanceBatch
            
            batch = GovernanceBatch()
            processed = await batch.process()
            
            logger.info(f"✅ Governance batch complete: {processed} patches processed")
            
            from app.core.metrics import get_metrics_store
            store = get_metrics_store()
            store.record_background_task("governance_batch", processed, status="success")
            
        except Exception as exc:
            logger.error(f"❌ Governance batch failed: {exc}")
    
    async def _maintain_caches(self):
        """Perform cache maintenance and TTL cleanup."""
        try:
            logger.info("Starting cache maintenance...")
            from app.retrieval.cache import get_semantic_cache
            from app.engine.intent_cache import get_intent_cache
            from app.engine.hyde import get_hyde_cache
            
            semantic_cleaned = await get_semantic_cache().cleanup_expired()
            intent_cleaned = await get_intent_cache().cleanup_expired()
            hyde_cleaned = await get_hyde_cache().cleanup_expired()
            
            total_cleaned = semantic_cleaned + intent_cleaned + hyde_cleaned
            logger.info(f"✅ Cache maintenance: {total_cleaned} entries cleaned")
            
            from app.core.metrics import get_metrics_store
            store = get_metrics_store()
            store.record_background_task("cache_maintenance", total_cleaned, status="success")
            
        except Exception as exc:
            logger.error(f"❌ Cache maintenance failed: {exc}")
    
    async def _aggregate_metrics(self):
        """Aggregate hourly metrics for dashboarding."""
        try:
            from app.core.metrics import get_metrics_store
            
            store = get_metrics_store()
            summary = store.get_hourly_summary()
            
            # Store for dashboard
            await store.persist_hourly_summary(summary)
            
        except Exception as exc:
            logger.error(f"❌ Metrics aggregation failed: {exc}")
    
    async def _alert_admins(self, message: str):
        """Send alert to admins (email, Slack, etc.)."""
        try:
            # Placeholder for notification system
            logger.warning(f"📢 ADMIN ALERT: {message}")
            # TODO: Integrate with Slack/email
        except Exception as exc:
            logger.error(f"Failed to send alert: {exc}")
    
    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("✅ Background scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("✅ Background scheduler stopped")

# Global instance
_scheduler = None

def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
```

### 0.3.2 Integration into Main Application

**File**: `backend/app/main.py` (MODIFIED)

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.tasks.scheduler import get_scheduler
import logging

logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    
    # Startup
    logger.info("🚀 Application startup")
    scheduler = get_scheduler()
    scheduler.start()
    yield
    
    # Shutdown
    logger.info("🛑 Application shutdown")
    scheduler.stop()

app = FastAPI(
    title="AMC Context Engineering",
    version="1.0.0",
    lifespan=lifespan
)

# Rest of application code...
```

---

## Task 0.4: Input Validation & Rate Limiting
**Effort**: 1 day  
**Owner**: Backend Lead  
**Dependency**: None  
**Blocking**: YES

### 0.4.1 Request Validation Schema

**File**: `backend/app/schemas/query.py` (MODIFIED/EXTENDED)

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List
import re

class QueryRequest(BaseModel):
    """Validated query request."""
    
    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="User query (3-1000 chars)"
    )
    
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return (1-100)"
    )
    
    session_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Session ID for multi-turn chat"
    )
    
    enable_hyde: bool = Field(
        default=True,
        description="Enable HyDE expansion"
    )
    
    enable_decomposition: bool = Field(
        default=True,
        description="Enable query decomposition"
    )
    
    @validator('query')
    def validate_query(cls, v):
        """Validate query content."""
        
        # Check for SQL injection patterns
        sql_patterns = [r"DROP\s+TABLE", r"DELETE\s+FROM", r"INSERT\s+INTO", r"UNION\s+SELECT"]
        for pattern in sql_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Invalid query pattern detected")
        
        # Check for script injection
        if "<script>" in v.lower() or "javascript:" in v.lower():
            raise ValueError("Script tags not allowed")
        
        # Ensure it's not just repeated characters
        if len(set(v.lower())) <= 2:  # e.g., "aaaaaaa"
            raise ValueError("Query too repetitive")
        
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        """Validate session ID format."""
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid session ID format")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is the minimum AUM for equity fund launch?",
                "top_k": 5,
                "session_id": "session_abc123"
            }
        }
```

### 0.4.2 Rate Limiting Implementation

**File**: `backend/app/core/rate_limiter.py` (NEW)

```python
"""
Rate limiting and quota management.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import logging
from typing import Dict
from datetime import datetime, timedelta

logger = logging.getLogger("rate_limiter")

# Rate limit: 60 requests per minute per IP
limiter = Limiter(key_func=get_remote_address)

# User-based quotas (premium vs. free)
QUOTA_CONFIG = {
    "free": {
        "queries_per_hour": 10,
        "queries_per_day": 100,
    },
    "premium": {
        "queries_per_hour": 1000,
        "queries_per_day": 10000,
    },
    "enterprise": {
        "queries_per_hour": None,  # Unlimited
        "queries_per_day": None,
    }
}

class UserQuotaTracker:
    def __init__(self):
        self.usage: Dict[str, dict] = {}
    
    def check_quota(self, user_id: str, tier: str) -> tuple[bool, str]:
        """Check if user has reached quota."""
        
        if not user_id in self.usage:
            self.usage[user_id] = {
                "hour_start": datetime.utcnow(),
                "day_start": datetime.utcnow(),
                "hour_count": 0,
                "day_count": 0
            }
        
        quota = QUOTA_CONFIG[tier]
        user_data = self.usage[user_id]
        now = datetime.utcnow()
        
        # Reset hourly counter if needed
        if (now - user_data["hour_start"]).seconds >= 3600:
            user_data["hour_start"] = now
            user_data["hour_count"] = 0
        
        # Reset daily counter if needed
        if (now - user_data["day_start"]).days >= 1:
            user_data["day_start"] = now
            user_data["day_count"] = 0
        
        # Check limits
        if quota["queries_per_hour"]:
            if user_data["hour_count"] >= quota["queries_per_hour"]:
                return False, f"Hourly limit ({quota['queries_per_hour']}) reached"
        
        if quota["queries_per_day"]:
            if user_data["day_count"] >= quota["queries_per_day"]:
                return False, f"Daily limit ({quota['queries_per_day']}) reached"
        
        # Increment counters
        user_data["hour_count"] += 1
        user_data["day_count"] += 1
        
        return True, "OK"

# Global tracker
quota_tracker = UserQuotaTracker()

def check_user_quota(user_id: str, tier: str = "free") -> tuple[bool, str]:
    """Check if user can make another query."""
    return quota_tracker.check_quota(user_id, tier)
```

### 0.4.3 Middleware Integration

**File**: `backend/app/api/middleware.py` (MODIFIED)

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging
from app.core.rate_limiter import check_user_quota

logger = logging.getLogger("middleware")

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting."""
        
        # Skip rate limiting for health/metrics endpoints
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Get user ID from token/session
        user_id = request.headers.get("X-User-ID", "anonymous")
        tier = request.headers.get("X-User-Tier", "free")
        
        # Check quota
        allowed, message = check_user_quota(user_id, tier)
        
        if not allowed:
            logger.warning(f"Rate limit exceeded for {user_id}: {message}")
            return JSONResponse(
                status_code=429,
                content={"error": message, "retry_after": 3600}
            )
        
        response = await call_next(request)
        return response

class ValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Add validation logging."""
        
        # Log request details
        logger.debug(f"[{request.method}] {request.url.path}")
        
        response = await call_next(request)
        return response
```

---

## Task 0.5: Integration Testing & QA
**Effort**: 1-2 days  
**Owner**: QA Lead + Backend Lead  
**Dependency**: All of 0.1-0.4  
**Blocking**: YES (gating production deployment)

### 0.5.1 E2E Test Suite

**File**: `backend/test_phase0_e2e.py` (NEW)

```python
"""
End-to-end tests for Phase 0 features.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import AsyncMock, patch

client = TestClient(app)

class TestReviewQueue:
    """Review queue functionality tests."""
    
    @pytest.fixture
    def auth_headers(self):
        return {
            "Authorization": "Bearer test_token",
            "X-User-ID": "test_user",
            "X-User-Tier": "premium"
        }
    
    def test_escalate_low_confidence_answer(self, auth_headers):
        """Test escalating low-confidence answer."""
        response = client.post(
            "/api/review-queue/escalate",
            json={
                "response_id": "resp_123",
                "reason": "confidence_low",
                "confidence_score": 0.35,
                "query": "What is the minimum AUM?",
                "answer": "Rs. 15 crore (LOW CONFIDENCE)"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "item_id" in response.json()
    
    def test_get_pending_reviews(self, auth_headers):
        """Test fetching pending reviews."""
        response = client.get(
            "/api/review-queue/pending",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "count" in response.json()
        assert "items" in response.json()
    
    def test_approve_review(self, auth_headers):
        """Test approving a review."""
        # First escalate
        escalate_resp = client.post(
            "/api/review-queue/escalate",
            json={
                "response_id": "resp_456",
                "reason": "hallucination_detected",
                "confidence_score": 0.20,
                "query": "Test query",
                "answer": "Guaranteed 20% returns"
            },
            headers=auth_headers
        )
        
        item_id = escalate_resp.json()["item_id"]
        
        # Then approve
        approve_resp = client.post(
            f"/api/review-queue/{item_id}/approve",
            json={
                "verdict": "needs_correction",
                "notes": "Answer claims guaranteed returns (prohibited)"
            },
            headers=auth_headers
        )
        
        assert approve_resp.status_code == 200
        assert approve_resp.json()["verdict"] == "needs_correction"

class TestNLIEvaluator:
    """NLI evaluator tests."""
    
    @pytest.mark.asyncio
    async def test_entailment_detection(self):
        """Test detecting entailment."""
        from app.evaluation.nli_evaluator import NLIEvaluator
        
        evaluator = NLIEvaluator()
        
        premise = "SEBI specifies minimum AUM of Rs. 10 crore for equity fund"
        hypothesis = "The minimum AUM for equity fund is Rs. 10 crore"
        
        label, confidence = evaluator.evaluate(premise, hypothesis)
        
        assert label == "entailment"
        assert confidence > 0.8
    
    @pytest.mark.asyncio
    async def test_contradiction_detection(self):
        """Test detecting contradictions."""
        from app.evaluation.nli_evaluator import NLIEvaluator
        
        evaluator = NLIEvaluator()
        
        premise = "SEBI prohibits guaranteed returns on mutual funds"
        hypothesis = "Mutual funds can guarantee 15% annual returns"
        
        label, confidence = evaluator.evaluate(premise, hypothesis)
        
        assert label == "contradiction"
        assert confidence > 0.75

class TestScheduler:
    """Background scheduler tests."""
    
    @pytest.mark.asyncio
    async def test_scheduler_startup(self):
        """Test scheduler starts correctly."""
        from app.tasks.scheduler import get_scheduler
        
        scheduler = get_scheduler()
        # Verify jobs registered
        jobs = scheduler.scheduler.get_jobs()
        
        assert len(jobs) >= 5  # Should have 5+ background jobs
        job_ids = [j.id for j in jobs]
        assert "sebi_polling" in job_ids
        assert "governance_batch" in job_ids
    
    @pytest.mark.asyncio
    async def test_sebi_polling_job(self):
        """Test SEBI polling job execution."""
        from app.tasks.scheduler import TaskScheduler
        
        scheduler = TaskScheduler()
        
        # Mock the ingester
        with patch('app.tasks.scheduler.SEBIFeedIngester') as mock_ingester:
            mock_ingester.return_value.poll_and_ingest = AsyncMock(
                return_value=["doc1", "doc2", "doc3"]
            )
            
            await scheduler._poll_sebi_feeds()

class TestRateLimiting:
    """Rate limiting tests."""
    
    def test_rate_limit_exceeded(self):
        """Test rate limit enforcement."""
        headers = {
            "X-User-ID": "user_123",
            "X-User-Tier": "free"
        }
        
        # Make multiple requests
        for i in range(11):  # Free tier = 10/hour
            response = client.post(
                "/api/query",
                json={"query": f"Test query {i}"},
                headers=headers
            )
            
            if i < 10:
                assert response.status_code in [200, 400]  # Success or validation error
            else:
                assert response.status_code == 429  # Rate limited

class TestInputValidation:
    """Input validation tests."""
    
    def test_sql_injection_prevention(self):
        """Test SQL injection is blocked."""
        response = client.post(
            "/api/query",
            json={"query": "'; DROP TABLE users; --"}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_script_injection_prevention(self):
        """Test script injection is blocked."""
        response = client.post(
            "/api/query",
            json={"query": "<script>alert('xss')</script>"}
        )
        
        assert response.status_code == 422
    
    def test_valid_query_accepted(self):
        """Test valid queries are accepted."""
        response = client.post(
            "/api/query",
            json={"query": "What is the minimum AUM for equity funds?"}
        )
        
        # Should not fail validation (may fail auth or other reasons)
        assert response.status_code != 422

@pytest.mark.asyncio
async def test_phase0_full_flow():
    """Test full Phase 0 flow end-to-end."""
    
    # 1. Make query
    # 2. Get low-confidence response
    # 3. Escalate to review queue
    # 4. Generate NLI verdict
    # 5. Approve and process
    
    # This is an integration test
    pass
```

### 0.5.2 Production Readiness Checklist

**File**: `PHASE_0_READINESS_CHECKLIST.md` (NEW)

```markdown
# Phase 0: Production Readiness Checklist

## Code Quality
- [ ] All new modules have docstrings
- [ ] Type hints on all functions
- [ ] No TODO/FIXME comments left
- [ ] Linting passes (pylint/black)
- [ ] No hardcoded passwords/secrets

## Testing
- [ ] Unit tests: >85% coverage
- [ ] Integration tests passing
- [ ] E2E tests passing
- [ ] Manual testing completed by QA
- [ ] Load testing: 100 req/s sustained

## Database
- [ ] Indexes created on review_queue table
- [ ] Migrations tested on staging
- [ ] Backup/recovery tested
- [ ] TTL policies configured

## Logging & Monitoring
- [ ] All errors logged with context
- [ ] Metrics collection active
- [ ] Dashboard prepared
- [ ] Alerting rules configured

## Security
- [ ] Input validation passing
- [ ] Rate limiting tested
- [ ] RBAC checks enforced
- [ ] Audit logging active

## Documentation
- [ ] API documentation updated
- [ ] Runbook prepared
- [ ] Rollback procedures documented
- [ ] Team briefing scheduled

## Deployment
- [ ] Staging deployment successful
- [ ] Performance benchmarked
- [ ] Rollback tested
- [ ] Runbook reviewed by ops

## Sign-Off
- [ ] Tech lead approval
- [ ] Product lead approval
- [ ] Ops lead approval
```

---

## Summary: Phase 0 Deliverables

**Total Effort**: 8-9 days (with 3-4 engineer parallelization)

| Task | Effort | Owner | Status |
|------|--------|-------|--------|
| 0.1: Review Queue | 2-3 days | FrontendLead + Backend | ⏳ |
| 0.2: NLI Evaluator | 3 days | ML Engineer | ⏳ (parallel) |
| 0.3: Scheduler | 1 day | DevOps | ⏳ |
| 0.4: Rate Limiting | 1 day | Backend | ⏳ |
| 0.5: Testing & QA | 1-2 days | QA + Backend | ⏳ |

**Output**: Production-ready system ready for deployment

---

# PHASE 1: Post-Production (Week 1-2)

[Continuing with remaining sections...]

Due to length, I'll create this as a separate document. Let me continue with Phase 1 and beyond in the next part.
