"""Verifiable two-person approval evidence for publications (Wave 3.1).

Before this module the operator CLI took two names and an attestation flag: nothing proved that two different
people approved. Now a publication needs an approval RECORD carrying two Ed25519 signatures, one per approver,
each made with that approver's OWN private key on their OWN machine:

    subject = {tenant, entity, attribute, value, proposal_id, revision, corpus_sha256}   (what is being approved)
    record  = {"v":1, "subject":subject, "issued_at":..., "expires_at":...,
               "approvals":[{"role":"proposer","approver_id":..,"key_id":..,"signature":..},
                            {"role":"reviewer", ...}]}

Each signature covers the role, approver id, key id, the hash of the subject and the validity window, so it cannot
be moved to another change, role or time. The operator host holds only a TRUST STORE of public keys
(AMC_PUBLICATION_APPROVER_KEYS), so the operator cannot forge a reviewer's approval; they would need the
reviewer's private key.

    {"approvers": {"alice": {"roles": ["proposer","reviewer"], "keys": {"alice-2026": "<b64 public key>"}}, ...},
     "revoked": ["old-key-id"]}

What this proves: the holders of two distinct, trusted, unrevoked private keys signed exactly this change within its
validity window. What it does not prove: that each key is held by the one named human (key custody and enrollment are
organizational controls), nor that the approvers reviewed the corpus content (they sign its hash).
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .types import canonical_bytes, sha256_json

VERSION = 1
KIND = "amc-publication-approval"
ROLES = ("proposer", "reviewer")
TRUST_ENV = "AMC_PUBLICATION_APPROVER_KEYS"
MAX_VALIDITY = timedelta(days=14)
CLOCK_SKEW = timedelta(minutes=5)
SUBJECT_FIELDS = ("tenant", "entity", "attribute", "value", "proposal_id", "revision", "corpus_sha256")
_ID = re.compile(r"^[A-Za-z0-9._:@-]{1,64}$")


class ApprovalRefused(ValueError):
    """The approval evidence is missing, malformed, untrusted, expired or does not match the change."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text, what: str) -> bytes:
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError, AttributeError) as exc:
        raise ApprovalRefused(f"{what} is not valid base64") from exc


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(text, what: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ApprovalRefused(f"{what} must look like 2026-01-31T12:00:00Z") from exc


def corpus_sha256(corpus: list[dict]) -> str:
    """Order-independent hash of a COMPLETE corpus snapshot (sorted by chunk_id)."""
    if not isinstance(corpus, list) or not corpus or any(not isinstance(r, dict) or "chunk_id" not in r for r in corpus):
        raise ApprovalRefused("corpus must be a nonempty list of rows with a chunk_id")
    return sha256_json(sorted(corpus, key=lambda r: str(r["chunk_id"])))


def make_subject(*, tenant, entity, attribute, value, proposal_id, revision, corpus) -> dict:
    return {"tenant": tenant, "entity": entity, "attribute": attribute, "value": value,
            "proposal_id": proposal_id, "revision": int(revision), "corpus_sha256": corpus_sha256(corpus)}


def _message(role: str, approver_id: str, key_id: str, subject: dict, issued_at: str, expires_at: str) -> bytes:
    return canonical_bytes({"v": VERSION, "kind": KIND, "role": role, "approver_id": approver_id, "key_id": key_id,
                            "subject_sha256": sha256_json(subject), "issued_at": issued_at, "expires_at": expires_at})


def new_record(subject: dict, *, now: datetime | None = None, valid_for: timedelta = timedelta(days=3)) -> dict:
    if valid_for <= timedelta(0) or valid_for > MAX_VALIDITY:
        raise ApprovalRefused(f"validity must be positive and at most {MAX_VALIDITY.days} days")
    now = now or datetime.now(timezone.utc)
    return {"v": VERSION, "subject": dict(subject), "issued_at": _iso(now), "expires_at": _iso(now + valid_for),
            "approvals": []}


class ApproverSigner:
    """An approver's private key. Lives on the approver's own machine, never on the operator host."""

    def __init__(self, approver_id: str, key_id: str, private_key_b64: str):
        if not _ID.match(approver_id or "") or not _ID.match(key_id or ""):
            raise ValueError("approver_id and key_id must be 1-64 characters of letters, digits and . _ : @ -")
        seed = _unb64(private_key_b64, "private key")
        if len(seed) != 32:
            raise ValueError("private key must be a raw 32-byte Ed25519 seed")
        self.approver_id, self.key_id = approver_id, key_id
        self._key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)

    def __repr__(self) -> str:
        return f"ApproverSigner(approver_id={self.approver_id!r}, key_id={self.key_id!r})"

    @property
    def public_key_b64(self) -> str:
        return _b64(self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))

    def sign(self, record: dict, role: str) -> dict:
        """Return a copy of `record` with this approver's signature added for `role`."""
        if role not in ROLES:
            raise ApprovalRefused(f"role must be one of {ROLES}")
        if any(a.get("role") == role for a in record.get("approvals", [])):
            raise ApprovalRefused(f"the record already has a {role} signature")
        sig = self._key.sign(_message(role, self.approver_id, self.key_id, record["subject"],
                                      record["issued_at"], record["expires_at"]))
        out = json.loads(json.dumps(record))
        out["approvals"].append({"role": role, "approver_id": self.approver_id, "key_id": self.key_id,
                                 "signature": _b64(sig)})
        return out


