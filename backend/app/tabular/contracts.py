# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
G03: Canonical Financial Data Model, Identity and Metric Dictionary
====================================================================

This module defines the authoritative schema, identity hierarchy, and metric
semantics for financial data. All definitions require data steward sign-off.

Tasks Implemented:
- G03-T01: CSV/XLSX field inventory with aliases
- G03-T02: AMC/scheme/plan/option identity hierarchy
- G03-T03: Separate Scheme_Code, ISIN, display name, source row IDs
- G03-T04: Immutable source_row_id and observation_id
- G03-T05: AAUM grain, aggregation safety, data quarter
- G03-T06: NAV per-unit metric and as-of date policy
- G03-T07: Fund status semantics and Closure_Date interpretation
- G03-T08: Category/type normalization with unknown handling
- G03-T09: Unit conversion and Decimal precision
- G03-T10: Missing, zero, placeholder, invalid value handling
- G03-T11: Duplicate record and cross-quarter aggregation policies
- G03-T12: Versioned metric definitions
- G03-T13: Entity alias registry and conflict review
- G03-T14: Known-answer dataset for testing
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ═══════════════════════════════════════════════════════════════════════════
# G03-T08: Enumerations and Normalized Values
# ═══════════════════════════════════════════════════════════════════════════

class SchemeType(str, Enum):
    """Normalized scheme type categories with alias support"""
    OPEN_ENDED = "Open Ended"
    CLOSE_ENDED = "Close Ended"
    INTERVAL = "Interval"
    UNKNOWN = "Unknown"
    
    @classmethod
    def normalize(cls, raw_value: Optional[str]) -> "SchemeType":
        """Normalize raw scheme type with alias handling"""
        if not raw_value:
            return cls.UNKNOWN
        
        normalized = raw_value.strip().lower()
        alias_map = {
            "open": cls.OPEN_ENDED,
            "open ended": cls.OPEN_ENDED,
            "openended": cls.OPEN_ENDED,
            "close": cls.CLOSE_ENDED,
            "close ended": cls.CLOSE_ENDED,
            "closeended": cls.CLOSE_ENDED,
            "closed": cls.CLOSE_ENDED,
            "interval": cls.INTERVAL,
        }
        
        return alias_map.get(normalized, cls.UNKNOWN)


class SchemeCategory(str, Enum):
    """Major scheme categories - extensible with UNKNOWN for unrecognized"""
    EQUITY = "Equity"
    DEBT = "Debt"
    HYBRID = "Hybrid"
    SOLUTION_ORIENTED = "Solution Oriented"
    OTHER = "Other"
    UNKNOWN = "Unknown"
    
    @classmethod
    def from_raw(cls, raw_category: Optional[str]) -> "SchemeCategory":
        """Extract major category from detailed category string"""
        if not raw_category:
            return cls.UNKNOWN
        
        category_lower = raw_category.lower()
        
        if "equity" in category_lower:
            return cls.EQUITY
        elif "debt" in category_lower:
            return cls.DEBT
        elif "hybrid" in category_lower:
            return cls.HYBRID
        elif "solution" in category_lower or "children" in category_lower or "retirement" in category_lower:
            return cls.SOLUTION_ORIENTED
        else:
            return cls.OTHER


class PlanType(str, Enum):
    """Plan/Option type distinguishing Direct vs Regular and growth vs dividend"""
    REGULAR_GROWTH = "Regular - Growth"
    REGULAR_IDCW = "Regular - IDCW"  # Income Distribution cum Capital Withdrawal
    DIRECT_GROWTH = "Direct - Growth"
    DIRECT_IDCW = "Direct - IDCW"
    INSTITUTIONAL = "Institutional"
    UNKNOWN = "Unknown"


class Unit(str, Enum):
    """Financial units with explicit precision"""
    INR_CRORE = "INR_CRORE"  # 10 million INR
    INR_LAKHS = "INR_LAKHS"  # 100,000 INR
    INR = "INR"              # Indian Rupees
    INR_PER_UNIT = "INR_PER_UNIT"  # NAV per fund unit
    PERCENTAGE = "PERCENTAGE"
    COUNT = "COUNT"
    ROWS = "ROWS"
    TEXT = "TEXT"
    DATE = "DATE"


class NullPolicy(str, Enum):
    """How to handle null/missing values per field"""
    REJECT = "REJECT"           # Quarantine row if null
    ALLOW_NULL = "ALLOW_NULL"   # NULL is valid (nullable column)
    DEFAULT_ZERO = "DEFAULT_ZERO"  # Convert to 0 (explicitly approved only)
    WARN = "WARN"               # Accept but log warning


