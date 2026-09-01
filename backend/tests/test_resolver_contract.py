# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Tests for EntityResolver contract, ResolutionResult, and alias lookups."""
from app.api.deps import ALIAS_SEED_PATH
from app.extraction.resolver import EntityResolver, ResolutionResult


def test_resolution_result_behavior():
    resolver = EntityResolver(llm=None, alias_seed_path=ALIAS_SEED_PATH)
    
    # 1. Exact alias match
    res_exact = resolver.resolve_surface_form("Adani")
    assert isinstance(res_exact, ResolutionResult)
    assert bool(res_exact) is True
    assert res_exact.name == "Adani Group"
    assert res_exact.confidence == 1.0
    
    # Can be unpacked like a tuple
    entity, conf = res_exact
    assert entity is not None and entity.name == "Adani Group"
    assert conf == 1.0
    
    # 2. Containment fallback match
    res_contain = resolver.resolve_surface_form("Adani Group exposure across schemes")
    assert bool(res_contain) is True
    assert res_contain.name == "Adani Group"
    assert res_contain.confidence == 0.88
    
    # 3. Unknown entity
    res_unknown = resolver.resolve_surface_form("Completely Unknown Entity 999")
    assert bool(res_unknown) is False
    assert res_unknown.entity is None
    assert res_unknown.confidence == 0.0
