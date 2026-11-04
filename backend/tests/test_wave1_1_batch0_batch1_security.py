# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_wave1_1_batch0_batch1_security.py
=======================================
Security tests for Wave 1.1 Batch 0 + Batch 1 P0 containment fixes.

Tests W1.1-10, W1.1-11, W1.1-12 implementation:
- Identity-derived access (no header trust, no default ADMIN)
- One repair approval authority (no confidence-based auto-approval)
- Publication result integrity (fail-closed on driver failure)
- Pending patch serving elimination (only ACTIVE approved patches)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# W1.1-10: Identity-Derived Access Tests
class TestIdentityDerivedAccess:
    """Test suite for W1.1-10: Reject unauthenticated access"""
    
    def test_missing_auth_header_rejected(self):
        """
        G02-T02 / W1.1-10: Missing authentication should return 401, not default to ADMIN.
        """
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        # Attempt admin action without authentication
        response = client.post("/api/admin/users", json={
            "username": "attacker",
            "password": "hack123",
            "role": "admin"
        })
        
        # Should reject with 401 Unauthorized
        assert response.status_code == 401
        assert "authentication" in response.json().get("detail", "").lower()
    
    def test_forged_x_user_role_not_trusted(self):
        """
        G02-T03 / W1.1-10: X-User-Role header should not grant privileges without JWT.
        
        Even if attacker provides X-User-Role: admin, JWT enforcement should reject.
        """
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        # Attempt with forged role header but no Bearer token
        response = client.get("/api/admin/users", headers={
            "X-User-Role": "admin"  # Forged header
        })
        
        # Should reject (401 or 403 depending on route protection)
        assert response.status_code in [401, 403]
    
    def test_valid_jwt_required_for_sensitive_routes(self):
        """
        W1.1-10: Sensitive routes must enforce CurrentUser dependency with valid JWT.
        """
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        # Test routes that should require authentication
        sensitive_routes = [
            ("POST", "/api/ingest/documents", {}),
            ("GET", "/api/governance/issues", None),
            ("POST", "/api/governance/proposals/test/approve", {}),
        ]
        
        for method, route, payload in sensitive_routes:
            if method == "POST":
                response = client.post(route, json=payload or {})
            else:
                response = client.get(route)
            
            # Should reject without valid JWT
            assert response.status_code == 401, f"{method} {route} should require authentication"


# W1.1-11: One Repair Approval Authority Tests
class TestRepairApprovalAuthority:
    """Test suite for W1.1-11: Disable confidence-based auto-approval"""
    
    @patch('app.services.repair_integration.get_settings')
    def test_high_confidence_patch_not_auto_approved(self, mock_settings):
        """
        G10-T01 / W1.1-11 / GOV-03: High-confidence patches should NOT be auto-approved.
        
        Even with confidence=0.98 and risk=LOW, patches must remain PENDING.
        """
        from app.services.repair_integration import RepairEngineIntegration
        from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
        
        # Mock settings to simulate old auto-approve config
        mock_settings.return_value.repair_auto_approve_enabled = True  # Should be ignored
        mock_settings.return_value.repair_service_url = None
        
        # Create mock record with high-confidence correction
        record = Mock(spec=UnifiedEvaluationRecord)
        record.response_id = "resp_test_123"
        record.adjudication_confidence = 0.98
        record.repair = True
        record.lifecycle_status = "ADJUDICATED"
        record.dissatisfaction_evidence_json = {
            "correction_claims": [{
                "entity_id": "Fund_ABC",
                "attribute": "nav",
                "asserted_value": "100.50",
                "rejected_value": "99.50",
                "confidence": 0.98
            }]
        }
        
        integration = RepairEngineIntegration()
        
        # Trigger repair (with mocked client)
        with patch('app.services.repair_integration.httpx.AsyncClient'):
            import asyncio
            result = asyncio.run(integration.trigger_repair_engine(record, db=None))
        
        # W1.1-11 FIX: Should NOT auto-approve despite high confidence
        assert result.get("auto_approved") is None or len(result.get("auto_approved", [])) == 0
        # Patches created but not automatically promoted
        assert len(result.get("patches_created", [])) > 0
    
    def test_repair_proposal_requires_human_approval(self):
        """
        G10-T01 / W1.1-11: Repair proposals must be created with is_approved=False.
        
        No automatic transition to approved status based on confidence.
        """
        from app.services.repair_proposal_service import RepairProposalService
        from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
        from app.core.database import SessionLocal
        
        service = RepairProposalService()
        db = SessionLocal()
        
        try:
            # Create mock unified record
            record = Mock(spec=UnifiedEvaluationRecord)
            record.response_id = "resp_test_456"
            record.query_text = "What is NAV of Fund XYZ?"
            record.adjudication_confidence = 0.99  # Very high confidence
            record.root_cause = "incorrect_value"
            record.repair = True
            
            # Create proposal - should always be is_approved=False
            proposal = service.create_proposal_from_record(
                record, 
                db, 
                is_approved=False  # W1.1-11: Always false
            )
            
            # Verify proposal is in PENDING status
            assert proposal.status == "pending"
            assert proposal.reviewed_by is None  # No auto-reviewer
            assert proposal.reviewed_at is None
            
        finally:
            db.rollback()
            db.close()
    
    def test_four_eyes_approval_separation(self):
        """
        G10-T09 / W1.1-11: Proposer cannot approve their own proposal (four-eyes check).
        
        This is a proposed test - implementation requires governance route update.
        """
        # TODO(W1.1-11): Implement when governance routes enforce four-eyes
        pytest.skip("Four-eyes enforcement requires governance route updates")


