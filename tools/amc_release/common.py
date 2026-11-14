"""Canonical JSON, SHA and timestamp primitives used by assurance components."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

SHA_PATTERN = re.compile(r'^[0-9a-f]{40}$')
DIGEST_PATTERN = re.compile(r'^[0-9a-f]{64}$')


def require_sha(value: str) -> str:
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise ValueError('exact 40-character lowercase Git commit SHA required')
    return value


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('timestamp string with timezone required')
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError) as exc:
        raise ValueError('invalid ISO timestamp') from exc
    if d.tzinfo is None:
        raise ValueError('UTC or timezone-aware timestamp required')
    return d.astimezone(timezone.utc)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def safe_relative(root: Path, relative: str) -> Path:
    """Refuse absolute paths and '..' escapes, including symlink escapes."""
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not relative.strip():
        raise ValueError('evidence file path must be relative within evidence root')
    candidate = (root / p).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as ex:
        raise ValueError('evidence path escapes root') from ex
    return candidate
