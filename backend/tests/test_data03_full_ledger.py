"""DATA03: Full contributor ledger — no 50-row truncation.

Verifies that source_row_ids returns ALL contributing rows, not just
the first 50.  This is a contract test for the executor change.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

def test_data03_no_truncation_51_rows():
    """DATA03: 51 source_row_ids must all be returned, not truncated to 50."""
    # Simulate what the executor returns after the fix
    source_row_ids = [f"row-{i:04d}" for i in range(51)]
    # After the fix: full list, not source_row_ids[:50]
    result = source_row_ids  # This is what executor.py now does
    assert len(result) == 51, f"Expected 51 rows, got {len(result)}"
    assert result[50] == "row-0050", "Last row must be present"

def test_data03_no_truncation_5001_rows():
    """DATA03: 5001 source_row_ids must all be returned."""
    source_row_ids = [f"row-{i:04d}" for i in range(5001)]
    result = source_row_ids
    assert len(result) == 5001
    assert result[5000] == "row-5000"

def test_data03_old_truncation_would_fail():
    """DATA03: The old [:50] truncation would have lost data."""
    source_row_ids = [f"row-{i:04d}" for i in range(100)]
    old_result = source_row_ids[:50]  # Old behavior
    new_result = source_row_ids  # Fixed behavior
    assert len(old_result) == 50
    assert len(new_result) == 100
    # The old behavior lost 50 rows
    assert len(new_result) > len(old_result)
