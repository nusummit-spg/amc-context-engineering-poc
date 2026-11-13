"""Exact-SHA JUnit test accounting with cross-platform *identity* reconciliation.

Unlike totals-only accounting, this rejects renamed/replaced tests that merely
preserve the same counts. JUnit XML is untrusted until artifact provenance is
independently established by the exact-SHA CI collector.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from .common import require_sha, hash_file


class CountError(ValueError):
    pass


def _declared_count(root: ET.Element, key: str) -> int | None:
    """Validate available aggregate JUnit declarations against actual cases."""
    if key not in root.attrib:
        return None
    try:
        n = int(root.attrib[key])
    except (ValueError, TypeError) as exc:
        raise CountError(f'invalid declared JUnit {key}') from exc
    if n < 0:
        raise CountError(f'negative declared JUnit {key}')
    return n


def from_junit(path: str | Path, sha: str, os_name: str, suite: str) -> dict:
    require_sha(sha)
    if os_name not in {'Windows', 'Linux'}:
        raise CountError('unsupported CI platform')
    if not isinstance(suite, str) or not suite.strip():
        raise CountError('suite label required')
    f = Path(path)
    if f.stat().st_size > 100 * 1024 * 1024:
        raise CountError('JUnit artifact larger than 100MB')
    root = ET.parse(f).getroot()
    if root.tag not in {'testsuite', 'testsuites'}:
        raise CountError('JUnit root must be testsuite or testsuites')
    cases = root.findall('.//testcase')
    if not cases:
        raise CountError('JUnit report has no test cases')
    passed = failed = errors = skipped = 0
    identities: set[str] = set()
    for c in cases:
        identity = (c.get('classname') or '').strip() + '::' + (c.get('name') or '').strip()
        if identity == '::' or identity in identities:
            raise CountError('missing or duplicate JUnit test identity')
        identities.add(identity)
        if c.find('failure') is not None:
            failed += 1
        elif c.find('error') is not None:
            errors += 1
        elif c.find('skipped') is not None:
            skipped += 1
        else:
            passed += 1
    observed = {'tests': len(cases), 'failures': failed, 'errors': errors, 'skipped': skipped}
    for k, v in observed.items():
        declared = _declared_count(root, k)
        if declared is not None and declared != v:
            raise CountError(f'JUnit summary {k} disagrees with testcase count')
    # For nested <testsuites>, each direct child declaration is also authoritative.
    if root.tag == 'testsuites':
        for sub in root.findall('testsuite'):
            sub_cases = sub.findall('.//testcase')
            for key, value in (('tests', len(sub_cases)),
                               ('failures', sum(c.find('failure') is not None for c in sub_cases)),
                               ('errors', sum(c.find('error') is not None for c in sub_cases)),
                               ('skipped', sum(c.find('skipped') is not None for c in sub_cases))):
                declared = _declared_count(sub, key)
                if declared is not None and declared != value:
                    raise CountError(f'JUnit nested suite {key} mismatch')
    identity_digest = hashlib.sha256(('\n'.join(sorted(identities)) + '\n').encode('utf-8')).hexdigest()
    return {'sha': sha, 'os': os_name, 'suite': suite, 'passed': passed,
            'failed': failed, 'errors': errors, 'skipped': skipped,
            'collected': len(cases), 'test_identity_sha256': identity_digest,
            'report_sha256': hash_file(f),
            'status': 'PASS' if not (failed or errors or skipped) else 'FAIL'}


def reconcile(reports: list[dict], sha: str, required: list[tuple[str, str]],
              historical_total: int | None = None) -> dict:
    require_sha(sha)
    if not isinstance(reports, list):
        raise CountError('report list required')
    reasons = []
    indexed: dict[tuple[str, str], dict] = {}
    for report in reports:
        if not isinstance(report, dict):
            raise CountError('JUnit normalized report must be an object')
        if report.get('sha') != sha:
            reasons.append('STALE_OR_MIXED_SHA')
        key = (report.get('os'), report.get('suite'))
        if key in indexed:
            reasons.append('DUPLICATE_OS_SUITE_REPORT')
        indexed[key] = report
        if report.get('status') != 'PASS' or any(report.get(x, 0) for x in ('failed', 'errors', 'skipped')) or type(report.get('collected')) is not int or report['collected'] <= 0:
            reasons.append('FAILED_SKIPPED_OR_EMPTY_SUITE')
        if not report.get('test_identity_sha256'):
            reasons.append('MISSING_TEST_IDENTITY_HASH')
    missing = sorted(set(required) - set(indexed))
    if missing:
        reasons.append('MISSING_REQUIRED_OS_SUITE')
    by_suite = {}
    for (os_name, suite), data in indexed.items():
        by_suite.setdefault(suite, []).append(data)
    for items in by_suite.values():
        if len({i.get('collected') for i in items}) > 1:
            reasons.append('CROSS_OS_COUNT_DRIFT')
        if len({i.get('test_identity_sha256') for i in items}) > 1:
            reasons.append('CROSS_OS_TEST_IDENTITY_DRIFT')
    observed_total = sum(r['collected'] for r in reports if type(r.get('collected')) is int)
    return {'sha': sha, 'status': 'PASS' if not reasons else 'FAIL',
            'reasons': sorted(set(reasons)),
            'required': [{'os': a, 'suite': b} for a, b in required],
            'missing': [{'os': a, 'suite': b} for a, b in missing],
            'observed_total_across_runs': observed_total,
            'historical_total_comparison_only': historical_total,
            'same_suite_per_platform_counts': {suite: [x.get('collected') for x in reports] for suite, reports in by_suite.items()},
            'same_suite_per_platform_test_identity_sha256': {suite: [x.get('test_identity_sha256') for x in reports] for suite, reports in by_suite.items()},
            'reports': len(reports)}
