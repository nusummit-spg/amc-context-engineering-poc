# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Custom exception types for AMC Context Engineering."""


class PromotionFailedError(Exception):
    """Raised when promotion of a repair proposal fails."""
    pass


class PromotionVerificationError(Exception):
    """Raised when promotion postcondition read-back verification fails."""
    pass


class RollbackNotImplementedError(Exception):
    """Raised when rollback operation cannot proceed without implementation."""
    pass
