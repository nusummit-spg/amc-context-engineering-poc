"""Wave 4.0 E6: provider residency policy, outbound PII scrub, and embedder binding."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import provider_policy40 as policy


def _settings(**kw):
    base = dict(llm_provider="bedrock", llm_model="m", enable_multi_provider_fallback=False,
                enable_local_llm_fallback=False)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_PROVIDER_POLICY", "on")
    monkeypatch.setenv("AMC_LLM_PROVIDER_ALLOWLIST", "bedrock, openai")
    monkeypatch.setenv("AMC_LLM_REGION_ALLOWLIST", "ap-south-1,ap-south-2")
    monkeypatch.setenv("AMC_LLM_REGION", "ap-south-1")


# ----------------------------------------------------------------------------------------- residency policy

def test_policy_off_by_default(monkeypatch):
    monkeypatch.delenv("AMC_PROVIDER_POLICY", raising=False)
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    assert policy.assert_provider_policy(_settings(llm_provider="groq")) is None


def test_policy_needs_enforce_mode(on, monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "off")
    assert policy.assert_provider_policy(_settings(llm_provider="groq")) is None


def test_good_configuration_is_recorded(on):
    assert policy.assert_provider_policy(_settings()) == {"provider": "bedrock", "region": "ap-south-1", "model": "m"}


@pytest.mark.parametrize("change,match", [
    ({"env": ("AMC_LLM_PROVIDER_ALLOWLIST", "")}, "ALLOWLIST is required"),
    ({"settings": {"llm_provider": "groq"}}, "not in AMC_LLM_PROVIDER_ALLOWLIST"),
    ({"env": ("AMC_LLM_REGION", "us-east-1")}, "not in AMC_LLM_REGION_ALLOWLIST"),
    ({"env": ("AMC_LLM_REGION", "")}, "AMC_LLM_REGION"),
    ({"settings": {"enable_multi_provider_fallback": True}}, "fallbacks must be disabled"),
    ({"settings": {"enable_local_llm_fallback": True}}, "fallbacks must be disabled"),
])
def test_violations_refuse(on, monkeypatch, change, match):
    if "env" in change:
        monkeypatch.setenv(*change["env"])
    with pytest.raises(policy.ProviderPolicyError, match=match):
        policy.assert_provider_policy(_settings(**change.get("settings", {})))


def test_malformed_flag_refuses(monkeypatch):
    monkeypatch.setenv("AMC_PROVIDER_POLICY", "true")
    with pytest.raises(policy.ProviderPolicyError):
        policy.policy_enabled()


# ------------------------------------------------------------------------------------------- outbound PII

def test_outbound_scrubs_pii_and_keeps_isin(on):
    prompt = ("Investor ABCDE1234F, mail a.b@example.com, phone +91 9876543210, Aadhaar 1234 5678 9012. "
              "Scheme ISIN INF209K01165 NAV 922.67.")
    clean, system = policy.outbound("bedrock", prompt, "System for x@y.com")
    for secret in ("ABCDE1234F", "a.b@example.com", "9876543210", "1234 5678 9012", "x@y.com"):
        assert secret not in clean + system
    assert "INF209K01165" in clean and "922.67" in clean


def test_outbound_refuses_provider_outside_allowlist(on):
    with pytest.raises(policy.ProviderPolicyError):
        policy.outbound("groq", "hello", None)


def test_outbound_is_noop_when_off(monkeypatch):
    monkeypatch.setenv("AMC_PROVIDER_POLICY", "off")
    assert policy.outbound("groq", "mail a@b.com", None) == ("mail a@b.com", None)


@pytest.mark.asyncio
async def test_llm_client_scrubs_before_every_provider_call(on):
    from app.core.llm import LLMClient
    client = object.__new__(LLMClient)               # no network client needed for this check
    seen = {}

    async def fake_openai(prompt, system, max_tokens, schema):
        seen["prompt"], seen["system"] = prompt, system
        return "ok"
    client._call_openai = fake_openai
    out = await client._call_provider("openai", "PAN ABCDE1234F", "sys", None, False, False, None)
    assert out == "ok" and "ABCDE1234F" not in seen["prompt"]
    with pytest.raises(policy.ProviderPolicyError):
        await client._call_provider("groq", "x", None, None, False, False, None)


# ------------------------------------------------------------------------------------------ embedder binding

from amc_publication.embedder_identity40 import embedder_identity, same_embedder  # noqa: E402


class _Declared:
    def __init__(self, model):
        self.embedder_identity = {"id": "fastembed.TextEmbedding", "model": model}
        self._dim = 4

    async def embed_async(self, texts):
        return [[0.5, 0.5, 0.5, 0.5] for _ in texts]


def test_identity_prefers_declaration_and_records_dimension():
    assert embedder_identity(_Declared("bge-small"), dimension=4) == {
        "id": "fastembed.TextEmbedding", "model": "bge-small", "dimension": 4}
    assert same_embedder({"id": "a", "model": "m", "dimension": 4}, {"id": "a", "model": "m"})
    assert not same_embedder({"id": "a", "model": "m"}, {"id": "a", "model": "other"})
    assert not same_embedder(None, {"id": "a"})


def test_vector_store_declares_identity():
    from app.vector.client import VectorStore
    ident = VectorStore.embedder_identity.fget(object.__new__(VectorStore))
    assert ident["id"] == "fastembed.TextEmbedding" and ident["model"]


class _Retriever:
    def __init__(self, built_with):
        self._built_with = built_with
        self.resolver = SimpleNamespace(_authority=lambda tenant: ("g", "d", 1, "w", "r"))

    def search(self, tenant, embedding, limit=100):
        doc = {"chunk_id": "c1", "tenant_id": tenant, "text": "t"}
        return [{"chunk_id": "c1", "score": 0.9, "document": doc}]

    def embedder_identity_for(self, tenant, generation_id=None):
        return self._built_with


def _bridge(built_with, query_model):
    from amc_publication.vector_bridge28 import VerifiedVectorBridge
    return VerifiedVectorBridge(embedder=_Declared(query_model), retriever=_Retriever(built_with), tenant_id="T")


@pytest.fixture
def binding(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_EMBEDDER_BINDING", "on")


@pytest.mark.asyncio
async def test_matching_embedder_serves(binding):
    hits = await _bridge({"id": "fastembed.TextEmbedding", "model": "bge-small", "dimension": 4},
                         "bge-small").search("q", tenant_id="T")
    assert [h["chunk_id"] for h in hits] == ["c1"]


@pytest.mark.asyncio
async def test_different_query_embedder_is_refused(binding):
    from amc_publication.serving27 import ServingDenied
    with pytest.raises(ServingDenied, match="differs"):
        await _bridge({"id": "fastembed.TextEmbedding", "model": "bge-small"}, "hash-stub").search("q", tenant_id="T")


@pytest.mark.asyncio
async def test_generation_without_recorded_embedder_is_refused(binding):
    from amc_publication.serving27 import ServingDenied
    with pytest.raises(ServingDenied, match="republish"):
        await _bridge(None, "bge-small").search("q", tenant_id="T")


@pytest.mark.asyncio
async def test_binding_off_keeps_wave31_behaviour(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_EMBEDDER_BINDING", "off")
    hits = await _bridge(None, "anything").search("q", tenant_id="T")
    assert len(hits) == 1


def test_faiss_stage_records_embedder_in_signed_manifest(tmp_path):
    """Real FAISS build: the identity is inside manifest.json, which the publisher signs."""
    pytest.importorskip("faiss")
    import json
    from amc_publication.faiss_artifacts import FaissGenerationStore
    from amc_publication.signing31 import GenerationSigner, GenerationVerifier, generate_keypair

    class Emb(_Declared):
        def embed(self, texts):
            return [[float(i + 1), 1.0, 0.0, 0.0] for i, _ in enumerate(texts)]
    priv, pub = generate_keypair()
    store = FaissGenerationStore(tmp_path, Emb("bge-small"), signer=GenerationSigner("k", priv),
                                 verifier=GenerationVerifier({"k": pub}))
    gen = store.stage("T", [{"chunk_id": "c1", "tenant_id": "T", "text": "a"},
                            {"chunk_id": "c2", "tenant_id": "T", "text": "b"}])
    manifest = json.loads((store._path(gen.digest) / "manifest.json").read_bytes())
    assert manifest["embedder"] == {"id": "fastembed.TextEmbedding", "model": "bge-small", "dimension": 4}
    store.verify(gen, "T")                      # signature still valid over the extended manifest
