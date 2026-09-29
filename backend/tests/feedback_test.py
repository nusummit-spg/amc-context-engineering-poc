from datetime import datetime, timezone
from feedback_loop import FeedbackLoopConfig, start_feedback_loop
from feedback_loop.adapters import InMemoryDatabaseAdapter, InMemoryEvidenceAdapter
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    IngestionStatus,
    RatingType,
)

# 1. Initialize configuration and adapters
config = FeedbackLoopConfig()
db = InMemoryDatabaseAdapter()
evidence = InMemoryEvidenceAdapter()

feedback_id = "fb_9c4f1a"
session_id = "sess_2201"
response_id = "resp_9c4f1a"

# 2. Seed pre-existing feedback record in host DB
sample_feedback = FeedbackRecord(
    feedback_id=feedback_id,
    session_id=session_id,
    response_id=response_id,
    rating=RatingType.NEGATIVE,
    feedback_type=FeedbackType.INACCURATE,
    source=FeedbackSource.ACTIVE,
    received_at=datetime.now(timezone.utc),
    entity_name="Axis Bluechip Fund",
    notes="The NAV and 3-year return shown is incorrect. NAV should be 150.",
    ingestion_status=IngestionStatus.PENDING,
)
db.seed_feedback(sample_feedback)

# 3. Seed evidence snapshot in host evidence store
sample_snapshot = EvidenceSnapshot(
    response_id=response_id,
    original_query="What is the 3-year return and NAV of Axis Bluechip Fund?",
    response_text="The 3-year return is 12% and the latest NAV is 120.",
    entity_name="Axis Bluechip Fund",
    evidence_selected=[
        EvidenceChunk(
            chunk_id="chk_01",
            value="150.25",
            source_version="v1",
            content="Axis Bluechip Fund NAV 150.25 as of last quarter.",
        )
    ],
)
evidence.seed_snapshot(sample_snapshot)

# 4. Trigger the feedback loop
result = start_feedback_loop(
    feedback_id=feedback_id,
    session_id=session_id,
    response_id=response_id,
    source="active",
    config=config,
    db=db,
    evidence_adapter=evidence,
)

print(f"Pipeline Result: {result}")

# 5. Inspect the generated UnifiedEvaluationRecord
records = db.get_all_unified()
for r in records:
    print(f"Response ID: {r.response_id}")
    print(f"Entry Route: {r.entry_route}")
    print(f"Root Cause:  {r.root_cause}")
    print(f"Severity:    {r.severity}")
    print(f"Status:      {r.lifecycle_status}")