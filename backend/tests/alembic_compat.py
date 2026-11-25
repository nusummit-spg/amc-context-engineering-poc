"""
alembic compatibility shim
==========================
This module provides compatibility shims for importing from the external
alembic package when the local 'alembic' directory shadows it.
"""

import sys
from pathlib import Path

# Find and temporarily remove the local alembic directory from sys.path
backend_dir = Path(__file__).parent.parent
alembic_paths = []

for i, path in enumerate(sys.path):
    p = Path(path)
    if p.name == "alembic" and p.parent == backend_dir:
        alembic_paths.append((i, path))

# Remove local alembic paths (create a copy first to avoid modifying while iterating)
paths_to_remove = list(alembic_paths)
for idx, path in reversed(paths_to_remove):
    sys.path.pop(idx)

# Import from external alembic
try:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
except ImportError:
    MigrationContext = None
    Operations = None

# Restore the original sys.path
for idx, path in alembic_paths:
    sys.path.insert(idx, path)

__all__ = ["MigrationContext", "Operations"]
