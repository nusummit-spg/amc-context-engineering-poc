"""Unit tests for Ed25519 generation signatures and two-person approval evidence. No services needed."""
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from amc_publication import approvals31 as ap
from amc_publication import signing31 as sg
from amc_publication.faiss_artifacts import FaissGenerationStore
from amc_publication.types import VerificationFailed


class _Embedder:
    _dim = 16

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 16
            for tok in re.findall(r"[a-z0-9.]+", t.lower()):
                v[int.from_bytes(hashlib.sha256(tok.encode()).digest()[:2], "big") % 16] += 1.0
            out.append(v)
        return out


def _rows(tenant="T", text="Fund expense ratio is 0.21 percent"):
    return [{"chunk_id": f"{tenant}:{i}", "tenant_id": tenant, "text": f"{text} {i}"} for i in range(3)]


@pytest.fixture
def keys():
    priv, pub = sg.generate_keypair()
    return sg.GenerationSigner("pub-2026", priv), sg.GenerationVerifier({"pub-2026": pub}), priv, pub


# ------------------------------------------------------------------------------ generation signatures


def test_a_signed_generation_verifies_and_serves_the_same_content(tmp_path, keys):
    signer, verifier, _, _ = keys
    store = FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier)
    gen = store.stage("T", _rows())
    assert (store._path(gen.digest) / sg.SIGNATURE_FILE).is_file()
    assert len(store.verify(gen, "T")) == 3
    reader = FaissGenerationStore(tmp_path, None, verifier=verifier)        # serving side: public keys only
    assert len(reader.verify_by_digest(gen.digest, "T")) == 3


def test_an_unsigned_generation_is_refused_when_a_verifier_is_configured(tmp_path, keys):
    _, verifier, _, _ = keys
    unsigned = FaissGenerationStore(tmp_path, _Embedder())                  # legacy publisher, no signer
    gen = unsigned.stage("T", _rows())
    with pytest.raises(VerificationFailed, match="not signed"):
        FaissGenerationStore(tmp_path, None, verifier=verifier).verify(gen, "T")
    FaissGenerationStore(tmp_path, None).verify(gen, "T")                   # no verifier: legacy behavior unchanged


def test_staging_content_that_already_exists_unsigned_signs_it_after_verifying(tmp_path, keys):
    signer, verifier, _, _ = keys
    gen = FaissGenerationStore(tmp_path, _Embedder()).stage("T", _rows())
    store = FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier)
    assert store.stage("T", _rows()).digest == gen.digest
    store.verify(gen, "T")


def test_corrupted_existing_content_is_never_signed(tmp_path, keys):
    signer, verifier, _, _ = keys
    gen = FaissGenerationStore(tmp_path, _Embedder()).stage("T", _rows())
    d = FaissGenerationStore(tmp_path, None)._path(gen.digest)
    raw = bytearray((d / "index.faiss").read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    (d / "index.faiss").write_bytes(bytes(raw))
    with pytest.raises(VerificationFailed):
        FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier).stage("T", _rows())
    assert not (d / sg.SIGNATURE_FILE).exists()


@pytest.mark.parametrize("mutation", ["flip_signature", "edit_manifest", "swap_key_id", "wrong_alg", "bad_json",
                                      "delete_signature", "extra_type", "truncate"])
def test_any_tampering_with_the_signature_or_manifest_is_refused(tmp_path, keys, mutation):
    signer, verifier, _, _ = keys
    store = FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier)
    gen = store.stage("T", _rows())
    d = store._path(gen.digest)
    sig_path, man_path = d / sg.SIGNATURE_FILE, d / "manifest.json"
    sig = json.loads(sig_path.read_text())
    if mutation == "flip_signature":
        raw = bytearray(base64.b64decode(sig["signature"]))
        raw[0] ^= 1
        sig["signature"] = base64.b64encode(bytes(raw)).decode()
        sig_path.write_text(json.dumps(sig))
    elif mutation == "edit_manifest":
        m = json.loads(man_path.read_text())
        m["count"] = m["count"]            # same data re-serialised with a different byte layout
        man_path.write_text(json.dumps(m, indent=2))
    elif mutation == "swap_key_id":
        sig["key_id"] = "other"
        sig_path.write_text(json.dumps(sig))
    elif mutation == "wrong_alg":
        sig["alg"] = "rsa"
        sig_path.write_text(json.dumps(sig))
    elif mutation == "bad_json":
        sig_path.write_text("{not json")
    elif mutation == "delete_signature":
        sig_path.unlink()
    elif mutation == "extra_type":
        sig_path.write_text(json.dumps(["not", "an", "object"]))
    elif mutation == "truncate":
        sig_path.write_bytes(sig_path.read_bytes()[:20])
    with pytest.raises(VerificationFailed):
        store.verify(gen, "T")


