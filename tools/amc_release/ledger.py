"""Tamper-evident evidence ledger. SHA chain is NOT an identity signature.

Anchor the resulting final SHA outside the artifact store (e.g. authenticated
CI artifact or a signed release record) to defend against entire-ledger rewrites.
"""
from __future__ import annotations
import json
from pathlib import Path
from .common import canonical, digest, require_sha, utc

GENESIS = '0' * 64
ALLOWED_STATUSES = {'PASS', 'FAIL', 'BLOCK', 'UNKNOWN', 'NOT_RUN'}


class LedgerError(ValueError):
    pass


def _content_entry(sequence: int, prior: str, event: dict) -> dict:
    if not isinstance(event, dict):
        raise LedgerError('evidence event must be an object')
    for name in ('id', 'sha', 'gate', 'status', 'time', 'source', 'artifact_sha256'):
        if not isinstance(event.get(name), str) or not event[name]:
            raise LedgerError(f'missing evidence field: {name}')
    require_sha(event['sha'])
    utc(event['time'])
    if event['status'] not in ALLOWED_STATUSES:
        raise LedgerError('unrecognized evidence status')
    if event['source'] not in {'ci', 'live', 'manual', 'local', 'simulation'}:
        raise LedgerError('evidence source must be classified')
    from .common import DIGEST_PATTERN
    if not DIGEST_PATTERN.fullmatch(event['artifact_sha256']):
        raise LedgerError('artifact SHA256 must be a 64-character digest')
    if sequence < 1:
        raise LedgerError('sequence starts at 1')
    core = {'sequence': sequence, 'prev_sha256': prior, 'event': event}
    return {**core, 'entry_sha256': digest(core)}


def verify(path: str | Path, *, expected_sha: str | None = None) -> dict:
    f = Path(path)
    previous = GENESIS
    count = 0
    seen = set()
    with f.open('r', encoding='utf-8') as reader:
        for line in reader:
            if not line.strip():
                raise LedgerError('blank ledger line is not permitted')
            try:
                record = json.loads(line)
            except ValueError as ex:
                raise LedgerError('invalid JSONL ledger line') from ex
            count += 1
            if not isinstance(record, dict) or record.get('sequence') != count or record.get('prev_sha256') != previous:
                raise LedgerError('ledger sequence / previous hash mismatch')
            expected = _content_entry(count, previous, record.get('event'))
            if record != expected:
                raise LedgerError('ledger content/hash mismatch')
            if expected_sha is not None and record['event']['sha'] != require_sha(expected_sha):
                raise LedgerError('evidence event belongs to another commit SHA')
            if record['event']['id'] in seen:
                raise LedgerError('duplicate evidence event ID')
            seen.add(record['event']['id'])
            previous = expected['entry_sha256']
    if count == 0:
        raise LedgerError('ledger must contain evidence')
    return {'events': count, 'final_sha256': previous}


def create(path: str | Path, events: list[dict]) -> dict:
    """Exclusive write: never overwrite an existing audited ledger."""
    if not events:
        raise LedgerError('empty ledger forbidden')
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = GENESIS
    seen = set()
    entries = []
    for index, event in enumerate(events, 1):
        if event.get('id') in seen:
            raise LedgerError('duplicate event ID')
        seen.add(event.get('id'))
        item = _content_entry(index, prev, event)
        entries.append(item)
        prev = item['entry_sha256']
    with p.open('x', encoding='utf-8', newline='\n') as f:
        for item in entries:
            f.write(canonical(item).decode('utf-8') + '\n')
        f.flush()
        import os
        os.fsync(f.fileno())
    return verify(p)
