# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
exceptions/__init__.py
======================
Custom exception classes for AMC Context Engineering system.
"""

from .promotion_exceptions import (
    PromotionFailedError,
    PromotionVerificationError,
)

__all__ = [
    "PromotionFailedError",
    "PromotionVerificationError",
]