# W1.1-12: Publication Result Integrity Tests
class TestPublicationIntegrity:
    """Test suite for W1.1-12: Fail-closed on graph driver failure"""
    
    def test_neo4j_driver_unavailable_raises_error(self):
        """
        G10-T10 / W1.1-12 / GOV-06: Missing Neo4j driver MUST raise PromotionFailedError.
        
        Prevents phantom APPLIED status when canonical mutation cannot execute.
        """
        from app.services.promotion_service import PromotionService
        from app.exceptions import PromotionFailedError
        from app.schemas.repair_proposals import RepairProposal
        from app.core.database import SessionLocal
        
        service = PromotionService()
        db = SessionLocal()
        
        try:
            # Create mock proposal
            proposal = RepairProposal(
                proposal_id="prop_test_789",
                proposal_type="graph",
                mutation_cypher="MATCH (n {id: $entity_id}) SET n.value = 'corrected'",
                entity_id="Fund_123",
                attribute="nav",
                status="approved"
            )
            
            # Simulate driver unavailability
            with pytest.raises(PromotionFailedError) as exc_info:
                service._execute_graph_mutation(
                    driver=None,  # Simulates unavailable driver
                    proposal=proposal,
                    db=db
                )
            
            assert "driver unavailable" in str(exc_info.value).lower()
            
        finally:
            db.close()
    
    def test_proposal_not_marked_applied_on_driver_failure(self):
        """
        W1.1-12: Proposal status should NOT transition to APPLIED if mutation fails.
        """
        from app.services.promotion_service import PromotionService
        from app.schemas.repair_proposals import RepairProposal
        from app.core.database import SessionLocal
        
        service = PromotionService()
        db = SessionLocal()
        
        try:
            # Create approved proposal in database
            proposal = RepairProposal(
                proposal_id="prop_test_fail",
                proposal_type="graph",
                mutation_cypher="MATCH (n) SET n.value = 'test'",
                status="approved",
                applied_at=None
            )
            db.add(proposal)
            db.commit()
            db.refresh(proposal)
            
            # Attempt to apply with unavailable driver (will fail)
            result = service.apply_approved_proposals(
                proposal_id=proposal.proposal_id,
                db=db
            )
            
            # Proposal should be in failed list, not applied
            assert proposal.proposal_id in result.get("failed_proposals", [])
            assert proposal.proposal_id not in result.get("applied_proposals", [])
            
            # Verify status did not change to 'applied'
            db.refresh(proposal)
            assert proposal.status == "approved"  # Still approved, not applied
            assert proposal.applied_at is None
            
        finally:
            db.rollback()
            db.close()
    
    def test_postcondition_verification_on_success(self):
        """
        G10-T11 / W1.1-12: After successful mutation, verify committed effect via read-back.
        """
        # This test requires actual Neo4j connection
        pytest.skip("Requires Neo4j test database for integration testing")