def generate_approver_keypair() -> tuple[str, str]:
    key = ed25519.Ed25519PrivateKey.generate()
    return (_b64(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                   serialization.NoEncryption())),
            _b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)))


@dataclass(frozen=True)
class VerifiedApproval:
    proposer: str
    reviewer: str
    proposer_key_id: str
    reviewer_key_id: str
    issued_at: str
    expires_at: str
    subject_sha256: str
    evidence_sha256: str


class ApprovalVerifier:
    """Holds approvers' PUBLIC keys and the roles they may sign for."""

    def __init__(self, approvers: dict, revoked=()):
        if not isinstance(approvers, dict) or not approvers:
            raise ValueError("the approver trust store is empty")
        self._approvers: dict[str, dict] = {}
        for approver_id, entry in approvers.items():
            if not _ID.match(approver_id) or not isinstance(entry, dict):
                raise ValueError(f"invalid approver {approver_id!r}")
            roles = entry.get("roles") or []
            if not roles or any(r not in ROLES for r in roles):
                raise ValueError(f"approver {approver_id} needs roles from {ROLES}")
            keys = {}
            for key_id, pub in (entry.get("keys") or {}).items():
                raw = _unb64(pub, f"public key {key_id}")
                if len(raw) != 32 or not _ID.match(key_id):
                    raise ValueError(f"invalid key {key_id!r} for {approver_id}")
                keys[key_id] = (ed25519.Ed25519PublicKey.from_public_bytes(raw), raw)
            if not keys:
                raise ValueError(f"approver {approver_id} has no keys")
            self._approvers[approver_id] = {"roles": set(roles), "keys": keys}
        self.revoked = frozenset(revoked or ())

    def verify(self, record, *, expected_subject: dict, now: datetime | None = None) -> VerifiedApproval:
        now = now or datetime.now(timezone.utc)
        if not isinstance(record, dict) or record.get("v") != VERSION:
            raise ApprovalRefused("approval record is missing or has an unsupported version")
        subject = record.get("subject")
        if not isinstance(subject, dict) or set(subject) != set(SUBJECT_FIELDS):
            raise ApprovalRefused("approval subject is malformed")
        for field in SUBJECT_FIELDS:
            if subject.get(field) != expected_subject.get(field):
                raise ApprovalRefused(f"approval does not cover this change: {field} differs")
        issued, expires = record.get("issued_at"), record.get("expires_at")
        issued_dt, expires_dt = _parse(issued, "issued_at"), _parse(expires, "expires_at")
        if expires_dt <= issued_dt or expires_dt - issued_dt > MAX_VALIDITY:
            raise ApprovalRefused(f"approval validity window must be positive and at most {MAX_VALIDITY.days} days")
        if issued_dt - CLOCK_SKEW > now:
            raise ApprovalRefused("approval is dated in the future")
        if now >= expires_dt:
            raise ApprovalRefused("approval has expired")
        entries = record.get("approvals")
        if not isinstance(entries, list) or len(entries) != 2 or {e.get("role") for e in entries if isinstance(e, dict)} != set(ROLES):
            raise ApprovalRefused("exactly one proposer and one reviewer signature are required")
        verified = {}
        for e in entries:
            role, approver_id, key_id = e.get("role"), e.get("approver_id"), e.get("key_id")
            if not all(isinstance(x, str) for x in (role, approver_id, key_id, e.get("signature"))):
                raise ApprovalRefused("an approval entry is malformed")
            if key_id in self.revoked:
                raise ApprovalRefused(f"key {key_id} is revoked")
            who = self._approvers.get(approver_id)
            if who is None:
                raise ApprovalRefused(f"approver {approver_id} is not in the trust store")
            if role not in who["roles"]:
                raise ApprovalRefused(f"approver {approver_id} may not sign as {role}")
            key = who["keys"].get(key_id)
            if key is None:
                raise ApprovalRefused(f"key {key_id} is not registered for approver {approver_id}")
            try:
                key[0].verify(_unb64(e["signature"], "signature"),
                              _message(role, approver_id, key_id, subject, issued, expires))
            except InvalidSignature as exc:
                raise ApprovalRefused(f"the {role} signature is invalid") from exc
            verified[role] = (approver_id, key_id, key[1])
        p, r = verified["proposer"], verified["reviewer"]
        if p[0] == r[0]:
            raise ApprovalRefused("proposer and reviewer must be different people")
        if p[1] == r[1] or p[2] == r[2]:
            raise ApprovalRefused("proposer and reviewer must sign with different keys")
        return VerifiedApproval(proposer=p[0], reviewer=r[0], proposer_key_id=p[1], reviewer_key_id=r[1],
                                issued_at=issued, expires_at=expires, subject_sha256=sha256_json(subject),
                                evidence_sha256=sha256_json(record))

    def verify_payload(self, payload: dict, *, now: datetime | None = None) -> VerifiedApproval:
        """Re-verify the evidence stored in a queued work's payload against that payload's own fields."""
        record = (payload or {}).get("approval")
        if record is None:
            raise ApprovalRefused("publication has no approval evidence")
        subject = (record or {}).get("subject") or {}
        expected = {"tenant": subject.get("tenant"), "entity": payload.get("entity"),
                    "attribute": payload.get("attribute"), "value": payload.get("corrected_value"),
                    "proposal_id": subject.get("proposal_id"), "revision": subject.get("revision"),
                    "corpus_sha256": corpus_sha256(payload.get("full_vector_snapshot"))}
        return self.verify(record, expected_subject=expected, now=now)


