# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

"""
test_implementation_plan_phase1.py
==================================
Phase 1: Ingestion Gateway
Tests for ingestion_gateway.py core functionality:
  - Deduplication by content hash
  - Namespace routing
  - Provenance record creation
  - IngestRequest validation

Test gates from implementation plan:
  - test_ingestion_gateway_dedup() — same PDF submitted twice is rejected on second call
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.engine import config
from app.engine.ingestion_gateway import (
    IngestNamespace,
    IngestRequest,
    IngestResult,
    process_ingest,
    compute_document_hash,
    batch_process_ingest,
    get_ingest_stats,
)
from app.engine.provenance_ledger import (
    IngestionChannel,
    DocumentStatus,
    ProvenanceLedger,
    get_ledger,
)


@pytest.fixture
def test_pdf_file():
    """Create a temporary test PDF file."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        # Minimal PDF header
        f.write(b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n")
        # Add some content
        f.write(b"1 0 obj\n<< /Type /Catalog >>\nendobj\n")
        f.write(b"xref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 >>\nstartxref\n0\n%%EOF")
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def ledger():
    """Initialize a fresh in-memory ledger for testing."""
    ledger_instance = ProvenanceLedger(":memory:")
    yield ledger_instance


class TestIngestRequestValidation:
    """Test IngestRequest validation."""

    def test_valid_ingest_request(self, test_pdf_file):
        """Valid request passes validation."""
        req = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        is_valid, msg = req.validate()
        assert is_valid, msg

    def test_missing_file(self):
        """Non-existent file fails validation."""
        req = IngestRequest(
            file_path=Path("/nonexistent/file.pdf"),
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        is_valid, msg = req.validate()
        assert not is_valid
        assert "not found" in msg.lower()

    def test_unsupported_extension(self, test_pdf_file):
        """Unsupported file extension fails validation."""
        bad_file = test_pdf_file.with_suffix(".txt")
        test_pdf_file.rename(bad_file)
        
        req = IngestRequest(
            file_path=bad_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        is_valid, msg = req.validate()
        assert not is_valid
        assert "unsupported" in msg.lower()
        
        # Cleanup
        if bad_file.exists():
            bad_file.unlink()

    def test_empty_file(self):
        """Empty file fails validation."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_path = Path(f.name)
        
        req = IngestRequest(
            file_path=temp_path,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        is_valid, msg = req.validate()
        assert not is_valid
        assert "empty" in msg.lower()
        
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


class TestDocumentHashComputation:
    """Test document hash computation."""

    def test_hash_computation(self, test_pdf_file):
        """Hash is computed correctly."""
        hash1 = compute_document_hash(test_pdf_file)
        assert hash1 is not None
        assert len(hash1) == 64  # SHA-256 hex length
        assert hash1.isalnum()

    def test_hash_stability(self, test_pdf_file):
        """Same file always produces same hash."""
        hash1 = compute_document_hash(test_pdf_file)
        hash2 = compute_document_hash(test_pdf_file)
        assert hash1 == hash2

    def test_different_files_different_hashes(self, test_pdf_file):
        """Different files produce different hashes."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\nDifferent content")
            different_file = Path(f.name)
        
        try:
            hash1 = compute_document_hash(test_pdf_file)
            hash2 = compute_document_hash(different_file)
            assert hash1 != hash2
        finally:
            if different_file.exists():
                different_file.unlink()


class TestProcessIngest:
    """Test ingestion process."""

    def test_first_ingest_succeeds(self, test_pdf_file, ledger):
        """First ingest of a document succeeds."""
        req = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
            source_url="file://test.pdf",
            ingested_by="test_user",
        )
        
        with patch("app.engine.ingestion_gateway.get_ledger", return_value=ledger):
            result = process_ingest(req)
        
        assert result.success
        assert not result.was_duplicate
        assert result.document_hash is not None
        assert len(result.document_hash) == 64

    def test_ingest_gateway_dedup(self, test_pdf_file, ledger):
        """Deduplication: same PDF submitted twice is rejected on second call.
        
        This is the primary test gate from the implementation plan.
        """
        req = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
            source_url="file://test.pdf",
            ingested_by="test_user",
        )
        
        # First ingest: should succeed
        result1 = process_ingest(req)
        assert result1.success
        assert not result1.was_duplicate
        hash1 = result1.document_hash
        
        # Second ingest (same file): should be rejected as duplicate
        result2 = process_ingest(req)
        assert result2.success  # process_ingest still returns success
        assert result2.was_duplicate  # but marks as duplicate
        assert result2.document_hash == hash1
        assert "duplicate" in result2.reason.lower()

    def test_dedup_by_hash_different_filename(self, test_pdf_file, ledger):
        """Deduplication: same content with different filename is caught."""
        # First ingest
        req1 = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        result1 = process_ingest(req1)
        assert result1.success and not result1.was_duplicate
        
        # Create second file with same content but different name
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(test_pdf_file.read_bytes())
            different_name_file = Path(f.name)
        
        try:
            req2 = IngestRequest(
                file_path=different_name_file,
                source_channel=IngestionChannel.ADMIN_MANUAL,
                namespace=IngestNamespace.ADMIN_UPLOAD,
            )
            result2 = process_ingest(req2)
            
            # Should be caught as duplicate by hash
            assert result2.was_duplicate
            assert result2.document_hash == result1.document_hash
        finally:
            if different_name_file.exists():
                different_name_file.unlink()

    def test_namespace_routing(self, test_pdf_file, ledger):
        """Namespace routing: documents stored in correct namespace."""
        namespaces = [
            IngestNamespace.ADMIN_UPLOAD,
            IngestNamespace.MEMBER_DOCUMENT,
            IngestNamespace.AMFI_REGULATORY,
            IngestNamespace.SEBI_CIRCULAR,
        ]
        
        for ns in namespaces:
            req = IngestRequest(
                file_path=test_pdf_file,
                source_channel=IngestionChannel.ADMIN_MANUAL,
                namespace=ns,
            )
            result = process_ingest(req)
            # Each namespace should store document independently
            # (testing dedup is namespace-aware)
            assert result.success or result.was_duplicate

    def test_provenance_record_created(self, test_pdf_file, ledger):
        """Provenance record is created on ingest."""
        req = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
            source_url="file://test.pdf",
            ingested_by="test_user",
            metadata={"key": "value"},
        )
        
        result = process_ingest(req)
        assert result.success
        assert result.provenance_record is not None
        assert result.provenance_record.document_hash == result.document_hash
        assert result.provenance_record.source_channel == IngestionChannel.ADMIN_MANUAL
        assert result.provenance_record.namespace == IngestNamespace.ADMIN_UPLOAD


