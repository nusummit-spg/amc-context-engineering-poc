"""Byte-level source manifests; string-format validation is insufficient."""
from hashlib import sha256
from pathlib import Path
from .types import VerificationFailed


def verify_source_manifest(source_path: str | Path, *, expected_sha256: str,
                           chunks: list[dict], expected_byte_count: int | None = None) -> dict:
    """Compute actual byte/chunk hashes; chunks cover the full file without gaps.

    Each chunk has {start: int, end: int, sha256: str}. No untrusted source
    content is accepted merely because its advertised digest is 64 chars.
    """
    data = Path(source_path).read_bytes()
    observed = sha256(data).hexdigest()
    if observed != expected_sha256:
        raise VerificationFailed("source file content hash differs from manifest")
    if expected_byte_count is not None and len(data) != expected_byte_count:
        raise VerificationFailed("source byte count differs from manifest")
    last = 0
    for c in chunks:
        start, end = c["start"], c["end"]
        if not (isinstance(start, int) and isinstance(end, int) and last == start and end > start and end <= len(data)):
            raise VerificationFailed("manifest chunks overlap, have gaps or exceed source")
        if sha256(data[start:end]).hexdigest() != c["sha256"]:
            raise VerificationFailed("manifest chunk data differs from source bytes")
        last = end
    if last != len(data):
        if data or chunks:
            raise VerificationFailed("manifest chunk coverage is incomplete")
    return {"sha256": observed, "bytes": len(data), "chunks": len(chunks)}