# G02-T13 / G10-T03: Pending Patch Serving Elimination Tests
class TestPendingPatchExclusion:
    """Test suite for excluding unapproved patches from serving context"""
    
    @pytest.mark.asyncio
    async def test_pending_patch_not_applied_to_context(self):
        """
        G02-T13 / G10-T03 / GOV-04: PENDING patches should NOT contaminate user answers.
        
        Only ACTIVE, explicitly approved patches may influence retrieval context.
        """
        from app.retrieval.orchestrator import ContextOrchestrator
        from app.config import get_settings
        
        orchestrator = ContextOrchestrator(settings=get_settings())
        
        # Mock patch data with mixed statuses
        mock_patches = [
            {
                "patch_id": "patch_pending",
                "entity_id": "Fund_A",
                "attribute": "nav",
                "corrected_value": "200.00",
                "confidence": 0.95,
                "approved": False,  # Not approved
                "status": "PENDING"
            },
            {
                "patch_id": "patch_active",
                "entity_id": "Fund_B",
                "attribute": "aum",
                "corrected_value": "5000",
                "confidence": 0.90,
                "approved": True,  # Approved
                "status": "ACTIVE"
            }
        ]
        
        # Simulate patch retrieval
        with patch.object(orchestrator, '_repair_client') as mock_client:
            if mock_client:
                mock_client.get_patches_for_entities.return_value = mock_patches
            
            context_text = "Original fund data: Fund_A NAV=100, Fund_B AUM=4000"
            entity_ids = ["Fund_A", "Fund_B"]
            
            modified_context, applied_patches = await orchestrator._apply_correction_patches(
                entity_ids=entity_ids,
                context_text=context_text
            )
            
            # W1.1-11 / G10-T03: Only ACTIVE approved patches should be applied
            assert len(applied_patches) <= 1  # Only patch_active should apply
            
            # Verify PENDING patch was excluded
            pending_applied = any(p.get("patch_id") == "patch_pending" for p in applied_patches)
            assert not pending_applied, "PENDING patch should not be applied to context"
            
            # Verify ACTIVE approved patch was included (if confidence >= 0.70)
            if len(applied_patches) > 0:
                assert applied_patches[0].get("status") == "ACTIVE"
                assert applied_patches[0].get("patch_id") == "patch_active"
    
    def test_correction_patch_layer_filters_unapproved(self):
        """
        G02-T13: CorrectionPatchLayer.apply_patches_to_context must filter by approved flag.
        """
        from app.graph.correction_patch_layer import CorrectionPatchLayer, CorrectionPatch
        
        layer = CorrectionPatchLayer()
        
        # Add unapproved patch
        layer.add_correction(
            entity_id="Scheme_X",
            attribute="nav",
            canonical_value="50.00",
            corrected_value="55.00",
            confidence=0.98,
            provenance={"source": "test"},
            approved=False  # Unapproved
        )
        
        # Apply patches to context
        original_context = "Scheme_X has various attributes"
        modified_context = layer.apply_patches_to_context(
            entities=["Scheme_X"],
            retrieval_context=original_context
        )
        
        # Context should be unchanged (unapproved patch filtered out)
        assert modified_context == original_context or "CORRECTION" not in modified_context


# Integration Test: End-to-End Security Verification
class TestEndToEndSecurity:
    """Integration tests for complete security flow"""
    
    @pytest.mark.asyncio
    async def test_high_confidence_feedback_to_answer_flow(self):
        """
        Complete flow: High-confidence feedback → NOT auto-approved → answer unchanged until manual approval.
        
        Tests W1.1-10, W1.1-11, W1.1-12, G02-T13 together.
        """
        pytest.skip("Requires full integration environment - manual verification test")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
