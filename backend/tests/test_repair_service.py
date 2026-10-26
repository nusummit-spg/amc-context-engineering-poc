# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_repair_service.py
======================
Tests for the repair service that bridges unified evaluation records
to the correction patch layer.
"""

import pytest
from typing import Optional
from sqlalchemy.orm import Session
import uuid

from app.core.database import SessionLocal
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.models import EntryRoute, RootCause, Severity, LifecycleStatus, RepairTarget, AdjudicationVerdict
from app.services.repair_service import (
    extract_corrections_from_evidence,
    resolve_entity_id,
    create_patch_from_correction,
    process_unified_record_for_repair_sync,
)


@pytest.fixture
def db():
    """Provide a database session for tests."""
    session = SessionLocal()
    yield session
    # Clean up after test
    try:
        session.rollback()
    except Exception:
        pass
    finally:
        session.close()


@pytest.fixture
def clean_patch_layer():
    """Provide a clean patch layer."""
    layer = get_correction_patch_layer()
    layer.clear_all()
    yield layer
    layer.clear_all()


def create_test_evidence(db: Session, response_id: str, session_id: Optional[str] = None) -> str:
    """Helper to create a QueryEvidence record for a test response."""
    if not session_id:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
    existing_sess = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not existing_sess:
        chat_sess = ChatSession(session_id=session_id, user_id="test_user")
        db.add(chat_sess)
        db.flush()
    evidence = QueryEvidence(
        response_id=response_id,
        session_id=session_id,
        user_id="test_user",
        query_text="Test query",
        retrieval_mode="contextgraph",
        assembled_context_json={"context": "Test context"},
        synthesis_output_json={"response": "Test response"},
    )
    db.add(evidence)
    db.commit()
    return session_id


# ────────────────────────────────────────────────────────────────────────────
# Test 1: Extraction of Corrections
# ────────────────────────────────────────────────────────────────────────────

class TestExtractCorrectionsFromEvidence:
    """Test extraction of corrections from dissatisfaction evidence."""

    def test_extract_from_structured_claims(self):
        """Extract corrections from structured_claims in evidence."""
        evidence = {
            "correction_claims": [
                {
                    "entity_id": "INF846K01DP5",
                    "entity_name": "Axis Liquid Fund",
                    "attribute": "TER",
                    "asserted_value": "0.82",
                    "rejected_value": "0.75",
                    "confidence": 0.92
                }
            ]
        }
        
        corrections = extract_corrections_from_evidence(evidence)
        
        assert len(corrections) == 1
        assert corrections[0]["entity_id"] == "INF846K01DP5"
        assert corrections[0]["attribute"] == "TER"
        assert corrections[0]["asserted_value"] == "0.82"
        assert corrections[0]["confidence"] == 0.92
        assert corrections[0]["source"] == "structured_claim"

    def test_extract_empty_evidence(self):
        """Handle empty or None evidence gracefully."""
        corrections = extract_corrections_from_evidence(None)
        assert corrections == []
        
        corrections = extract_corrections_from_evidence({})
        assert corrections == []

    def test_extract_multiple_corrections(self):
        """Extract multiple corrections from evidence."""
        evidence = {
            "correction_claims": [
                {
                    "entity_id": "INF846K01DP5",
                    "attribute": "TER",
                    "asserted_value": "0.82",
                    "rejected_value": "0.75",
                    "confidence": 0.92
                },
                {
                    "entity_id": "INF846K01DP5",
                    "attribute": "AUM",
                    "asserted_value": "5000",
                    "rejected_value": "4500",
                    "confidence": 0.85
                }
            ]
        }
        
        corrections = extract_corrections_from_evidence(evidence)
        
        assert len(corrections) == 2
        assert corrections[0]["attribute"] == "TER"
        assert corrections[1]["attribute"] == "AUM"


# ────────────────────────────────────────────────────────────────────────────
# Test 2: Patch Creation
# ────────────────────────────────────────────────────────────────────────────

class TestCreatePatchFromCorrection:
    """Test patch creation from corrections."""

    def test_create_patch_with_resolved_entity(self, clean_patch_layer):
        """Create patch when entity ID is already resolved."""
        correction = {
            "entity_id": "INF846K01DP5",
            "entity_name": "Axis Liquid Fund",
            "attribute": "TER",
            "asserted_value": "0.82",
            "rejected_value": "0.75",
            "confidence": 0.92
        }
        
        patch_id = create_patch_from_correction(
            correction,
            response_id="resp_12345"
        )
        
        assert patch_id is not None
        
        # Verify patch was created
        patch = clean_patch_layer.get_correction("INF846K01DP5", "TER")
        assert patch is not None
        assert patch.corrected_value == "0.82"
        assert patch.canonical_value == "0.75"
        assert patch.confidence == 0.92
        assert patch.approved is False

    def test_create_patch_missing_entity(self, clean_patch_layer):
        """Handle correction with missing entity ID."""
        correction = {
            "entity_name": "NonExistent Fund",
            "attribute": "TER",
            "asserted_value": "0.82",
            "confidence": 0.92
        }
        
        # Should return None since entity can't be resolved
        patch_id = create_patch_from_correction(
            correction,
            response_id="resp_12345"
        )
        
        assert patch_id is None

    def test_create_patch_missing_attribute(self, clean_patch_layer):
        """Handle correction with missing attribute."""
        correction = {
            "entity_id": "INF846K01DP5",
            "asserted_value": "0.82",
            "confidence": 0.92
        }
        
        patch_id = create_patch_from_correction(
            correction,
            response_id="resp_12345"
        )
        
        assert patch_id is None

    def test_create_patch_missing_value(self, clean_patch_layer):
        """Handle correction with neither asserted nor rejected value."""
        correction = {
            "entity_id": "INF846K01DP5",
            "attribute": "TER",
            "confidence": 0.92
        }
        
        patch_id = create_patch_from_correction(
            correction,
            response_id="resp_12345"
        )
        
        assert patch_id is None


# ────────────────────────────────────────────────────────────────────────────
# Test 3: Process Unified Records
# ────────────────────────────────────────────────────────────────────────────

class TestProcessUnifiedRecordForRepair:
    """Test the main repair service that processes unified records."""

    def test_process_record_with_repair_flag(self, db: Session, clean_patch_layer):
        """Process a unified record marked for repair."""
        response_id = f"resp_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        # Create QueryEvidence first (required by FK constraint)
        create_test_evidence(db, response_id, session_id)
        
        # Create a unified record
        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.HITL,
            evidence_snapshot_ref=response_id,
            root_cause=RootCause.KNOWLEDGE,
            severity=Severity.HIGH,
            lifecycle_status=LifecycleStatus.OPEN,
            repair=True,
            repair_target=RepairTarget.VECTOR,
            dissatisfaction_evidence_json={
                "correction_claims": [
                    {
                        "entity_id": "INF846K01DP5",
                        "attribute": "TER",
                        "asserted_value": "0.82",
                        "rejected_value": "0.75",
                        "confidence": 0.92
                    }
                ]
            },
            adjudication_verdict=AdjudicationVerdict.VALID,
            adjudication_confidence=0.95
        )
        db.add(record)
        db.commit()
        
        # Process the record
        result = process_unified_record_for_repair_sync(
            response_id=response_id,
            db=db
        )
        
        assert result["success"] is True
        assert result["patches_created"] == 1
        assert len(result["patches"]) == 1

    def test_process_record_without_repair_flag(self, db: Session):
        """Process a unified record not marked for repair."""
        response_id = f"resp_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        # Create QueryEvidence first
        create_test_evidence(db, response_id, session_id)
        
        # Create a unified record without repair flag
        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.AUTOMATIC,
            evidence_snapshot_ref=response_id,
            root_cause=RootCause.RETRIEVAL,
            severity=Severity.MEDIUM,
            lifecycle_status=LifecycleStatus.OPEN,
            repair=False,  # Not flagged for repair
            dissatisfaction_evidence_json={}
        )
        db.add(record)
        db.commit()
        
        # Process the record
        result = process_unified_record_for_repair_sync(
            response_id=response_id,
            db=db
        )
        
        assert result["success"] is True
        assert result["patches_created"] == 0
        assert len(result["patches"]) == 0

    def test_process_nonexistent_record(self, db: Session):
        """Handle processing of a record that doesn't exist."""
        result = process_unified_record_for_repair_sync(
            response_id="resp_nonexistent_12345",
            db=db
        )
        
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert "not found" in result["errors"][0].lower()

    def test_process_record_with_multiple_corrections(self, db: Session, clean_patch_layer):
        """Process a unified record with multiple corrections."""
        response_id = f"resp_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        # Create QueryEvidence first
        create_test_evidence(db, response_id, session_id)
        
        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.HITL,
            evidence_snapshot_ref=response_id,
            root_cause=RootCause.KNOWLEDGE,
            severity=Severity.HIGH,
            lifecycle_status=LifecycleStatus.OPEN,
            repair=True,
            repair_target=RepairTarget.GRAPH,
            dissatisfaction_evidence_json={
                "correction_claims": [
                    {
                        "entity_id": "INF846K01DP5",
                        "attribute": "TER",
                        "asserted_value": "0.82",
                        "rejected_value": "0.75",
                        "confidence": 0.92
                    },
                    {
                        "entity_id": "INF846K01DP5",
                        "attribute": "AUM",
                        "asserted_value": "5000",
                        "rejected_value": "4500",
                        "confidence": 0.88
                    }
                ]
            },
            adjudication_verdict=AdjudicationVerdict.VALID
        )
        db.add(record)
        db.commit()
        
        # Process the record
        result = process_unified_record_for_repair_sync(
            response_id=response_id,
            db=db
        )
        
        assert result["success"] is True
        assert result["patches_created"] == 2
        assert len(result["patches"]) == 2
        
        # Verify both patches exist
        patch1 = clean_patch_layer.get_correction("INF846K01DP5", "TER")
        patch2 = clean_patch_layer.get_correction("INF846K01DP5", "AUM")
        assert patch1 is not None
        assert patch2 is not None


# ────────────────────────────────────────────────────────────────────────────
# Test 4: Integration Tests
# ────────────────────────────────────────────────────────────────────────────

class TestRepairServiceIntegration:
    """Integration tests for the repair service."""

    def test_patch_appears_in_context_retrieval(self, clean_patch_layer):
        """Verify that created patches appear in context retrieval."""
        # Create a patch
        clean_patch_layer.add_correction(
            entity_id="INF846K01DP5",
            attribute="TER",
            canonical_value="0.75",
            corrected_value="0.82",
            confidence=0.92
        )
        
        # Apply patches to context
        context = clean_patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context="Current TER is 0.75%"
        )
        
        assert "[CORRECTION - TER]" in context
        assert "0.82" in context
        assert "⚠️ INSTRUCTION" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