def test_a_signature_cannot_be_reused_for_another_tenant_or_generation(tmp_path, keys):
    signer, verifier, _, _ = keys
    store = FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier)
    g1, g2 = store.stage("T", _rows(text="alpha")), store.stage("T", _rows(text="beta"))
    d1, d2 = store._path(g1.digest), store._path(g2.digest)
    (d2 / sg.SIGNATURE_FILE).write_bytes((d1 / sg.SIGNATURE_FILE).read_bytes())      # transplant
    with pytest.raises(VerificationFailed):
        store.verify(g2, "T")
    with pytest.raises(VerificationFailed):                                           # right file, wrong tenant
        verifier.verify_directory(d1, tenant="OTHER", generation_id=g1.generation_id)


def test_unknown_and_revoked_keys_are_refused(tmp_path, keys):
    signer, verifier, _, pub = keys
    gen = FaissGenerationStore(tmp_path, _Embedder(), signer=signer).stage("T", _rows())
    d = FaissGenerationStore(tmp_path, None)._path(gen.digest)
    stranger = sg.GenerationVerifier({"someone-else": sg.generate_keypair()[1]})
    with pytest.raises(VerificationFailed, match="unknown key"):
        stranger.verify_directory(d, tenant="T", generation_id=gen.generation_id)
    revoking = sg.GenerationVerifier({"pub-2026": pub}, revoked=["pub-2026"])
    with pytest.raises(VerificationFailed, match="revoked"):
        revoking.verify_directory(d, tenant="T", generation_id=gen.generation_id)
    impostor = sg.GenerationVerifier({"pub-2026": sg.generate_keypair()[1]})          # same id, different key
    with pytest.raises(VerificationFailed, match="invalid"):
        impostor.verify_directory(d, tenant="T", generation_id=gen.generation_id)


def test_key_material_is_validated_and_never_printed(keys):
    signer, _, priv, _ = keys
    assert priv not in repr(signer) and "private" not in repr(signer).lower()
    for bad in ("", "not base64!!", base64.b64encode(b"short").decode()):
        with pytest.raises(ValueError):
            sg.GenerationSigner("k", bad)
    for bad_id in ("", "has space", "x" * 65, "../etc"):
        with pytest.raises(ValueError):
            sg.GenerationSigner(bad_id, priv)
    with pytest.raises(ValueError):
        sg.GenerationVerifier({})


def test_env_loaders_read_json_files_and_reject_garbage(tmp_path, keys):
    signer, _, priv, pub = keys
    sk, pk = tmp_path / "sk.json", tmp_path / "pk.json"
    sk.write_text(json.dumps({"key_id": "pub-2026", "private_key": priv}))
    pk.write_text(json.dumps({"keys": {"pub-2026": pub}, "revoked": ["old"]}))
    assert sg.signer_from_env({sg.SIGNING_KEY_ENV: str(sk)}).key_id == "pub-2026"
    v = sg.verifier_from_env({sg.PUBLIC_KEYS_ENV: str(pk)})
    assert v.key_ids == ["pub-2026"] and "old" in v.revoked
    assert sg.signer_from_env({}) is None and sg.verifier_from_env({}) is None
    bad = tmp_path / "bad.json"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        sg.verifier_from_env({sg.PUBLIC_KEYS_ENV: str(bad)})
    with pytest.raises(ValueError):
        sg.verifier_from_env({sg.PUBLIC_KEYS_ENV: str(tmp_path / "missing.json")})


