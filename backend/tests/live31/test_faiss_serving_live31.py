"""WP05 / gate G5: verified FAISS serving on a REAL index, receipt, authority and tenant.

The production read path is exercised: VerifiedVectorBridge -> VerifiedFaissRetriever ->
ActiveReceiptResolver -> PostgreSQL receipt/authority + digest-verified index bytes. Generations are
published by the real worker; tampering is done to the real files on disk.

Note on "signed": the index generation is bound by SHA-256 digests (manifest, payload map, index bytes)
and by the PostgreSQL receipt. No asymmetric signature exists on the index itself; that is a design
fact recorded in the validation summary, not something this suite can assert.
"""
import json

import pytest

from amc_publication.serving27 import ServingDenied
from amc_publication.types import VerificationFailed
from amc_publication.vector_bridge28 import VerifiedVectorBridge
from tests.live31 import support
from tests.live31.support import ALPHA, BETA, HashEmbedder, fx, pg_state, seed_graph, serving_allowed

DENIED = (ServingDenied, VerificationFailed)


@pytest.fixture(autouse=True)
def enforce_mode(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")


def _publish(stack, tenant, generation):
    entity, attr, _ = support.graph_target(tenant, generation)
    if support.read_graph(stack.driver, tenant, entity, attr) is None:
        seed_graph(stack.driver, tenant, entity, attr, "legacy")
    work = stack.submit(tenant, generation)
    assert stack.worker().run_once()["status"] == "published"
    return work


def _bridge(stack, tenant, user=None):
    return VerifiedVectorBridge(embedder=HashEmbedder(), retriever=stack.retriever, tenant_id=tenant, user_id=user)


def _gen_dir(stack, tenant):
    return stack.store._path(pg_state(stack.sessions, tenant)["authority"]["digest"])


# ------------------------------------------------------------------ correct answers, correct tenant


@pytest.mark.parametrize("tenant", [ALPHA, BETA])
@pytest.mark.parametrize("generation", ["A", "B"])
async def test_every_probe_is_answered_from_the_active_generation_only(live_stack, tenant, generation):
    _publish(live_stack, tenant, "A")
    if generation == "B":
        _publish(live_stack, tenant, "B")
    bridge = _bridge(live_stack, tenant)
    other = BETA if tenant == ALPHA else ALPHA
    for probe in fx.probes(tenant):
        hits = await bridge.search(probe["query"], top_k=5)
        assert hits, probe["id"]
        top = hits[0]
        assert top["chunk_id"] == probe["expected_citations"][generation], (probe["id"], generation, top["chunk_id"])
        assert probe["must_contain"][generation] in top["text"]
        assert not any(bad in top["text"] for bad in probe["must_not_contain"])
        assert all(h["tenant_id"] == tenant for h in hits), "cross-tenant hit"
        stale = probe["expected_citations"]["A" if generation == "B" else "B"]
        assert stale not in {h["chunk_id"] for h in hits}, "a chunk from the other generation was served"
        assert not any(other.split("_")[1].capitalize() in h["text"] for h in hits)


async def test_two_tenants_with_the_same_document_ids_never_see_each_others_content(live_stack):
    _publish(live_stack, ALPHA, "A")
    _publish(live_stack, BETA, "A")
    q = "What is the total expense ratio of the Liquid Fund?"
    a = await _bridge(live_stack, ALPHA).search(q, top_k=8)
    b = await _bridge(live_stack, BETA).search(q, top_k=8)
    assert {h["tenant_id"] for h in a} == {ALPHA} and {h["tenant_id"] for h in b} == {BETA}
    assert "0.21" in a[0]["text"] and "0.35" in b[0]["text"]
    assert {h["document_id"] for h in a} & {h["document_id"] for h in b}, "fixture must overlap document ids"
    assert not {h["chunk_id"] for h in a} & {h["chunk_id"] for h in b}


async def test_a_tenant_with_no_published_generation_is_denied_not_empty(live_stack):
    _publish(live_stack, ALPHA, "A")
    with pytest.raises(DENIED):
        await _bridge(live_stack, BETA).search("anything", top_k=3)


async def test_a_bridge_scoped_to_one_tenant_refuses_a_request_for_another(live_stack):
    _publish(live_stack, ALPHA, "A")
    _publish(live_stack, BETA, "A")
    with pytest.raises(ServingDenied, match="differs from authenticated scope"):
        await _bridge(live_stack, ALPHA).search("fund", top_k=3, tenant_id=BETA)


async def test_no_tenant_means_no_search(live_stack):
    with pytest.raises(ServingDenied):
        await VerifiedVectorBridge(embedder=HashEmbedder(), retriever=live_stack.retriever).search("x")


# ------------------------------------------------------------------ tamper, corruption, cache


async def _warm(stack, tenant):
    """Serve once so the reader has the index loaded in memory (the stale-cache risk)."""
    assert await _bridge(stack, tenant).search("expense ratio", top_k=2)


async def test_flipped_index_byte_is_refused_even_with_a_warm_cache(live_stack):
    _publish(live_stack, ALPHA, "A")
    await _warm(live_stack, ALPHA)
    path = _gen_dir(live_stack, ALPHA) / "index.faiss"
    raw = bytearray(path.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    path.write_bytes(bytes(raw))
    with pytest.raises(DENIED):
        await _bridge(live_stack, ALPHA).search("expense ratio", top_k=2)
    assert not serving_allowed(live_stack, ALPHA)


@pytest.mark.parametrize("filename", ["index.faiss", "manifest.json", "payloads.json", "snapshot.json"])
async def test_a_missing_generation_file_is_refused(live_stack, filename):
    _publish(live_stack, ALPHA, "A")
    await _warm(live_stack, ALPHA)
    (_gen_dir(live_stack, ALPHA) / filename).unlink()
    with pytest.raises(DENIED):
        await _bridge(live_stack, ALPHA).search("expense ratio", top_k=2)


@pytest.mark.parametrize("field,value", [("tenant", BETA), ("digest", "0" * 64), ("count", 99),
                                         ("index_hash", "f" * 64), ("payload_hash", "e" * 64)])
async def test_a_tampered_manifest_is_refused(live_stack, field, value):
    _publish(live_stack, ALPHA, "A")
    await _warm(live_stack, ALPHA)
    mpath = _gen_dir(live_stack, ALPHA) / "manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest[field] = value
    mpath.write_text(json.dumps(manifest))
    with pytest.raises(DENIED):
        await _bridge(live_stack, ALPHA).search("expense ratio", top_k=2)


async def test_an_edited_payload_text_is_refused(live_stack):
    _publish(live_stack, ALPHA, "A")
    await _warm(live_stack, ALPHA)
    ppath = _gen_dir(live_stack, ALPHA) / "payloads.json"
    payloads = json.loads(ppath.read_text())
    first = next(iter(payloads))
    payloads[first]["text"] = "[SYNTHETIC-FIXTURE] Alpha Liquid Fund total expense ratio is 0.01 percent."
    ppath.write_text(json.dumps(payloads))
    with pytest.raises(DENIED):
        await _bridge(live_stack, ALPHA).search("expense ratio", top_k=2)


def test_a_snapshot_with_a_duplicate_chunk_id_cannot_be_staged(live_stack):
    rows = support.snapshot(ALPHA, "A")
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="duplicate chunk_id"):
        live_stack.store.stage(ALPHA, rows)


def test_a_snapshot_with_a_foreign_tenant_row_cannot_be_staged(live_stack):
    rows = support.snapshot(ALPHA, "A")
    rows.append({**support.snapshot(BETA, "A")[0]})
    with pytest.raises(ValueError, match="cross-tenant"):
        live_stack.store.stage(ALPHA, rows)


async def test_query_embedding_of_the_wrong_dimension_is_refused(live_stack):
    _publish(live_stack, ALPHA, "A")
    with pytest.raises(ServingDenied, match="dimension"):
        await _bridge(live_stack, ALPHA).similarity_search(embedding=[0.1, 0.2, 0.3], limit=3)


# ------------------------------------------------------------------ revocation and rollback


async def test_rollback_revokes_serving_at_once_and_old_generation_returns_cleanly(live_stack):
    _publish(live_stack, ALPHA, "A")
    work_b = _publish(live_stack, ALPHA, "B")
    bridge = _bridge(live_stack, ALPHA)
    probe = fx.probes(ALPHA)[0]
    assert (await bridge.search(probe["query"], top_k=3))[0]["chunk_id"] == probe["expected_citations"]["B"]

    live_stack.journal.request_rollback(work_b, ALPHA)
    with pytest.raises(DENIED):
        await bridge.search(probe["query"], top_k=3)                 # revoked immediately

    assert live_stack.worker().run_once()["status"] == "rolled_back"
    hits = await bridge.search(probe["query"], top_k=3)
    assert hits[0]["chunk_id"] == probe["expected_citations"]["A"]
    assert probe["expected_citations"]["B"] not in {h["chunk_id"] for h in hits}


async def test_revocation_between_retrieval_and_delivery_releases_nothing(live_stack):
    """The authority is re-read after retrieval; a rollback requested in between must stop delivery."""
    _publish(live_stack, ALPHA, "A")
    work_b = _publish(live_stack, ALPHA, "B")
    bridge = _bridge(live_stack, ALPHA)
    real_search = live_stack.retriever.search

    def search_then_revoke(*a, **k):
        hits = real_search(*a, **k)                                  # retrieval completed with B
        live_stack.journal.request_rollback(work_b, ALPHA)          # ... then B is revoked
        return hits

    live_stack.retriever.search = search_then_revoke
    try:
        with pytest.raises(DENIED):
            await bridge.search("expense ratio", top_k=3)
    finally:
        live_stack.retriever.search = real_search


async def test_in_flight_publication_denies_serving_until_it_completes(live_stack):
    _publish(live_stack, ALPHA, "A")
    entity, attr, _ = support.graph_target(ALPHA, "B")
    live_stack.submit(ALPHA, "B")
    bridge = _bridge(live_stack, ALPHA)
    probe = fx.probes(ALPHA)[0]
    seen = []

    async def during(name):
        try:
            seen.append(("served", (await bridge.search(probe["query"], top_k=2))[0]["chunk_id"]))
        except DENIED:
            seen.append(("denied", None))

    import asyncio
    loop = asyncio.get_running_loop()

    def failpoint(name):
        if name == "graph_verified":     # graph written, pointer not yet switched, authority suspended
            asyncio.run_coroutine_threadsafe(during(name), loop).result(30)

    result = await loop.run_in_executor(None, lambda: live_stack.worker(failpoint=failpoint).run_once())
    assert result["status"] == "published"
    assert seen == [("denied", None)], "serving must be denied while the publication is in flight"
    assert (await bridge.search(probe["query"], top_k=2))[0]["chunk_id"] == probe["expected_citations"]["B"]


# ------------------------------------------------------------------ no unreviewed API, no legacy fallback


@pytest.mark.parametrize("attr", ["ingest_documents", "add_documents", "delete", "upsert", "_index", "base_client"])
async def test_the_bridge_exposes_no_write_or_legacy_api(live_stack, attr):
    with pytest.raises(ServingDenied, match="unverified vector API not enabled"):
        getattr(_bridge(live_stack, ALPHA), attr)


async def test_unreviewed_search_options_are_refused(live_stack):
    _publish(live_stack, ALPHA, "A")
    with pytest.raises(ServingDenied, match="unreviewed vector-search options"):
        await _bridge(live_stack, ALPHA).search("fund", top_k=2, rerank=True)


@pytest.mark.parametrize("limit", [0, -1, 101, "5", 2.5])
async def test_result_limit_is_bounded(live_stack, limit):
    _publish(live_stack, ALPHA, "A")
    with pytest.raises(ValueError):
        await _bridge(live_stack, ALPHA).similarity_search(query="fund", limit=limit)