def approver_verifier_from_env(environ=None) -> ApprovalVerifier | None:
    path = (os.environ if environ is None else environ).get(TRUST_ENV)
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{TRUST_ENV} ({path}) is missing or not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{TRUST_ENV} must be a JSON object")
    return ApprovalVerifier(data.get("approvers", {}), data.get("revoked", []))


# ------------------------------------------------------------------------------ approver-side tool


def _cmd_subject(a) -> dict:
    corpus = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    subject = make_subject(tenant=a.tenant, entity=a.entity, attribute=a.attribute, value=a.value,
                           proposal_id=a.proposal_id, revision=a.revision, corpus=corpus)
    record = new_record(subject, valid_for=timedelta(days=a.valid_days))
    Path(a.out).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {"ok": True, "record": a.out, "corpus_sha256": subject["corpus_sha256"], "expires_at": record["expires_at"]}


def _cmd_sign(a) -> dict:
    key = json.loads(Path(a.key_file).read_text(encoding="utf-8"))
    signer = ApproverSigner(key["approver_id"], key["key_id"], key["private_key"])
    record = json.loads(Path(a.record).read_text(encoding="utf-8"))
    corpus = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    if record["subject"]["corpus_sha256"] != corpus_sha256(corpus):
        raise ApprovalRefused("the corpus file does not match the hash in the record: refusing to sign what you have not seen")
    signed = signer.sign(record, a.role)
    Path(a.record).write_text(json.dumps(signed, indent=2), encoding="utf-8")
    return {"ok": True, "signed_as": a.role, "approver_id": signer.approver_id, "signatures": len(signed["approvals"])}


def _cmd_verify(a) -> dict:
    verifier = approver_verifier_from_env()
    if verifier is None:
        raise ApprovalRefused(f"{TRUST_ENV} is not set")
    record = json.loads(Path(a.record).read_text(encoding="utf-8"))
    corpus = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    s = record.get("subject", {})
    expected = make_subject(tenant=s.get("tenant"), entity=s.get("entity"), attribute=s.get("attribute"),
                            value=s.get("value"), proposal_id=s.get("proposal_id"), revision=s.get("revision", 0),
                            corpus=corpus)
    v = verifier.verify(record, expected_subject=expected)
    return {"ok": True, "proposer": v.proposer, "reviewer": v.reviewer, "expires_at": v.expires_at}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="amc_publication.approvals31", description="Approver-side tool: build, sign and check approval records.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("subject", help="create an unsigned approval record for a change")
    for f in ("tenant", "entity", "attribute", "value", "proposal-id", "corpus", "out"):
        s.add_argument("--" + f, required=True)
    s.add_argument("--revision", type=int, default=1)
    s.add_argument("--valid-days", type=int, default=3)
    g = sub.add_parser("sign", help="add YOUR signature (your own key file) after checking the corpus yourself")
    g.add_argument("--record", required=True)
    g.add_argument("--corpus", required=True)
    g.add_argument("--key-file", required=True)
    g.add_argument("--role", required=True, choices=ROLES)
    v = sub.add_parser("verify", help="check a record against the trust store")
    v.add_argument("--record", required=True)
    v.add_argument("--corpus", required=True)
    args = parser.parse_args(argv)
    try:
        out = {"subject": _cmd_subject, "sign": _cmd_sign, "verify": _cmd_verify}[args.cmd](args)
    except (ApprovalRefused, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 2
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