def test_the_production_worker_and_the_serving_factory_require_signed_generations(tmp_path, keys, monkeypatch):
    from amc_publication.graph import InMemoryGraphPort, Neo4jGraphPort
    from amc_publication.worker import PublicationWorker
    signer, verifier, _, _ = keys
    unsigned = FaissGenerationStore(tmp_path, _Embedder())
    graph = Neo4jGraphPort(object(), allowed_attributes={"ter"})
    with pytest.raises(ValueError, match="signed generations"):
        PublicationWorker(object(), graph, unsigned, serving_probe=lambda *a: True)
    with pytest.raises(ValueError, match="signed generations"):                     # signer without verifier
        PublicationWorker(object(), graph, FaissGenerationStore(tmp_path, _Embedder(), signer=signer),
                          serving_probe=lambda *a: True)
    PublicationWorker(object(), graph, FaissGenerationStore(tmp_path, _Embedder(), signer=signer, verifier=verifier),
                      serving_probe=lambda *a: True)
    from amc_publication.serving27 import ServingDenied
    from amc_publication.vector_bridge28 import create_verified_vector_store
    monkeypatch.setenv("AMC_VERIFIED_FAISS_ROOT", str(tmp_path))
    monkeypatch.delenv(sg.PUBLIC_KEYS_ENV, raising=False)
    with pytest.raises(ServingDenied, match="signed generations are required"):
        create_verified_vector_store(base_client=object())


# ------------------------------------------------------------------------------ two-person approvals


def _approvers():
    keys = {}
    trust = {"approvers": {}, "revoked": []}
    for name in ("alice", "bob", "carol"):
        priv, pub = ap.generate_approver_keypair()
        keys[name] = ap.ApproverSigner(name, f"{name}-2026", priv)
        trust["approvers"][name] = {"roles": ["proposer", "reviewer"], "keys": {f"{name}-2026": pub}}
    return keys, trust


def _subject(corpus=None, **over):
    base = dict(tenant="T", entity="Fund", attribute="ter", value="0.21", proposal_id="P-1", revision=1,
                corpus=corpus or _rows())
    base.update(over)
    return ap.make_subject(**base)


def _signed(keys, subject, proposer="alice", reviewer="bob", **kw):
    rec = ap.new_record(subject, **kw)
    return keys[reviewer].sign(keys[proposer].sign(rec, "proposer"), "reviewer")


def test_two_distinct_signed_approvals_verify_and_bind_the_exact_change():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    subject = _subject()
    rec = _signed(keys, subject)
    ok = v.verify(rec, expected_subject=subject)
    assert (ok.proposer, ok.reviewer) == ("alice", "bob") and len(ok.evidence_sha256) == 64


@pytest.mark.parametrize("field,value", [("tenant", "OTHER"), ("entity", "Other Fund"), ("attribute", "exit_load"),
                                         ("value", "9.99"), ("proposal_id", "P-2"), ("revision", 2)])
def test_an_approval_for_one_change_cannot_authorise_another(field, value):
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    rec = _signed(keys, _subject())
    with pytest.raises(ap.ApprovalRefused, match=field):
        v.verify(rec, expected_subject=_subject(**{field: value}))


def test_a_different_corpus_invalidates_the_approval():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    rec = _signed(keys, _subject())
    with pytest.raises(ap.ApprovalRefused, match="corpus_sha256"):
        v.verify(rec, expected_subject=_subject(corpus=_rows(text="tampered")))


def test_the_same_person_cannot_be_both_approvers():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    subject = _subject()
    with pytest.raises(ap.ApprovalRefused, match="different people"):
        v.verify(_signed(keys, subject, proposer="alice", reviewer="alice"), expected_subject=subject)


def test_one_key_registered_under_two_names_cannot_be_both_approvers():
    priv, pub = ap.generate_approver_keypair()
    one, two = ap.ApproverSigner("mallory", "m-1", priv), ap.ApproverSigner("mallory2", "m-2", priv)
    v = ap.ApprovalVerifier({"mallory": {"roles": ["proposer"], "keys": {"m-1": pub}},
                             "mallory2": {"roles": ["reviewer"], "keys": {"m-2": pub}}})
    subject = _subject()
    rec = two.sign(one.sign(ap.new_record(subject), "proposer"), "reviewer")
    with pytest.raises(ap.ApprovalRefused, match="different keys"):
        v.verify(rec, expected_subject=subject)


