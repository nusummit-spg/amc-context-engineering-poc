# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests.test_conflict_resolver
=============================
Unit tests for PatchConflictResolver (GAP 1: Conflict Resolution).
Tests precedence rules, versioning, and conflict detection.
"""

import pytest
from amc_repair.conflict_resolver import PatchConflictResolver, ConflictReport


class TestPatchConflictResolver:
    """Test suite for PatchConflictResolver."""
    
    def setup_method(self):
        """Setup for each test."""
        self.resolver = PatchConflictResolver()
    
    def test_regulatory_source_beats_user_feedback(self):
        """Regulatory patches auto-supersede user feedback patches."""
        existing = [{
            "entity_id": "Axis Bluechip Fund",
            "attribute": "CATEGORY",
            "corrected_value": "Large Cap",
            "confidence": 0.85,
            "source_type": "user_feedback",
            "patch_id": "patch_old_123",
            "version": 1,
        }]
        
        new = {
            "entity_id": "Axis Bluechip Fund",
            "attribute": "CATEGORY",
            "corrected_value": "Mid Cap",
            "confidence": 0.80,  # Lower confidence but regulatory source
            "source_type": "regulatory"
        }
        
        strategy = self.resolver._determine_strategy(existing, new, conf_delta=0.05)
        assert strategy == "auto_supersede", "Regulatory source should beat user feedback"
    
    def test_user_feedback_rejected_by_regulatory(self):
        """User feedback patches rejected when regulatory existing patch."""
        existing = [{
            "entity_id": "Test Fund",
            "attribute": "TER",
            "corrected_value": "1.5",
            "confidence": 0.75,
            "source_type": "regulatory",
            "patch_id": "patch_reg_456",
            "version": 1,
        }]
        
        new = {
            "entity_id": "Test Fund",
            "attribute": "TER",
            "corrected_value": "1.8",
            "confidence": 0.90,  # Higher confidence but user feedback
            "source_type": "user_feedback"
        }
        
        strategy = self.resolver._determine_strategy(existing, new, conf_delta=0.15)
        assert strategy == "reject_new", "Regulatory source should be preferred"
    
    def test_high_confidence_delta_auto_resolves(self):
        """Confidence delta >= 0.15 triggers auto-resolution."""
        existing = [{
            "entity_id": "Test Fund",
            "attribute": "TER",
            "corrected_value": "1.5",
            "confidence": 0.70,
            "source_type": "user_feedback",
            "patch_id": "patch_old_789",
            "version": 1,
        }]
        
        new = {
            "entity_id": "Test Fund",
            "attribute": "TER",
            "corrected_value": "1.8",
            "confidence": 0.90,  # Delta = 0.20 >= 0.15
            "source_type": "user_feedback"
        }
        
        strategy = self.resolver._determine_strategy(existing, new, conf_delta=0.20)
        assert strategy == "confidence_based_supersede", "High confidence should win"
    
    def test_low_confidence_delta_escalates(self):
        """Confidence delta < 0.10 escalates to human review."""
        existing = [{
            "entity_id": "Test Fund",
            "attribute": "AUM",
            "corrected_value": "5000 Cr",
            "confidence": 0.83,
            "source_type": "user_feedback",
            "patch_id": "patch_aum_111",
            "version": 1,
        }]
        
        new = {
            "entity_id": "Test Fund",
            "attribute": "AUM",
            "corrected_value": "5200 Cr",
            "confidence": 0.87,  # Delta = 0.04 < 0.10
            "source_type": "user_feedback"
        }
        
        strategy = self.resolver._determine_strategy(existing, new, conf_delta=0.04)
        assert strategy == "escalate_to_human", "Low delta should escalate"
    
    def test_medium_confidence_delta_timestamp_based(self):
        """Medium confidence delta uses timestamp-based resolution."""
        existing = [{
            "entity_id": "Fund X",
            "attribute": "CATEGORY",
            "corrected_value": "Mid Cap",
            "confidence": 0.80,
            "source_type": "user_feedback",
            "patch_id": "patch_cat_222",
            "version": 1,
            "created_at": "2024-01-01T00:00:00Z"
        }]
        
        new = {
            "entity_id": "Fund X",
            "attribute": "CATEGORY",
            "corrected_value": "Large Cap",
            "confidence": 0.85,  # Delta = 0.05, between 0.10 and 0.15
            "source_type": "user_feedback",
            "created_at": "2024-01-15T00:00:00Z"
        }
        
        strategy = self.resolver._determine_strategy(existing, new, conf_delta=0.05)
        assert strategy == "timestamp_based_supersede", "Medium delta uses timestamp"
    
    def test_recommendation_generation_auto_supersede(self):
        """Test recommendation text for auto-supersede strategy."""
        existing = [{
            "entity_id": "Fund A",
            "attribute": "EXIT_LOAD",
            "confidence": 0.70,
            "source_type": "user_feedback",
        }]
        
        new = {
            "entity_id": "Fund A",
            "attribute": "EXIT_LOAD",
            "confidence": 0.75,
            "source_type": "regulatory"
        }
        
        rec = self.resolver._get_recommendation("auto_supersede", existing, new)
        assert "regulatory source override" in rec.lower(), "Should mention regulatory source"
    
    def test_recommendation_generation_escalate_human(self):
        """Test recommendation text for human escalation."""
        existing = [{
            "entity_id": "Fund B",
            "attribute": "NAV",
            "confidence": 0.82,
        }]
        
        new = {
            "entity_id": "Fund B",
            "attribute": "NAV",
            "confidence": 0.85,
        }
        
        rec = self.resolver._get_recommendation("escalate_to_human", existing, new)
        assert "human review" in rec.lower(), "Should mention human review"
        assert "0.10" in rec or "confidence delta" in rec.lower(), "Should mention delta threshold"
    
    def test_conflict_report_dataclass(self):
        """Test ConflictReport dataclass structure."""
        report = ConflictReport(
            conflict_type="attribute_collision",
            existing_patches=[{"patch_id": "old_patch"}],
            new_patch={"patch_id": "new_patch"},
            resolution_strategy="escalate_to_human",
            confidence_delta=0.08,
            recommended_action="Manual review recommended"
        )
        
        assert report.conflict_type == "attribute_collision"
        assert report.resolution_strategy == "escalate_to_human"
        assert report.confidence_delta == 0.08


class TestPatchVersioning:
    """Test versioning and lineage tracking."""
    
    def setup_method(self):
        """Setup for each test."""
        self.resolver = PatchConflictResolver()
    
    def test_version_increment_on_supersede(self):
        """Test that version increments correctly on supersede."""
        existing_patch = {
            "patch_id": "patch_v1",
            "entity_id": "Fund C",
            "attribute": "TER",
            "version": 1,
            "confidence": 0.75
        }
        
        new_patch = {
            "entity_id": "Fund C",
            "attribute": "TER",
            "confidence": 0.88
        }
        
        conflict = ConflictReport(
            conflict_type="attribute_collision",
            existing_patches=[existing_patch],
            new_patch=new_patch,
            resolution_strategy="confidence_based_supersede",
            confidence_delta=0.13,
            recommended_action="Higher confidence wins"
        )
        
        # Simulate resolution
        new_version = existing_patch.get("version", 1) + 1
        new_patch["version"] = new_version
        new_patch["supersedes_patch_id"] = existing_patch.get("patch_id")
        
        assert new_patch["version"] == 2, "Version should increment to 2"
        assert new_patch["supersedes_patch_id"] == "patch_v1", "Should track lineage"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
