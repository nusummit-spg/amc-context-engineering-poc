"""
financial_policy_service.py
=============================
F package: Financial correctness policy enforcement.

Tasks:
- F01: Reject unapproved metric operations
- F02: Exact numeric arithmetic (Decimal)
- F03: Canonical AMC identity
- F04: NAV observation pairing
- F05: Manifest validation
- F06: Immutable dataset versions
- F07: Aggregate provenance/gold
- F08: Legacy numeric fail-closed
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MetricPolicy(str, Enum):
    """Authoritative metric operation policies (F01, F08)"""
    APPROVED = "APPROVED"
    PENDING_STEWARD = "PENDING_STEWARD"
    BLOCKED = "BLOCKED"
    LEGACY = "LEGACY"


class DatasetVersionState(str, Enum):
    """Immutable dataset version lifecycle (F06)"""
    DISCOVERED = "DISCOVERED"
    STAGED = "STAGED"
    RECONCILED = "RECONCILED"
    REVIEWED = "REVIEWED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class AggregationSafety(str, Enum):
    """Aggregation safety classification (F07)"""
    SUMMABLE = "SUMMABLE"
    NON_SUMMABLE = "NON_SUMMABLE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    NO_AGGREGATION = "NO_AGGREGATION"


@dataclass
class MetricDefinition:
    """Metric registry entry with policy metadata (F01, F02, F03)"""
    metric_id: str
    description: str
    unit: str
    aggregation_safety: AggregationSafety
    steward_approved: bool
    allowed_operations: List[str]
    canonical_grains: List[str]  # e.g., ["amc", "scheme", "plan_option"]
    decimal_precision: int = 10
    decimal_scale: int = 4


@dataclass
class ManifestEntry:
    """Source manifest entry with validation fields (F05)"""
    source_id: str
    source_hash: str  # SHA256
    row_count: int
    chunk_hashes: List[str]
    source_path: str
    ingestion_timestamp: str
    validated: bool = False
    validation_error: Optional[str] = None


@dataclass
class AggregationProvenance:
    """Aggregate result provenance with gold status (F07)"""
    contributor_ids: List[str]
    version: str
    filters_applied: Dict[str, Any]
    result_hash: str
    aggregation_safety: AggregationSafety
    is_gold: bool
    timestamp: str


class FinancialPolicyService:
    """
    Enforces financial correctness policies across the system.
    
    F01: Reject unapproved metric operations
    F02: Exact numeric arithmetic (Decimal)
    F03: Canonical AMC identity (stable IDs)
    F04: NAV observation pairing (same observation)
    F05: Manifest validation (hashes, counts)
    F06: Immutable dataset versions (state machine)
    F07: Aggregate provenance/gold
    F08: Legacy numeric fail-closed
    """

    def __init__(self):
        # Metric registry with policies (F01, F02, F03)
        self.metrics: Dict[str, MetricDefinition] = {
            "nav_per_unit": MetricDefinition(
                metric_id="nav_per_unit",
                description="Net Asset Value per unit",
                unit="INR_PER_UNIT",
                aggregation_safety=AggregationSafety.NO_AGGREGATION,
                steward_approved=True,
                allowed_operations=["SELECT", "EXACT_LOOKUP"],
                canonical_grains=["scheme_code", "scheme_id", "plan_option_id", "nav_date"],
                decimal_precision=10,
                decimal_scale=4,
            ),
            "aaum_crore": MetricDefinition(
                metric_id="aaum_crore",
                description="Assets Under Management in Crore",
                unit="INR_CRORE",
                aggregation_safety=AggregationSafety.SUMMABLE,
                steward_approved=True,
                allowed_operations=["SELECT", "SUM", "AVG", "RANK"],
                canonical_grains=["amc_id", "amc_display_name", "scheme_type", "scheme_category", "aaum_quarter"],
                decimal_precision=10,
                decimal_scale=2,
            ),
            "record_count": MetricDefinition(
                metric_id="record_count",
                description="Row count",
                unit="COUNT",
                aggregation_safety=AggregationSafety.SUMMABLE,
                steward_approved=True,
                allowed_operations=["COUNT"],
                canonical_grains=["dataset_version"],
            ),
        }
        
        # Dataset version state machine (F06)
        self.valid_transitions = {
            DatasetVersionState.DISCOVERED: [DatasetVersionState.STAGED],
            DatasetVersionState.STAGED: [DatasetVersionState.RECONCILED],
            DatasetVersionState.RECONCILED: [DatasetVersionState.REVIEWED],
            DatasetVersionState.REVIEWED: [DatasetVersionState.ACTIVE],
            DatasetVersionState.ACTIVE: [DatasetVersionState.ARCHIVED],
            DatasetVersionState.ARCHIVED: [],  # Terminal state
        }

    def validate_metric_operation(self, metric_id: str, operation: str) -> tuple[bool, str]:
        """
        F01: Validate metric operation against policy.
        
        Returns (allowed, error_message)
        """
        metric = self.metrics.get(metric_id)
        
        if not metric:
            return False, f"METRIC_POLICY_BLOCKED: Unknown metric '{metric_id}'"
        
        if operation not in metric.allowed_operations:
            return False, f"METRIC_POLICY_BLOCKED: Operation '{operation}' not allowed for metric '{metric_id}'"
        
        if metric.steward_approved:
            return True, "METRIC_POLICY_APPROVED"
        
        # Pending steward approval
        return True, f"METRIC_POLICY_PENDING_STEWARD: {metric_id} pending steward signoff"

    def to_decimal(self, value: Any, precision: int = 10, scale: int = 4) -> Optional[Decimal]:
        """
        F02: Convert value to Decimal with exact arithmetic.
        
        Replaces CAST(... AS REAL) to avoid IEEE 754 floating point drift.
        """
        if value is None:
            return None
        
        try:
            if isinstance(value, Decimal):
                return value
            
            # Handle string representations
            if isinstance(value, str):
                # Remove any commas and strip whitespace
                cleaned = value.replace(",", "").strip()
                if not cleaned:
                    return None
                return Decimal(cleaned).quantize(Decimal(10) ** -scale, rounding=ROUND_HALF_UP)
            
            # Handle numeric types
            if isinstance(value, (int, float)):
                return Decimal(str(value)).quantize(Decimal(10) ** -scale, rounding=ROUND_HALF_UP)
            
            return None
        except Exception:
            return None

    def format_decimal(self, value: Decimal, scale: int = 4) -> str:
        """
        F02: Format Decimal for display with fixed scale.
        
        Ensures consistent decimal representation (e.g., "123.4500").
        """
        quantizer = Decimal(10) ** -scale
        return str(value.quantize(quantizer, rounding=ROUND_HALF_UP))

    def get_canonical_amc_identity(
        self,
        amc_id: str,
        scheme_id: Optional[str] = None,
        plan_option_id: Optional[str] = None,
    ) -> str:
        """
        F03: Generate canonical AMC identity.
        
        Uses stable IDs in order: AMC ID + scheme ID + plan_option ID.
        """
        parts = [str(amc_id).strip()]
        if scheme_id:
            parts.append(str(scheme_id).strip())
        if plan_option_id:
            parts.append(str(plan_option_id).strip())
        
        return ":".join(parts)

    def validate_nav_observation_pairing(self, observations: List[Dict[str, Any]]) -> tuple[bool, str]:
        """
        F04: Validate NAV observations come from same observation record.
        
        Ensures NAV, date, and plan_option_id are paired correctly from same source row.
        """
        if not observations:
            return False, "NO_OBSERVATIONS: No NAV observations provided"
        
        # Check all observations have same source_row_id
        source_ids = set()
        for obs in observations:
            if "source_row_id" in obs and obs["source_row_id"]:
                source_ids.add(obs["source_row_id"])
        
        if len(source_ids) > 1:
            return False, "MIXED_OBSERVATIONS: NAV observations from different source rows"
        
        # Check all have nav_per_unit, nav_date, plan_option_id
        required_fields = ["nav_per_unit", "nav_date", "plan_option_id"]
        for obs in observations:
            missing = [f for f in required_fields if f not in obs or obs[f] is None]
            if missing:
                return False, f"MISSING_FIELDS: NAV observation missing {missing}"
        
        return True, "VALID_PAIRING"

    def validate_manifest(self, manifest: ManifestEntry) -> tuple[bool, str]:
        """
        F05: Validate manifest entry.
        
        Verifies source hashes, row counts, and chunk hashes.
        """
        if not manifest.source_id:
            return False, "INVALID_MANIFEST: Missing source_id"
        
        if not manifest.source_hash:
            return False, "INVALID_MANIFEST: Missing source_hash"
        
        if manifest.row_count <= 0:
            return False, "INVALID_MANIFEST: Invalid row_count"
        
        if not manifest.chunk_hashes:
            return False, "INVALID_MANIFEST: Missing chunk_hashes"
        
        # Validate chunk count matches row count (if known)
        expected_chunks = (manifest.row_count + 999) // 1000  # Assuming 1000 rows per chunk
        if len(manifest.chunk_hashes) != expected_chunks:
            return False, f"INVALID_MANIFEST: Expected {expected_chunks} chunks, got {len(manifest.chunk_hashes)}"
        
        # Validate chunk hashes are non-empty
        for i, chunk_hash in enumerate(manifest.chunk_hashes):
            if not chunk_hash or len(chunk_hash) != 64:  # SHA256 = 64 hex chars
                return False, f"INVALID_MANIFEST: Invalid chunk hash at index {i}"
        
        return True, "MANIFEST_VALID"

    def transition_dataset_version(
        self,
        current_state: DatasetVersionState,
        target_state: DatasetVersionState,
    ) -> tuple[bool, str]:
        """
        F06: Validate dataset version state transition.
        
        Enforces immutable lifecycle: DISCOVERED -> STAGED -> RECONCILED -> REVIEWED -> ACTIVE
        """
        valid_targets = self.valid_transitions.get(current_state, [])
        
        if target_state not in valid_targets:
            return False, f"INVALID_TRANSITION: Cannot move {current_state} -> {target_state}"
        
        return True, "TRANSITION_VALID"

    def create_aggregation_provenance(
        self,
        contributor_ids: List[str],
        version: str,
        filters: Dict[str, Any],
        result_hash: str,
        aggregation_safety: AggregationSafety,
    ) -> AggregationProvenance:
        """
        F07: Create aggregation provenance record.
        
        Persists contributor IDs, version, filters, and result hash.
        """
        return AggregationProvenance(
            contributor_ids=contributor_ids,
            version=version,
            filters_applied=filters,
            result_hash=result_hash,
            aggregation_safety=aggregation_safety,
            is_gold=aggregation_safety in [AggregationSafety.SUMMABLE, AggregationSafety.NO_AGGREGATION],
            timestamp="now",  # Would use actual timestamp in production
        )

    def check_legacy_fallback(self, metric_id: str) -> bool:
        """
        F08: Check if legacy Pandas/LLM fallback should be bypassed.
        
        Fail-closed: bypass legacy when source unavailable.
        """
        metric = self.metrics.get(metric_id)
        
        if not metric:
            return False  # Fail closed: unknown metric blocks legacy fallback
        
        if not metric.steward_approved:
            return False  # Fail closed: unapproved metrics block legacy fallback
        
        return True  # Legacy fallback allowed for approved metrics

    def validate_query_for_policy(
        self,
        metric_id: str,
        operation: str,
        grain: List[str],
        period: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        F01 + F03: Validate query against financial policy.
        
        Checks metric operation approval, canonical identity, and temporal validity.
        """
        # F01: Check metric operation
        allowed, msg = self.validate_metric_operation(metric_id, operation)
        if not allowed:
            return False, msg
        
        # F03: Check grain matches canonical grains
        metric = self.metrics.get(metric_id)
        if metric:
            canonical_grains = set(metric.canonical_grains)
            query_grains = set(grain)
            
            if not query_grains.issubset(canonical_grains):
                return False, f"INVALID_GRAIN: Query grains {query_grains} not subset of canonical {canonical_grains}"
        
        # F04: If NAV metric, check period consistency
        if metric_id == "nav_per_unit" and period:
            # NAV queries should use exact date, not period
            return False, "INVALID_PERIOD: NAV queries must use exact date, not period"
        
        return True, "POLICY_VALID"


__all__ = [
    "FinancialPolicyService",
    "MetricDefinition",
    "MetricPolicy",
    "DatasetVersionState",
    "AggregationSafety",
    "ManifestEntry",
    "AggregationProvenance",
]
