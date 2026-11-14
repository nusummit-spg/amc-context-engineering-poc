"""Fail-closed Wave 2.3 UAT / release gate evaluation.

Inputs are assertions with external evidence, not verified facts by themselves.
The evaluator validates consistency and bounded properties; operators must
provide independent links and signed signoffs for UAT and production releases.
"""
from __future__ import annotations
from datetime import timedelta
import hmac
import hashlib
from .common import canonical
from pathlib import Path
from .common import require_sha, utc, safe_relative, hash_file, DIGEST_PATTERN
from .ledger import verify as verify_ledger

GATES = ('GATE01', 'GATE05', 'GATE06', 'GATE07', 'FB05', 'FB06', 'CI07', 'E05', 'CI08')


def _positive(d: dict, keys: tuple[str, ...]) -> bool:
    return all(type(d.get(k)) is int and d[k] > 0 for k in keys)


def _gate_details(gate: str, d: dict, *, sha: str, root: Path, now=None) -> list[str]:
    errors = []
    if gate == 'GATE01':
        if d.get('environment') != 'staging' or d.get('mode') != 'live':
            errors.append('LIVE_STAGING_INTEGRATION_REQUIRED')
        if not _positive(d, ('graph_readbacks', 'faiss_reload_probes', 'rollback_drills', 'feedback_roundtrips')):
            errors.append('MISSING_CROSS_STORE_PROBES')
        if d.get('cross_tenant_violations') != 0 or d.get('synthetic_receipts') != 0:
            errors.append('TENANT_OR_RECEIPT_INVARIANT_FAILED')
    elif gate == 'GATE05':
        if d.get('environment') != 'staging' or d.get('mode') != 'live':
            errors.append('REAL_CANARY_REQUIRED')
        if not _positive(d, ('read_only_probes', 'duration_minutes')) or d['duration_minutes'] < 30:
            errors.append('CANARY_DURATION_OR_PROBES_INSUFFICIENT')
        if d.get('failures') != 0 or d.get('rollback_probe') != 'PASS':
            errors.append('CANARY_OR_ROLLBACK_NOT_VERIFIED')
        from .rollback import evaluate as check_rollback
        try:
            rollback_result = check_rollback(d['rollback_observations'], expected_sha=sha)
            if rollback_result['status'] != 'PASS':
                errors.append('ROLLBACK_CROSS_STORE_PROOF_INVALID')
        except (KeyError, TypeError, ValueError):
            errors.append('ROLLBACK_CROSS_STORE_PROOF_MISSING')
    elif gate == 'GATE06':
        try:
            ledger_path = safe_relative(root, d['ledger_file'])
            result = verify_ledger(ledger_path, expected_sha=sha)
            if result['final_sha256'] != d.get('ledger_sha256') or result['events'] < 1:
                errors.append('LEDGER_HASH_OR_COUNT_MISMATCH')
            if d.get('anchor_type') not in {'github_artifact', 'external_signing'}:
                errors.append('NO_EXTERNAL_LEDGER_ANCHOR')
        except (OSError, ValueError, KeyError, TypeError):
            errors.append('INVALID_EVIDENCE_LEDGER')
    elif gate == 'GATE07':
        reviewers = d.get('reviewers', [])
        if d.get('decision') != 'ACCEPT_UAT' or d.get('scope') != 'uat':
            errors.append('EXPLICIT_UAT_SIGNOFF_REQUIRED')
        if not isinstance(reviewers, list) or len(reviewers) < 2 or any(not isinstance(x, str) or not x for x in reviewers) or len(set(reviewers)) != len(reviewers):
            errors.append('TWO_DISTINCT_REVIEWERS_REQUIRED')
        if d.get('signatures_verified') is not True or d.get('independent_review') is not True:
            errors.append('EXTERNALLY_VERIFIED_SIGNOFF_REQUIRED')
    elif gate == 'FB05':
        if d.get('thresholds_approved') is not True:
            errors.append('SLO_LIMITS_NOT_APPROVED')
        limits = d.get('limits') or {}
        try:
            max_p95_ms = float(limits['max_p95_ms'])
            max_error_rate = float(limits['max_error_rate'])
            if not (max_p95_ms > 0 and 0 <= max_error_rate < 1):
                raise ValueError('invalid limits')
        except (KeyError, ValueError, TypeError):
            max_p95_ms, max_error_rate = -1, -1
            errors.append('SLO_LIMITS_MISSING_OR_INVALID')
        windows = d.get('windows')
        if not isinstance(windows, list) or len(windows) != 2 or not all(isinstance(x, dict) for x in windows) or {x.get('window_minutes') for x in windows} != {60, 1440}:
            errors.append('ONE_HOUR_AND_DAY_SLO_WINDOWS_REQUIRED')
        else:
            tenants = {x.get('tenant') for x in windows if isinstance(x, dict)}
            if len(tenants) != 1 or None in tenants:
                errors.append('MIXED_OR_MISSING_SLO_TENANT')
            for x in windows:
                try:
                    start, end = utc(x['window_start']), utc(x['window_end'])
                    if end <= start or abs((end - start).total_seconds() - x['window_minutes'] * 60) > 1:
                        errors.append('INVALID_SLO_WINDOW_BOUNDARIES')
                    if now is None or end > now or now - end > timedelta(minutes=5):
                        errors.append('STALE_SLO_WINDOW')
                except (KeyError, ValueError, TypeError):
                    errors.append('MISSING_SLO_TIME_BOUNDS')
                if x.get('status') != 'PASS' or x.get('provenance') != 'live' or x.get('environment') != 'staging':
                    errors.append('UNVERIFIED_SLO_WINDOW')
                min_required = 1000 if x.get('window_minutes') == 1440 else 100
                if type(x.get('samples')) is not int or x['samples'] < min_required or x.get('bucket_coverage', 0) < .95:
                    errors.append('SLO_WINDOW_INSUFFICIENT_COVERAGE')
                try:
                    p95, rate = float(x['p95_ms']), float(x['error_rate'])
                    from math import isfinite
                    if not isfinite(p95) or not isfinite(rate) or p95 < 0 or not 0 <= rate < 1:
                        raise ValueError('invalid measured SLO')
                    if p95 > max_p95_ms or rate > max_error_rate:
                        errors.append('MEASURED_SLO_LIMIT_EXCEEDED')
                except (KeyError, ValueError, TypeError):
                    errors.append('MISSING_MEASURED_SLO')
    elif gate == 'FB06':
        if d.get('runner') != 'playwright' or d.get('environment') != 'staging':
            errors.append('REAL_BROWSER_STAGING_TESTS_REQUIRED')
        if not {'chromium', 'firefox'}.issubset(set(d.get('browsers', []))):
            errors.append('BROWSER_COVERAGE_MISSING')
        if not _positive(d, ('scenarios',)) or d.get('failed') != 0 or d.get('skipped') != 0:
            errors.append('BROWSER_SCENARIOS_INCOMPLETE')
    elif gate == 'CI07':
        results = d.get('platforms')
        if not isinstance(results, dict) or not all(results.get(p) == 'PASS' for p in ('Windows', 'Linux')):
            errors.append('LINUX_WINDOWS_MATRIX_INCOMPLETE')
        suites = d.get('suites')
        if (not isinstance(suites, dict) or
            any(not all(suites.get(suite, {}).get(platform) == 'PASS' for platform in ('Linux', 'Windows'))
                for suite in ('amc_release', 'backend_contracts'))):
            errors.append('BACKEND_CROSS_PLATFORM_CONTRACTS_MISSING')
        if d.get('required_skips') != 0:
            errors.append('REQUIRED_MATRIX_TESTS_SKIPPED')
    elif gate == 'E05':
        jobs = d.get('workflows')
        required = ('AMC Publication V2 Contract Tests', 'AMC Quality V2 Contract Tests', 'AMC Assurance Pipeline', 'AMC Release Verification Matrix')
        if not isinstance(jobs, dict) or not all(jobs.get(j, {}).get('sha') == sha and jobs[j].get('conclusion') == 'success' and jobs[j].get('required_skips') == 0 and type(jobs[j].get('run_id')) is int and jobs[j]['run_id'] > 0 and type(jobs[j].get('job_count')) is int and jobs[j]['job_count'] > 0 for j in required):
            errors.append('EXACT_SHA_CI_CHECKS_INCOMPLETE')
    elif gate == 'CI08':
        report = d.get('reconciliation')
        if not isinstance(report, dict) or report.get('sha') != sha or report.get('status') != 'PASS' or report.get('missing') or report.get('reports', 0) < 4:
            errors.append('TEST_COUNT_RECONCILIATION_INCOMPLETE')
        else:
            identity = report.get('same_suite_per_platform_test_identity_sha256')
            if not isinstance(identity, dict) or any(
                not isinstance(identity.get(suite), list) or len(identity[suite]) != 2 or
                not all(isinstance(x, str) and DIGEST_PATTERN.fullmatch(x) for x in identity[suite]) or
                identity[suite][0] != identity[suite][1]
                for suite in ('amc_release', 'backend_contracts')
            ):
                errors.append('TEST_IDENTITY_RECONCILIATION_INCOMPLETE')
    return errors