def test_the_operator_cannot_forge_a_reviewer_signature():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    subject = _subject()
    rec = keys["alice"].sign(ap.new_record(subject), "proposer")
    forged_priv, _ = ap.generate_approver_keypair()
    forged = ap.ApproverSigner("bob", "bob-2026", forged_priv)                  # claims to be bob, wrong key
    with pytest.raises(ap.ApprovalRefused, match="signature is invalid"):
        v.verify(forged.sign(rec, "reviewer"), expected_subject=subject)


@pytest.mark.parametrize("case", ["unknown_approver", "unknown_key", "role_not_allowed", "revoked", "missing_reviewer",
                                  "three_signatures", "no_signatures", "bad_version", "not_a_dict"])
def test_untrusted_or_malformed_evidence_is_refused(case):
    keys, trust = _approvers()
    approvers = json.loads(json.dumps(trust["approvers"]))
    revoked = []
    subject = _subject()
    rec = _signed(keys, subject)
    if case == "unknown_approver":
        approvers.pop("bob")
    elif case == "unknown_key":
        approvers["bob"]["keys"] = {"bob-other": next(iter(approvers["bob"]["keys"].values()))}
    elif case == "role_not_allowed":
        approvers["bob"]["roles"] = ["proposer"]
    elif case == "revoked":
        revoked = ["bob-2026"]
    elif case == "missing_reviewer":
        rec = keys["alice"].sign(ap.new_record(subject), "proposer")
    elif case == "three_signatures":
        rec["approvals"].append(dict(rec["approvals"][0]))
    elif case == "no_signatures":
        rec["approvals"] = []
    elif case == "bad_version":
        rec["v"] = 2
    elif case == "not_a_dict":
        rec = ["x"]
    with pytest.raises(ap.ApprovalRefused):
        ap.ApprovalVerifier(approvers, revoked).verify(rec, expected_subject=subject)