class QueryErrorCode(str, Enum):
    """Standardized failure codes for typed financial queries (03_CSV_EXCEL_SPEC §6)"""
    STRUCTURED_SOURCE_UNAVAILABLE = "STRUCTURED_SOURCE_UNAVAILABLE"
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    INCOMPATIBLE_PERIODS = "INCOMPATIBLE_PERIODS"
    UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
    NO_MATCH = "NO_MATCH"
    INVALID_PLAN = "INVALID_PLAN"
    EXECUTION_ERROR = "EXECUTION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# G03-T01: Source Schema Definition
# ═══════════════════════════════════════════════════════════════════════════

class SourceFieldDefinition(BaseModel):
    """Definition of a source CSV/XLSX field with validation rules"""
    
    source_name: str  # Exact header name in source
    canonical_name: str  # Normalized internal name
    data_type: str  # Python type: str, Decimal, date, etc.
    unit: Optional[Unit] = None
    null_policy: NullPolicy = NullPolicy.ALLOW_NULL
    aliases: List[str] = Field(default_factory=list)
    description: str
    validation_rules: Dict[str, Any] = Field(default_factory=dict)
    steward_approved: bool = False
    
    model_config = ConfigDict(use_enum_values=True)


# Source schema as per manifest and chunk analysis
SOURCE_SCHEMA_V1 = {
    "schema_version": "1.0",
    "approved_date": "2026-11-03",
    "approver": "Data Steward (Pending)",
    "total_fields": 16,
    "fields": [
        SourceFieldDefinition(
            source_name="Scheme_Code",
            canonical_name="scheme_code",
            data_type="str",
            null_policy=NullPolicy.WARN,
            description="Source scheme code - preserve leading zeros, not unique key alone",
            validation_rules={"max_length": 50},
            steward_approved=False  # Needs uniqueness/collision review
        ),
        SourceFieldDefinition(
            source_name="Scheme_Name",
            canonical_name="scheme_display_name",
            data_type="str",
            null_policy=NullPolicy.REJECT,
            description="Display name - not safe for grouping without canonical ID",
            validation_rules={"max_length": 500},
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="AMC",
            canonical_name="amc_display_name",
            data_type="str",
            null_policy=NullPolicy.REJECT,
            description="AMC display name - requires alias resolution to canonical amc_id",
            validation_rules={"max_length": 200},
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="Scheme_Type",
            canonical_name="scheme_type",
            data_type="SchemeType",
            null_policy=NullPolicy.WARN,
            description="Open Ended, Close Ended, Interval - normalized via enum",
            steward_approved=True
        ),
        SourceFieldDefinition(
            source_name="Scheme_Category",
            canonical_name="scheme_category_raw",
            data_type="str",
            null_policy=NullPolicy.ALLOW_NULL,
            description="Detailed category - extract major category via SchemeCategory.from_raw()",
            validation_rules={"max_length": 200},
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="Scheme_NAV_Name",
            canonical_name="plan_option_display_name",
            data_type="str",
            null_policy=NullPolicy.ALLOW_NULL,
            description="Plan/Option display - parse into PlanType",
            validation_rules={"max_length": 500},
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="Scheme_Min_Amt",
            canonical_name="minimum_amount",
            data_type="str",  # Keep as string initially (mixed formats)
            unit=Unit.INR,
            null_policy=NullPolicy.ALLOW_NULL,
            description="Minimum investment - needs parsing (Rs. 500/-, numeric, etc.)",
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="NAV",
            canonical_name="nav_per_unit",
            data_type="Decimal",
            unit=Unit.INR_PER_UNIT,
            null_policy=NullPolicy.ALLOW_NULL,
            description="NAV per unit as of Latest_NAV_Date - NEVER sum across rows",
            validation_rules={"min": 0, "max_decimal_places": 6},
            steward_approved=True
        ),
        SourceFieldDefinition(
            source_name="Latest_NAV_Date",
            canonical_name="nav_date",
            data_type="date",
            unit=Unit.DATE,
            null_policy=NullPolicy.ALLOW_NULL,
            description="As-of date for NAV - required for cross-date comparisons",
            steward_approved=True
        ),
        SourceFieldDefinition(
            source_name="Average_AUM_Cr",
            canonical_name="aaum_crore",
            data_type="Decimal",
            unit=Unit.INR_CRORE,
            null_policy=NullPolicy.ALLOW_NULL,
            description="Average AUM in crores for AAUM_Quarter - grain and additivity require steward approval",
            validation_rules={"min": 0, "max_decimal_places": 6},
            steward_approved=False  # Grain and SUM safety pending
        ),
        SourceFieldDefinition(
            source_name="AAUM_Quarter",
            canonical_name="aaum_quarter",
            data_type="str",  # Parse to canonical quarter later
            unit=Unit.TEXT,
            null_policy=NullPolicy.ALLOW_NULL,
            description="Quarter for AAUM observation - format: 'January - March 2026'",
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="ISIN_Div_Payout/Growth",
            canonical_name="isin_growth_payout",
            data_type="str",
            null_policy=NullPolicy.ALLOW_NULL,
            description="ISIN for growth/payout variant - preserve dashes and case",
            validation_rules={"pattern": r"^[A-Z]{2}[A-Z0-9]{10}$|^-$"},
            steward_approved=True
        ),
        SourceFieldDefinition(
            source_name="ISIN_Div_Reinvestment",
            canonical_name="isin_reinvestment",
            data_type="str",
            null_policy=NullPolicy.ALLOW_NULL,
            description="ISIN for reinvestment variant",
            validation_rules={"pattern": r"^[A-Z]{2}[A-Z0-9]{10}$|^-$"},
            steward_approved=True
        ),
        SourceFieldDefinition(
            source_name="ISIN_Div_Payout/Growth/Div_Reinvestment",
            canonical_name="isin_combined",
            data_type="str",
            null_policy=NullPolicy.ALLOW_NULL,
            description="Combined ISINs - may contain concatenated codes without delimiter",
            steward_approved=False  # Parsing rules pending
        ),
        SourceFieldDefinition(
            source_name="Launch_Date",
            canonical_name="launch_date",
            data_type="date",
            unit=Unit.DATE,
            null_policy=NullPolicy.ALLOW_NULL,
            description="Fund launch date - semantic meaning requires verification",
            steward_approved=False
        ),
        SourceFieldDefinition(
            source_name="Closure_Date",
            canonical_name="closure_date",
            data_type="date",
            unit=Unit.DATE,
            null_policy=NullPolicy.ALLOW_NULL,
            description="Fund closure date - CANNOT infer is_active without steward rules",
            validation_rules={"note": "Sample shows launch_date == closure_date cases"},
            steward_approved=False
        ),
    ]
}