def attest(document: dict, *, key: str, attestor: str) -> dict:
    """Explicit external-key attestation; only after independent evidence review.

    This is HMAC (shared-secret authentication), NOT a two-party digital
    signature. Store key outside the repository, never in a JSON artifact.
    """
    if len(key) < 32 or not attestor.strip():
        raise ValueError('reviewer identity and >=32-character external key required')
    unsigned = {k: v for k, v in document.items() if k != 'attestation'}
    auth = {'attestor': attestor}
    sig = hmac.new(key.encode('utf-8'), canonical({'payload': unsigned, 'attestor': attestor}), hashlib.sha256).hexdigest()
    return {**unsigned, 'attestation': {**auth, 'hmac_sha256': sig}}


def _valid_attestation(document: dict, *, key: str | None) -> bool:
    auth = document.get('attestation')
    if not key or len(key) < 32 or not isinstance(auth, dict) or not isinstance(auth.get('attestor'), str):
        return False
    unsigned = {k: v for k, v in document.items() if k != 'attestation'}
    expected = hmac.new(key.encode('utf-8'), canonical({'payload': unsigned, 'attestor': auth['attestor']}), hashlib.sha256).hexdigest()
    signature = auth.get('hmac_sha256')
    return isinstance(signature, str) and hmac.compare_digest(expected, signature)


