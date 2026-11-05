# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_wave13_graph_verification.py
==================================
Wave 1.3 B03: Graph Verification Tests

Verifies that graph mutations write exact values and verification
is recorded with immutable receipts, closing C-11 integrity gate.

Key Properties:
- Graph writes verified by read-back
- Exact value comparison (not just node existence)
- Value mismatches cause PromotionVerificationError
- Immutable receipts stored in graph_mutations table
- Failed verifications never mark proposals as applied
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from app.services.promotion_service import PromotionService
from app.schemas.repair_proposals import RepairProposal
from app.schemas.graph_mutations_table import GraphMutation
from app.exceptions import PromotionVerificationError
from app.core.database import SessionLocal


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = Mock()
    session.query = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    return session


@pytest.fixture
def sample_proposal():
    """Create sample repair proposal."""
    return RepairProposal(
        proposal_id="prop_test_001",
        proposal_type="graph",
        entity_id="INF846K01DP5",
        attribute="ter",
        corrected_value="0.82",
        mutation_cypher="MATCH (s:Scheme {id: $entity_id}) SET s.ter = '0.82'",
        status="approved",
        applied_at=None
    )


def test_b03_exact_value_verification_success(mock_db_session, sample_proposal):
    """
    B03-T01: Graph mutation with exact value match passes verification.
    
    Requirement: C-11 integrity proof
    Gate: Release blocker
    """
    # Setup mock Neo4j driver that returns correct value
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": "0.82"}  # Matches expected
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Execute mutation
    service._execute_graph_mutation(mock_driver, sample_proposal, mock_db_session)
    
    # Verify mutation was logged with success=True
    assert mock_db_session.add.called
    logged_mutation = mock_db_session.add.call_args[0][0]
    assert isinstance(logged_mutation, GraphMutation)
    assert logged_mutation.success is True
    assert logged_mutation.verified_value == "0.82"
    assert logged_mutation.verification_receipt is not None
    assert logged_mutation.verification_receipt["expected_value"] == "0.82"
    assert logged_mutation.verification_receipt["verified_value"] == "0.82"
    assert logged_mutation.verification_receipt["entity_id"] == "INF846K01DP5"
    assert logged_mutation.verification_receipt["attribute"] == "ter"


def test_b03_value_mismatch_raises_error(mock_db_session, sample_proposal):
    """
    B03-T02: Value mismatch between expected and actual raises PromotionVerificationError.
    
    Security Requirement: Silent corruption prevention
    Gate: Release blocker
    """
    # Setup mock Neo4j driver that returns WRONG value
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": "0.79"}  # WRONG! Expected 0.82
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Execute mutation - should raise
    with pytest.raises(PromotionVerificationError) as exc_info:
        service._execute_graph_mutation(mock_driver, sample_proposal, mock_db_session)
    
    assert "value mismatch" in str(exc_info.value).lower()
    assert "0.82" in str(exc_info.value)  # Expected value
    assert "0.79" in str(exc_info.value)  # Actual value
    
    # Verify mutation was logged with success=False
    assert mock_db_session.add.called
    logged_mutation = mock_db_session.add.call_args[0][0]
    assert logged_mutation.success is False
    assert "mismatch" in logged_mutation.error.lower()


def test_b03_node_not_found_after_commit(mock_db_session, sample_proposal):
    """
    B03-T03: Node not found after commit raises PromotionVerificationError.
    
    Security Requirement: Mutation completeness verification
    Gate: Release blocker
    """
    # Setup mock Neo4j driver that cannot find node after commit
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = None  # Node not found!
    
    mock_tx.run.return_value = Mock()
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Execute mutation - should raise
    with pytest.raises(PromotionVerificationError) as exc_info:
        service._execute_graph_mutation(mock_driver, sample_proposal, mock_db_session)
    
    assert "not found" in str(exc_info.value).lower()
    assert "INF846K01DP5" in str(exc_info.value)


