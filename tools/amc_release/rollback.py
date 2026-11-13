"""GATE05 evidence-only rollback invariant evaluator.

Checks the coherence of observations independently gathered BEFORE publication,
AFTER canary publication and AFTER rollback. Never performs a rollback. Even
PASS does not authenticate the observer; the raw records must be anchored in a
separate immutable CI/staging evidence store and reviewed by a real operator.
"""
from __future__ import annotations
from .common import utc, require_sha, DIGEST_PATTERN


class RollbackEvidenceError(ValueError):
    pass


def evaluate(document: dict, *, expected_sha: str) -> dict:
    require_sha(expected_sha)
    if not isinstance(document, dict):
        raise RollbackEvidenceError('rollback observations must be a JSON object')
    reasons = []
    if document.get('sha') != expected_sha:
        reasons.append('SHA_MISMATCH')
    if not document.get('tenant') or not document.get('work_id'):
        reasons.append('TENANT_OR_WORK_REQUIRED')
    if document.get('environment') != 'staging' or document.get('source') != 'live':
        reasons.append('LIVE_STAGING_OBSERVATIONS_REQUIRED')
    states = document.get('observations')
    if not isinstance(states, list) or len(states) != 3 or not all(isinstance(x, dict) for x in states) or [x.get('phase') for x in states] != ['before','published','after_rollback']:
        reasons.append('ORDERED_THREE_PHASE_OBSERVATIONS_REQUIRED')
        return {'status':'BLOCK','reasons':reasons,'sha':expected_sha}
    try:
        observed_times = [utc(x['at']) for x in states]
        if not (observed_times[0] < observed_times[1] < observed_times[2]):
            reasons.append('NONMONOTONIC_OBSERVATION_TIMES')
    except (KeyError,ValueError,TypeError):
        reasons.append('INVALID_OBSERVATION_TIME')
    for state in states:
        if state.get('tenant') != document.get('tenant') or state.get('work_id') != document.get('work_id'):
            reasons.append('OBSERVATION_TENANT_WORK_MISMATCH')
        for key in ('graph_sha256','generation_sha256','serving_reader_generation_sha256'):
            if not isinstance(state.get(key),str) or not DIGEST_PATTERN.fullmatch(state[key]):
                reasons.append('MISSING_CONTENT_HASH_'+key)
        if state.get('verified_readback') is not True:
            reasons.append('INDEPENDENT_READBACK_MISSING')
    before, pub, after = states
    if (before.get('graph_sha256'),before.get('generation_sha256')) == (pub.get('graph_sha256'),pub.get('generation_sha256')):
        reasons.append('CANARY_PUBLICATION_DID_NOT_CHANGE_EFFECTS')
    for key in ('graph_sha256','generation_sha256'):
        if before.get(key) != after.get(key):
            reasons.append('ROLLBACK_DID_NOT_RESTORE_'+key)
    for state in states:
        if state.get('generation_sha256') != state.get('serving_reader_generation_sha256'):
            reasons.append('SERVING_READER_NOT_CONVERGED')
    if document.get('rollback_receipt_verified') is not True:
        reasons.append('ROLLBACK_RECEIPT_NOT_VERIFIED')
    return {'status': 'PASS' if not reasons else 'BLOCK', 'sha': expected_sha,
            'reasons': sorted(set(reasons)), 'tenant': document.get('tenant'),
            'work_id': document.get('work_id'), 'mode': 'evidence_consistency_only',
            'authenticity_requires_external_evidence': True}