def evaluate(document: dict, *, root: Path, now: str, verification_key: str | None = None) -> dict:
    """Returns BLOCK until every gate has credible scoped evidence on exact SHA."""
    sha = require_sha(document['sha'])
    current = utc(now)
    if document.get('schema') != 'amc-uat-evidence-v2.3':
        raise ValueError('unrecognized UAT evidence schema')
    evidence = document.get('evidence')
    if not isinstance(evidence, list):
        raise ValueError('evidence array required')
    seen = set()
    findings = {}
    for item in evidence:
        if not isinstance(item, dict) or item.get('gate') not in GATES:
            continue
        gate = item['gate']
        if gate in seen:
            findings[gate] = ['DUPLICATE_GATE_EVIDENCE']
            continue
        seen.add(gate)
        errs = []
        if item.get('sha') != sha:
            errs.append('EVIDENCE_COMMIT_MISMATCH')
        if item.get('status') != 'PASS' or item.get('verified') is not True:
            errs.append('EVIDENCE_NOT_VERIFIED_PASS')
        if item.get('source') not in {'ci', 'live', 'manual'}:
            errs.append('UNTRUSTED_EVIDENCE_SOURCE')
        try:
            time = utc(item['at'])
            if current < time or current - time > timedelta(days=7):
                errs.append('STALE_OR_FUTURE_EVIDENCE')
        except (ValueError, KeyError, TypeError):
            errs.append('MISSING_EVIDENCE_TIMESTAMP')
        detail = item.get('details')
        if not isinstance(detail, dict):
            errs.append('MISSING_EVIDENCE_DETAILS')
        else:
            errs.extend(_gate_details(gate, detail, sha=sha, root=root, now=current))
        # A cryptographic file digest and external location are mandatory for every gate.
        artifact = item.get('artifact')
        artifact_digest = item.get('artifact_sha256')
        if not isinstance(artifact, str) or not isinstance(artifact_digest, str) or not DIGEST_PATTERN.fullmatch(artifact_digest):
            errs.append('MISSING_EVIDENCE_ARTIFACT_HASH')
        else:
            try:
                f = safe_relative(root, artifact)
                if hash_file(f) != artifact_digest:
                    errs.append('EVIDENCE_ARTIFACT_BYTES_MISMATCH')
            except (OSError, ValueError):
                errs.append('EVIDENCE_ARTIFACT_UNREADABLE')
        findings[gate] = sorted(set(errs))
    for gate in GATES:
        if gate not in findings:
            findings[gate] = ['MISSING_GATE_EVIDENCE']
    if not _valid_attestation(document, key=verification_key):
        findings.setdefault('ATTESTATION', []).append('EXTERNAL_HMAC_NOT_VERIFIED')
    passed = sorted(g for g, errs in findings.items() if not errs)
    blocked = {g: errs for g, errs in findings.items() if errs}
    # Even a fully green UAT package does not authorize production deployment.
    return {'sha': sha, 'state': 'UAT_READY' if not blocked else 'BLOCKED',
            'production_release': 'REQUIRES_SEPARATE_APPROVAL',
            'passing_gates': passed, 'blocked_gates': blocked,
            'total_gates': len(GATES), 'verified_gate_count': sum(g in GATES for g in passed)}