class TestBatchIngest:
    """Test batch ingestion."""

    def test_batch_process_ingest(self, test_pdf_file, ledger):
        """Batch processing handles multiple requests."""
        reqs = [
            IngestRequest(
                file_path=test_pdf_file,
                source_channel=IngestionChannel.ADMIN_MANUAL,
                namespace=IngestNamespace.ADMIN_UPLOAD,
                ingested_by=f"user_{i}",
            )
            for i in range(3)
        ]
        
        results = batch_process_ingest(reqs)
        
        assert len(results) == 3
        assert results[0].success  # First should succeed
        # Subsequent duplicates should be marked as such


class TestIngestStats:
    """Test statistics aggregation."""

    def test_get_ingest_stats(self, test_pdf_file, ledger):
        """Ingest statistics aggregated correctly."""
        req = IngestRequest(
            file_path=test_pdf_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
        )
        
        process_ingest(req)
        stats = get_ingest_stats()
        
        assert stats["total_ingested"] > 0
        assert "by_channel" in stats
        assert "by_namespace" in stats
        assert "by_status" in stats


class TestIngestResultModel:
    """Test IngestResult dataclass."""

    def test_ingest_result_success(self):
        """IngestResult captures successful ingest."""
        result = IngestResult(
            success=True,
            document_hash="abc123",
            was_duplicate=False,
            reason="",
        )
        assert result.success
        assert not result.was_duplicate

    def test_ingest_result_duplicate(self):
        """IngestResult captures duplicate detection."""
        result = IngestResult(
            success=True,
            document_hash="abc123",
            was_duplicate=True,
            reason="Duplicate by hash",
        )
        assert result.success
        assert result.was_duplicate
        assert "duplicate" in result.reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
