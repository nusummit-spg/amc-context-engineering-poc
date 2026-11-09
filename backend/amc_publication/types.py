"""Strict value types and canonical SHA-256 helpers for durable publication."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class PublicationError(RuntimeError):
    pass


class Conflict(PublicationError):
    pass


class LeaseLost(PublicationError):
    pass


class VerificationFailed(PublicationError):
    pass


@dataclass(frozen=True)
class Claim:
    work_id: str
    tenant: str
    owner: str
    epoch: int
    payload: dict
    fence: int
    mode: str = "publish"


@dataclass(frozen=True)
class Generation:
    generation_id: str
    digest: str
    count: int
