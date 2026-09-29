# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Python 3.12+ compatibility fix: multiprocess.resource_tracker bug where
# _lock._recursion_count() is called on _thread.RLock which has no such attribute in 3.12+.
try:
    import multiprocess.resource_tracker as _rt
    if hasattr(_rt, "ResourceTracker"):
        _orig_stop_locked = _rt.ResourceTracker._stop_locked

        def _safe_stop_locked(self, *args, **kwargs):
            if getattr(self._lock, "_recursion_count", int)() > 1:
                return self._reentrant_call_error()
            if self._fd is None or self._pid is None:
                return
            return _orig_stop_locked(self, *args, **kwargs)

        _rt.ResourceTracker._stop_locked = _safe_stop_locked
except Exception:
    pass
