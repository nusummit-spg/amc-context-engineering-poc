"""Portable local support for Wave 2.5 and Wave 2.6 release tests."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'backend'
if not (BACKEND/'amc_publication/models.py').is_file():
    BACKEND=ROOT/'test_support/baseline/backend'
if BACKEND.is_dir():
    sys.path.insert(0,str(BACKEND))

# An extracted overlay contains new additive modules but uses the historical
# Wave 1.9 package as a test-only import backing. Resolve new submodules from
# the overlay without writing or shadowing production imports in a real repo.
if BACKEND != ROOT/'backend':
    import amc_publication
    addon=ROOT/'backend/amc_publication'
    if addon.is_dir() and str(addon) not in amc_publication.__path__:
        amc_publication.__path__.insert(0,str(addon))
