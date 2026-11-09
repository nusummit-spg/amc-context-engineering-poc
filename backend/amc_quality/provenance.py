"""Complete, externally anchored contributor ledger for financial answers.

No [:50] truncation. The returned digest anchors all JSONL bytes, but is NOT
an HMAC/signature; store digest in separate durable audit store to detect edits.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Iterable
from uuid import uuid4


class ProvenanceError(ValueError):
    pass


def _line(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class LedgerReceipt:
    dataset_version: str
    query_id: str
    contributors: int
    digest_sha256: str
    path: str


def write_ledger(path: str | Path, *, dataset_version: str, query_id: str,
                 source_row_ids: Iterable[str], allow_replace: bool = False) -> LedgerReceipt:
    if not dataset_version or not query_id:
        raise ProvenanceError("dataset_version and query_id are required")
    destination = Path(path)
    if destination.exists() and not allow_replace:
        raise FileExistsError("ledger already exists; append-only evidence requires new filename")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
    h = sha256()
    count = 0
    try:
        with temp.open("wb") as f:
            def emit(record):
                b = _line(record)
                f.write(b)
                h.update(b)
            emit({"type": "header", "schema": "amc.contributor-ledger.v2", "version": dataset_version,
                  "query_id": query_id})
            for row_id in source_row_ids:
                if not isinstance(row_id, str) or not re.fullmatch(r"[0-9a-f]{64}", row_id):
                    raise ProvenanceError("source_row_id must be lowercase SHA-256, no missing evidence")
                emit({"type": "contributor", "index": count, "source_row_id": row_id})
                count += 1
            emit({"type": "footer", "contributors": count})
            f.flush()
            os.fsync(f.fileno())
        digest = h.hexdigest()
        os.replace(temp, destination)
        return LedgerReceipt(dataset_version, query_id, count, digest, str(destination))
    finally:
        temp.unlink(missing_ok=True)


def verify_ledger(path: str | Path, *, expected_sha256: str,
                  expected_dataset_version: str | None = None,
                  expected_query_id: str | None = None) -> LedgerReceipt:
    """Verify every byte, schema, sequence, contributor and count against anchor."""
    p = Path(path)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ProvenanceError("valid externally anchored SHA-256 is required")
    h = sha256()
    count = 0
    header = None
    footer = None
    try:
        with p.open("rb") as f:
            for raw in f:
                h.update(raw)
                try:
                    obj = json.loads(raw)
                except ValueError as exc:
                    raise ProvenanceError("invalid JSONL evidence") from exc
                if not isinstance(obj, dict):
                    raise ProvenanceError("invalid evidence record")
                typ = obj.get("type")
                if header is None:
                    if typ != "header" or obj.get("schema") != "amc.contributor-ledger.v2":
                        raise ProvenanceError("invalid ledger header")
                    header = obj
                elif footer is not None:
                    raise ProvenanceError("data after footer")
                elif typ == "contributor":
                    if obj.get("index") != count or not isinstance(obj.get("source_row_id"), str) or not re.fullmatch(r"[0-9a-f]{64}", obj["source_row_id"]):
                        raise ProvenanceError("invalid/missing contributor or sequence")
                    count += 1
                elif typ == "footer":
                    footer = obj
                else:
                    raise ProvenanceError("unknown ledger record type")
    except OSError as exc:
        raise ProvenanceError("ledger unreadable") from exc
    if not header or not footer or footer.get("contributors") != count:
        raise ProvenanceError("ledger incomplete or count mismatch")
    if h.hexdigest() != expected_sha256:
        raise ProvenanceError("ledger content digest differs from external anchor")
    if expected_dataset_version is not None and header.get("version") != expected_dataset_version:
        raise ProvenanceError("dataset version mismatch")
    if expected_query_id is not None and header.get("query_id") != expected_query_id:
        raise ProvenanceError("query identity mismatch")
    return LedgerReceipt(str(header.get("version")), str(header.get("query_id")), count, h.hexdigest(), str(p))
