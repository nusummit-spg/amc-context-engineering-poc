"""Ed25519 signatures for published FAISS generations (Wave 3.1).

A generation directory holds manifest.json, which already binds the index bytes (index_hash), the payload map
(payload_hash), the count, the tenant and the content digest. The publisher signs a small message that binds
that manifest to one tenant and one generation:

    {"v":1,"alg":"ed25519","key_id":K,"tenant":T,"generation_id":G,"manifest_sha256":sha256(manifest.json)}

and writes signature.json next to it. The serving side holds ONLY public keys, so a compromised app host cannot
mint a generation; it can be told to distrust a key (revocation list) and refuses a generation signed by any
unknown, revoked or mismatched key. A signature cannot be reused for another tenant or generation because both
are part of the signed message and are taken from what the caller EXPECTS, never from the file.

Key custody is the control: the private key lives only on the publisher host (AMC_PUBLICATION_SIGNING_KEY_FILE,
JSON {"key_id","private_key"} with a base64 raw 32-byte seed); the serving host gets AMC_VERIFIED_FAISS_PUBLIC_KEYS,
JSON {"keys":{key_id: base64 public key}, "revoked":[key_id,...]}. This module does not manage rotation; add a new
key to "keys" and revoke the old one.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .types import VerificationFailed, canonical_bytes

SIGNATURE_FILE = "signature.json"
ALG = "ed25519"
VERSION = 1
SIGNING_KEY_ENV = "AMC_PUBLICATION_SIGNING_KEY_FILE"
PUBLIC_KEYS_ENV = "AMC_VERIFIED_FAISS_PUBLIC_KEYS"
_KEY_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError, AttributeError) as exc:
        raise ValueError(f"{what} is not valid base64") from exc


def _message(key_id: str, tenant: str, generation_id: str, manifest_sha256: str) -> bytes:
    return canonical_bytes({"v": VERSION, "alg": ALG, "key_id": key_id, "tenant": tenant,
                            "generation_id": generation_id, "manifest_sha256": manifest_sha256})


def generate_keypair() -> tuple[str, str]:
    """(private_seed_b64, public_key_b64). For tests and first-time setup; keep the private half private."""
    key = ed25519.Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _b64(private), _b64(public)


class GenerationSigner:
    """Holds the private key. Exists only on the publisher host."""

    def __init__(self, key_id: str, private_key_b64: str):
        if not isinstance(key_id, str) or not _KEY_ID.match(key_id):
            raise ValueError("key_id must be 1-64 characters of letters, digits and . _ : -")
        seed = _unb64(private_key_b64, "private key")
        if len(seed) != 32:
            raise ValueError("private key must be a raw 32-byte Ed25519 seed")
        self.key_id = key_id
        self._key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)

    def __repr__(self) -> str:                       # never print key material
        return f"GenerationSigner(key_id={self.key_id!r})"

    @property
    def public_key_b64(self) -> str:
        return _b64(self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))

    def sign_manifest(self, manifest_bytes: bytes, *, tenant: str, generation_id: str) -> dict:
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        sig = self._key.sign(_message(self.key_id, tenant, generation_id, digest))
        return {"v": VERSION, "alg": ALG, "key_id": self.key_id, "manifest_sha256": digest, "signature": _b64(sig)}


class GenerationVerifier:
    """Holds public keys only."""

    def __init__(self, keys: dict[str, str], revoked=()):
        if not isinstance(keys, dict) or not keys:
            raise ValueError("at least one trusted public key is required")
        self._keys = {}
        for key_id, pub in keys.items():
            if not isinstance(key_id, str) or not _KEY_ID.match(key_id):
                raise ValueError(f"invalid key_id {key_id!r}")
            raw = _unb64(pub, f"public key {key_id}")
            if len(raw) != 32:
                raise ValueError(f"public key {key_id} must be a raw 32-byte Ed25519 key")
            self._keys[key_id] = ed25519.Ed25519PublicKey.from_public_bytes(raw)
        self.revoked = frozenset(revoked or ())

    @property
    def key_ids(self) -> list[str]:
        return sorted(self._keys)

    def trusts(self, key_id: str, public_key_b64: str) -> bool:
        """True only if key_id is trusted, not revoked, and bound to exactly this public key."""
        public = self._keys.get(key_id)
        if public is None or key_id in self.revoked:
            return False
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return _b64(raw) == public_key_b64

    def verify_directory(self, directory: Path, *, tenant: str, generation_id: str) -> None:
        """Raise VerificationFailed unless directory/signature.json validly signs directory/manifest.json."""
        try:
            doc = json.loads((Path(directory) / SIGNATURE_FILE).read_bytes())
        except FileNotFoundError as exc:
            raise VerificationFailed("generation is not signed") from exc
        except (OSError, ValueError) as exc:
            raise VerificationFailed("generation signature is unreadable") from exc
        try:
            manifest = (Path(directory) / "manifest.json").read_bytes()
        except OSError as exc:
            raise VerificationFailed("generation manifest is missing") from exc
        self.verify_manifest_bytes(manifest, doc, tenant=tenant, generation_id=generation_id)

    def verify_manifest_bytes(self, manifest: bytes, doc, *, tenant: str, generation_id: str) -> None:
        """Raise VerificationFailed unless `doc` (a signature.json object) validly signs `manifest`.

        Wave 4.0: also used for structured-dataset manifests held in PostgreSQL (amc_publication.fin40),
        so both planes share one signature format, key set and revocation list.
        """
        if not isinstance(doc, dict):
            raise VerificationFailed("generation signature is malformed")
        if doc.get("v") != VERSION or doc.get("alg") != ALG:
            raise VerificationFailed("unsupported generation signature version or algorithm")
        key_id, claimed, signature = doc.get("key_id"), doc.get("manifest_sha256"), doc.get("signature")
        if not all(isinstance(x, str) for x in (key_id, claimed, signature)):
            raise VerificationFailed("generation signature is malformed")
        if key_id in self.revoked:
            raise VerificationFailed("generation was signed with a revoked key")
        public = self._keys.get(key_id)
        if public is None:
            raise VerificationFailed("generation was signed with an unknown key")
        if not isinstance(manifest, (bytes, bytearray)):
            raise VerificationFailed("generation manifest is missing")
        if hashlib.sha256(manifest).hexdigest() != claimed:
            raise VerificationFailed("generation manifest changed after it was signed")
        try:
            public.verify(_unb64(signature, "signature"), _message(key_id, tenant, generation_id, claimed))
        except (InvalidSignature, ValueError) as exc:
            raise VerificationFailed("generation signature is invalid for this tenant and generation") from exc


def _read_json(path: str, what: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{what} ({path}) is missing or not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{what} must be a JSON object")
    return data


def signer_from_env(environ=None) -> GenerationSigner | None:
    path = (os.environ if environ is None else environ).get(SIGNING_KEY_ENV)
    if not path:
        return None
    data = _read_json(path, SIGNING_KEY_ENV)
    return GenerationSigner(data.get("key_id", ""), data.get("private_key", ""))


def verifier_from_env(environ=None) -> GenerationVerifier | None:
    path = (os.environ if environ is None else environ).get(PUBLIC_KEYS_ENV)
    if not path:
        return None
    data = _read_json(path, PUBLIC_KEYS_ENV)
    return GenerationVerifier(data.get("keys", {}), data.get("revoked", []))
