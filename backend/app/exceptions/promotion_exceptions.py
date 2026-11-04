# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
promotion_exceptions.py
=======================
Exception classes for repair promotion and publication integrity.

Part of W1.1-12: Publication result integrity & rollback (P0)
"""


class PromotionFailedError(Exception):
    """
    Raised when promotion cannot proceed due to infrastructure or precondition failure.
    
    Examples:
    - Neo4j driver unavailable
    - Required data plane not initialized
    - Base version mismatch (optimistic concurrency conflict)
    - Precondition check failure
    
    This exception MUST prevent proposal status from transitioning to APPLIED.
    """
    pass


class PromotionVerificationError(Exception):
    """
    Raised when postcondition verification fails after transaction commit.
    
    Examples:
    - Expected value not found after mutation
    - Read-back shows different value than expected
    - Required index/cache update failed
    
    This exception triggers rollback and quarantine of the proposal.
    """
    pass