def test_expired_future_and_overlong_approvals_are_refused():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    subject = _subject()
    now = datetime.now(timezone.utc)
    with pytest.raises(ap.ApprovalRefused, match="expired"):
        v.verify(_signed(keys, subject, now=now - timedelta(days=5), valid_for=timedelta(days=1)), expected_subject=subject)
    with pytest.raises(ap.ApprovalRefused, match="future"):
        v.verify(_signed(keys, subject, now=now + timedelta(days=2)), expected_subject=subject)
    with pytest.raises(ap.ApprovalRefused, match="at most"):
        ap.new_record(subject, valid_for=timedelta(days=30))
    long_rec = _signed(keys, subject)
    long_rec["expires_at"] = (now + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(ap.ApprovalRefused):
        v.verify(long_rec, expected_subject=subject)


def test_tampering_with_the_validity_window_or_role_breaks_the_signature():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    subject = _subject()
    rec = _signed(keys, subject)
    later = json.loads(json.dumps(rec))
    later["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(ap.ApprovalRefused, match="signature is invalid"):
        v.verify(later, expected_subject=subject)
    swapped = json.loads(json.dumps(rec))
    for e in swapped["approvals"]:
        e["role"] = "reviewer" if e["role"] == "proposer" else "proposer"
    with pytest.raises(ap.ApprovalRefused, match="signature is invalid"):
        v.verify(swapped, expected_subject=subject)


def test_a_signer_cannot_sign_the_same_role_twice_or_an_unknown_role():
    keys, _ = _approvers()
    rec = keys["alice"].sign(ap.new_record(_subject()), "proposer")
    with pytest.raises(ap.ApprovalRefused, match="already"):
        keys["bob"].sign(rec, "proposer")
    with pytest.raises(ap.ApprovalRefused):
        keys["bob"].sign(rec, "approver")


def test_payload_reverification_binds_the_record_to_the_queued_work():
    keys, trust = _approvers()
    v = ap.ApprovalVerifier(trust["approvers"])
    corpus = _rows()
    rec = _signed(keys, _subject(corpus=corpus))
    payload = {"entity": "Fund", "attribute": "ter", "corrected_value": "0.21", "full_vector_snapshot": corpus,
              "approval": rec}
    assert v.verify_payload(payload).proposer == "alice"
    for key, value in (("entity", "Other"), ("attribute", "x"), ("corrected_value", "9"),
                       ("full_vector_snapshot", _rows(text="swapped"))):
        with pytest.raises(ap.ApprovalRefused):
            v.verify_payload({**payload, key: value})
    with pytest.raises(ap.ApprovalRefused, match="no approval evidence"):
        v.verify_payload({k: x for k, x in payload.items() if k != "approval"})


def test_the_corpus_hash_ignores_row_order_but_not_content():
    a = _rows()
    assert ap.corpus_sha256(a) == ap.corpus_sha256(list(reversed(a)))
    assert ap.corpus_sha256(a) != ap.corpus_sha256(_rows(text="changed"))
    for bad in ([], None, [{"no_chunk_id": 1}], "x"):
        with pytest.raises(ap.ApprovalRefused):
            ap.corpus_sha256(bad)


def test_approver_side_tool_builds_signs_and_verifies_a_record(tmp_path, monkeypatch, capsys):
    keys, trust = _approvers()
    priv_alice = {"approver_id": "alice", "key_id": "alice-2026"}
    # real key files as an approver would hold them
    alice_priv, alice_pub = ap.generate_approver_keypair()
    bob_priv, bob_pub = ap.generate_approver_keypair()
    (tmp_path / "alice.json").write_text(json.dumps({**priv_alice, "private_key": alice_priv}))
    (tmp_path / "bob.json").write_text(json.dumps({"approver_id": "bob", "key_id": "bob-2026", "private_key": bob_priv}))
    (tmp_path / "trust.json").write_text(json.dumps({"approvers": {
        "alice": {"roles": ["proposer"], "keys": {"alice-2026": alice_pub}},
        "bob": {"roles": ["reviewer"], "keys": {"bob-2026": bob_pub}}}}))
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps(_rows()))
    rec = tmp_path / "rec.json"
    base = ["--corpus", str(corpus)]
    assert ap.main(["subject", "--tenant", "T", "--entity", "Fund", "--attribute", "ter", "--value", "0.21",
                    "--proposal-id", "P-1", "--out", str(rec), *base]) == 0
    assert ap.main(["sign", "--record", str(rec), "--key-file", str(tmp_path / "alice.json"), "--role", "proposer", *base]) == 0
    assert ap.main(["sign", "--record", str(rec), "--key-file", str(tmp_path / "bob.json"), "--role", "reviewer", *base]) == 0
    monkeypatch.setenv(ap.TRUST_ENV, str(tmp_path / "trust.json"))
    capsys.readouterr()
    assert ap.main(["verify", "--record", str(rec), *base]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["proposer"] == "alice" and out["reviewer"] == "bob"
    # an approver is refused if the corpus they are shown is not the corpus in the record
    other = tmp_path / "other.json"
    other.write_text(json.dumps(_rows(text="not what was approved")))
    fresh = tmp_path / "rec2.json"
    assert ap.main(["subject", "--tenant", "T", "--entity", "Fund", "--attribute", "ter", "--value", "0.21",
                    "--proposal-id", "P-1", "--out", str(fresh), *base]) == 0
    capsys.readouterr()
    assert ap.main(["sign", "--record", str(fresh), "--key-file", str(tmp_path / "alice.json"), "--role", "proposer",
                    "--corpus", str(other)]) == 2
    assert "refusing to sign what you have not seen" in capsys.readouterr().out


def test_trusts_requires_the_same_key_id_and_the_same_public_key():
    from amc_publication import signing31 as s
    k1, k2 = s.generate_keypair()[0], s.generate_keypair()[0]
    signer = s.GenerationSigner("k", k1)
    same = s.GenerationVerifier({"k": signer.public_key_b64})
    other = s.GenerationVerifier({"k": s.GenerationSigner("k", k2).public_key_b64})
    assert same.trusts("k", signer.public_key_b64)
    assert not other.trusts("k", signer.public_key_b64), "same id, different key must not be trusted"
    assert not s.GenerationVerifier({"k": signer.public_key_b64}, ["k"]).trusts("k", signer.public_key_b64)
    assert not same.trusts("unknown", signer.public_key_b64)