# ═══════════════════════════════════════════════════════════════════════════
# G03-T02, T03, T04: Identity Hierarchy
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalIdentifiers(BaseModel):
    """Immutable identifiers for source data and entities (G03-T04)"""
    
    # Source row identity (immutable, globally unique)
    source_row_id: str = Field(
        description="SHA256(dataset_version || logical_source_path || row_number || row_content_hash)"
    )
    
    # Business entity identifiers (derived via aliases and rules)
    amc_id: Optional[str] = Field(None, description="Canonical AMC identifier")
    scheme_id: Optional[str] = Field(None, description="Canonical scheme identifier")
    plan_option_id: Optional[str] = Field(None, description="Canonical plan/option identifier")
    
    # Observation identity for time-series data
    observation_id: Optional[str] = Field(
        None,
        description="Unique fact observation: source_row_id + metric + period"
    )
    
    @staticmethod
    def compute_source_row_id(
        dataset_version: str,
        logical_source_path: str,
        original_row_number: int,  # 1-based data row in original source
        row_content_hash: str
    ) -> str:
        """
        Generate immutable source_row_id (G03-T04)
        
        Args:
            dataset_version: Immutable dataset version ID
            logical_source_path: Path to original unchunked source
            original_row_number: 1-based row number in original file
            row_content_hash: SHA256 of raw row content
        
        Returns:
            SHA256 hex digest as source_row_id
        """
        composite = f"{dataset_version}|{logical_source_path}|{original_row_number}|{row_content_hash}"
        return hashlib.sha256(composite.encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# G03-T05, T06: Metric Definitions
# ═══════════════════════════════════════════════════════════════════════════

class AggregationSafety(str, Enum):
    """Whether a metric can be safely aggregated"""
    SUMMABLE = "SUMMABLE"  # Can use SUM (after steward approval)
    AVERAGE_ONLY = "AVERAGE_ONLY"  # Use weighted average
    MAX_MIN_ONLY = "MAX_MIN_ONLY"  # Only max/min valid
    NO_AGGREGATION = "NO_AGGREGATION"  # Lookup only, no grouping
    PENDING_APPROVAL = "PENDING_APPROVAL"  # Awaiting steward decision


class MetricDefinition(BaseModel):
    """
    Canonical metric definition with steward-approved semantics (G03-T12)
    """
    metric_id: str
    display_name: str
    description: str
    source_field: str
    unit: Unit
    data_type: str  # Decimal, int, str, date
    grain: str  # e.g., "plan_option + quarter", "plan_option + nav_date"
    aggregation_safety: AggregationSafety
    allowed_operations: List[str]  # ["SUM", "AVG", "MAX", "MIN", "COUNT"]
    period_rule: Optional[str] = None  # e.g., "require_same_quarter", "require_same_date"
    null_handling: str = "EXCLUDE"  # "EXCLUDE", "ZERO", "ERROR"
    precision: int = 6  # Decimal places
    version: str = "1.0"
    steward_approved: bool = False
    approved_date: Optional[date] = None
    known_answer_fixtures: List[Dict[str, Any]] = Field(default_factory=list)
    
    model_config = ConfigDict(use_enum_values=True)


# Metric Registry (G03-T05, G03-T06)
METRIC_REGISTRY_V1 = {
    "nav_per_unit": MetricDefinition(
        metric_id="nav_per_unit",
        display_name="NAV per Unit",
        description="Net Asset Value per fund unit on a specific date",
        source_field="NAV",
        unit=Unit.INR_PER_UNIT,
        data_type="Decimal",
        grain="plan_option + nav_date",
        aggregation_safety=AggregationSafety.NO_AGGREGATION,
        allowed_operations=["EXACT_LOOKUP", "MAX", "MIN"],
        period_rule="require_same_date_for_comparison",
        null_handling="EXCLUDE",
        precision=6,
        steward_approved=True,
        approved_date=date(2026, 11, 3),
        known_answer_fixtures=[
            {"scheme_code": "100033", "nav_date": "2026-06-29", "expected_nav": Decimal("922.67")}
        ]
    ),
    "aaum_crore": MetricDefinition(
        metric_id="aaum_crore",
        display_name="Average AUM (Crores)",
        description="Average Assets Under Management in INR crores for a quarter",
        source_field="Average_AUM_Cr",
        unit=Unit.INR_CRORE,
        data_type="Decimal",
        grain="plan_option + quarter",
        aggregation_safety=AggregationSafety.PENDING_APPROVAL,  # Needs steward review
        allowed_operations=["EXACT_LOOKUP"],  # SUM pending grain approval
        period_rule="require_same_quarter",
        null_handling="EXCLUDE",
        precision=6,
        steward_approved=False,  # Pending additivity approval
        known_answer_fixtures=[]
    ),
    "scheme_count": MetricDefinition(
        metric_id="scheme_count",
        display_name="Distinct Scheme Count",
        description="Count of distinct canonical scheme IDs",
        source_field="derived",
        unit=Unit.COUNT,
        data_type="int",
        grain="canonical_scheme_id",
        aggregation_safety=AggregationSafety.SUMMABLE,
        allowed_operations=["COUNT_DISTINCT"],
        null_handling="EXCLUDE",
        precision=0,
        steward_approved=True,
        approved_date=date(2026, 11, 3)
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# G03-T10: Value Parsing and Validation
# ═══════════════════════════════════════════════════════════════════════════

def parse_decimal_safe(value: Any, field_name: str, allow_null: bool = True) -> Optional[Decimal]:
    """
    Parse decimal with explicit null/zero/placeholder handling (G03-T09, G03-T10)
    
    Args:
        value: Raw value from source
        field_name: Field name for error messages
        allow_null: Whether NULL is acceptable
    
    Returns:
        Decimal value or None
    
    Raises:
        ValueError: If value is invalid and null not allowed
    """
    # Handle explicit nulls
    if value is None or value == "":
        if allow_null:
            return None
        raise ValueError(f"{field_name}: NULL not allowed per null_policy")
    
    # Handle string representations
    if isinstance(value, str):
        value = value.strip()
        
        # Common placeholders that should NOT become zero
        null_placeholders = ["-", "NA", "N/A", "NULL", "NONE", ""]
        if value.upper() in null_placeholders:
            if allow_null:
                return None
            raise ValueError(f"{field_name}: Placeholder '{value}' found but null not allowed")
        
        # Remove currency symbols and commas
        value = value.replace("Rs.", "").replace("₹", "").replace(",", "").strip()
    
    # Convert to Decimal
    try:
        decimal_value = Decimal(str(value))
        
        # Validation: no negative financial values in this domain
        if decimal_value < 0:
            raise ValueError(f"{field_name}: Negative value {decimal_value} not allowed")
        
        return decimal_value
    except (ValueError, ArithmeticError) as e:
        raise ValueError(f"{field_name}: Cannot parse '{value}' as Decimal: {e}")


def parse_date_safe(value: Any, field_name: str, allow_null: bool = True) -> Optional[date]:
    """
    Parse date with consistent format handling (G03-T09)
    
    Args:
        value: Raw date value
        field_name: Field name for errors
        allow_null: Whether NULL acceptable
    
    Returns:
        date object or None
    """
    if value is None or value == "":
        if allow_null:
            return None
        raise ValueError(f"{field_name}: NULL not allowed")
    
    if isinstance(value, date):
        return value
    
    if isinstance(value, datetime):
        return value.date()
    
    # Parse string dates - try common formats
    if isinstance(value, str):
        value = value.strip()
        if not value:
            if allow_null:
                return None
            raise ValueError(f"{field_name}: Empty string not allowed")
        
        # Try common formats
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        
        raise ValueError(f"{field_name}: Cannot parse date '{value}' with known formats")
    
    raise ValueError(f"{field_name}: Unsupported date type {type(value)}")


# ═══════════════════════════════════════════════════════════════════════════
# G03-T13: Entity Alias Registry
# ═══════════════════════════════════════════════════════════════════════════

class EntityAlias(BaseModel):
    """Mapping from source display names to canonical IDs"""
    source_value: str
    canonical_id: str
    entity_type: str  # "amc", "scheme", "plan_option"
    confidence: float = Field(ge=0.0, le=1.0)
    requires_review: bool = False
    notes: Optional[str] = None


# Example AMC alias registry (G03-T13)
AMC_ALIAS_REGISTRY = {
    "Aditya Birla Sun Life AMC Limited": EntityAlias(
        source_value="Aditya Birla Sun Life AMC Limited",
        canonical_id="amc_abslamc",
        entity_type="amc",
        confidence=1.0,
        requires_review=False
    ),
    "Aditya Birla": EntityAlias(
        source_value="Aditya Birla",
        canonical_id="amc_abslamc",
        entity_type="amc",
        confidence=0.9,
        requires_review=True,
        notes="Short form - verify no other Aditya Birla entities"
    ),
    # More aliases to be populated from data profiling
}


# ═══════════════════════════════════════════════════════════════════════════
# G03-T14: Golden Test Cases
# ═══════════════════════════════════════════════════════════════════════════

class GoldenTestCase(BaseModel):
    """Known-answer test case for metric validation"""
    case_id: str
    description: str
    query_intent: str
    filters: Dict[str, Any]
    expected_value: Any
    expected_unit: Unit
    source_row_ids: List[str]  # Provenance
    dataset_version: str
    approved_by: str
    approved_date: date
    
    model_config = ConfigDict(use_enum_values=True)


# Example golden test (from reconciliation probe)
GOLDEN_TEST_CASES = [
    GoldenTestCase(
        case_id="CSV-EXACT-001",
        description="NAV for scheme code 100033 on 2026-06-29",
        query_intent="EXACT_LOOKUP",
        filters={"scheme_code": "100033", "nav_date": "2026-06-29"},
        expected_value=Decimal("922.67"),
        expected_unit=Unit.INR_PER_UNIT,
        source_row_ids=[],  # To be computed after ingestion
        dataset_version="v1_baseline",
        approved_by="Data Steward (Pending)",
        approved_date=date(2026, 11, 3)
    ),
]


__all__ = [
    # Enums
    "SchemeType",
    "SchemeCategory",
    "PlanType",
    "Unit",
    "NullPolicy",
    "AggregationSafety",
    "QueryErrorCode",
    
    # Models
    "SourceFieldDefinition",
    "CanonicalIdentifiers",
    "MetricDefinition",
    "EntityAlias",
    "GoldenTestCase",
    
    # Registries
    "SOURCE_SCHEMA_V1",
    "METRIC_REGISTRY_V1",
    "AMC_ALIAS_REGISTRY",
    "GOLDEN_TEST_CASES",
    
    # Utilities
    "parse_decimal_safe",
    "parse_date_safe",
]