def test_b03_verification_receipt_structure(mock_db_session, sample_proposal):
    """
    B03-T04: Verification receipt has required fields and structure.
    
    Audit Requirement: Immutable proof of verification
    Gate: Compliance
    """
    # Setup successful verification
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": "0.82"}
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    service._execute_graph_mutation(mock_driver, sample_proposal, mock_db_session)
    
    # Verify receipt structure
    logged_mutation = mock_db_session.add.call_args[0][0]
    receipt = logged_mutation.verification_receipt
    
    # Required fields
    assert "entity_id" in receipt
    assert "attribute" in receipt
    assert "expected_value" in receipt
    assert "verified_value" in receipt
    assert "verified_at" in receipt
    assert "mutation_id" in receipt
    assert "proposal_id" in receipt
    
    # Verify timestamp is ISO format
    verified_at = receipt["verified_at"]
    assert "T" in verified_at  # ISO format
    assert "Z" in verified_at or "+" in verified_at  # Timezone


def test_b03_numeric_type_normalization(mock_db_session):
    """
    B03-T05: Numeric values are compared correctly regardless of type.
    
    Functional Requirement: Handle Neo4j numeric vs string types
    Gate: Production correctness
    """
    proposal = RepairProposal(
        proposal_id="prop_numeric_001",
        proposal_type="graph",
        entity_id="INF846K01DP5",
        attribute="aum",
        corrected_value="1000.50",  # String representation
        mutation_cypher="MATCH (s:Scheme {id: $entity_id}) SET s.aum = 1000.50",
        status="approved",
        applied_at=None
    )
    
    # Setup mock that returns numeric type
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": 1000.50}  # Numeric type
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Should succeed - string "1000.50" == str(1000.50) == "1000.5"
    # This test documents the type normalization behavior
    service._execute_graph_mutation(mock_driver, proposal, mock_db_session)
    
    logged_mutation = mock_db_session.add.call_args[0][0]
    assert logged_mutation.success is True


def test_b03_null_value_handling(mock_db_session):
    """
    B03-T06: NULL values are handled correctly in verification.
    
    Edge Case: Attribute deletion or NULL assignment
    Gate: Robustness
    """
    proposal = RepairProposal(
        proposal_id="prop_null_001",
        proposal_type="graph",
        entity_id="INF846K01DP5",
        attribute="exit_load",
        corrected_value=None,  # NULL value
        mutation_cypher="MATCH (s:Scheme {id: $entity_id}) REMOVE s.exit_load",
        status="approved",
        applied_at=None
    )
    
    # Setup mock that returns NULL
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": None}
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Should succeed - NULL == NULL
    service._execute_graph_mutation(mock_driver, proposal, mock_db_session)
    
    logged_mutation = mock_db_session.add.call_args[0][0]
    assert logged_mutation.success is True
    assert logged_mutation.verified_value == "None"  # Stringified


def test_b03_verification_failure_does_not_mark_applied(mock_db_session, sample_proposal):
    """
    B03-T07: Verification failure prevents proposal from being marked as applied.
    
    Security Requirement: No phantom APPLIED status
    Gate: Critical - prevents corruption
    """
    # Setup mock that causes verification failure
    mock_driver = Mock()
    mock_session = Mock()
    mock_tx = Mock()
    mock_result = Mock()
    mock_result.single.return_value = {"value": "WRONG_VALUE"}
    
    mock_tx.run.return_value = mock_result
    mock_tx.commit = Mock()
    mock_session.begin_transaction.return_value = mock_tx
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=False)
    mock_driver.session.return_value = mock_session
    
    service = PromotionService(db=mock_db_session)
    
    # Verification should raise, preventing applied_at from being set
    with pytest.raises(PromotionVerificationError):
        service._execute_graph_mutation(mock_driver, sample_proposal, mock_db_session)
    
    # Proposal should remain in 'approved' status (not 'applied')
    assert sample_proposal.status == "approved"
    assert sample_proposal.applied_at is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
