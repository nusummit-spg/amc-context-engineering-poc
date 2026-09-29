"""
Unit tests for amc-repair-engine package.
"""
import pytest
from amc_repair import RepairEngine, RepairConfig, MemoryCacheAdapter, MemoryGraphAdapter

@pytest.mark.asyncio
async def test_patch_lifecycle_and_context_healing():
    config = RepairConfig()
    cache = MemoryCacheAdapter()
    graph = MemoryGraphAdapter()
    engine = RepairEngine(config=config, cache_adapter=cache, graph_adapter=graph)

    # 1. Create provisional patch
    patch = await engine.patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="TER",
        corrected_value="0.82",
        original_value="0.79",
        confidence=0.98,
        source="feedback",
        auto_approve=False
    )
    assert patch.approved is False
    assert patch.attribute == "TER"

    # Verify pending
    pending = await engine.patch_layer.get_all_pending()
    assert len(pending) == 1

    # 2. Run governance batch
    report = await engine.governance.run_batch(dry_run=False)
    assert report.approved == 1
    assert report.promoted_to_graph == 1

    # Verify graph updated
    updated_ter = await graph.get_entity_property("INF846K01DP5", "TER")
    assert updated_ter == "0.82"

    # 3. Verify context injection
    raw_context = "Axis Bluechip Fund has TER 0.79%."
    healed = await engine.patch_layer.apply_patches_to_context(["INF846K01DP5"], raw_context)
    assert "0.82" in healed
    assert "[CORRECTION PATCH APPLIED" in healed

    await engine.close()

@pytest.mark.asyncio
async def test_tiered_evaluator():
    config = RepairConfig()
    engine = RepairEngine(config=config)

    res_fail = engine.evaluator.evaluate(
        response_id="r1",
        evidence_pack={"response_text": "TER is 0.79%", "claimed_value": "0.82"}
    )
    assert res_fail.verdict == "REVISE"

    res_pass = engine.evaluator.evaluate(
        response_id="r2",
        evidence_pack={"response_text": "TER is 0.82%", "claimed_value": "0.82"}
    )
    assert res_pass.verdict == "PASS"

    await engine.close()
