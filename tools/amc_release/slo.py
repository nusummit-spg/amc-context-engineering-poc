"""Compute observed request SLOs from real timestamped events, never invented uptime.

An event log cannot prove availability in intervals with no traffic; those
windows are UNKNOWN, not PASS. Prometheus exporters should provide measured
values and collection provenance before a release can be authorized.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from math import ceil
from .common import utc


class SLOError(ValueError):
    pass


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = ceil(p * len(ordered)) - 1
    return ordered[max(0, min(len(ordered) - 1, idx))]


def evaluate(events: list[dict], *, tenant: str, now: str,
             minutes: int = 60, bucket_minutes: int = 5,
             min_samples: int = 100, coverage: float = .95,
             max_error_rate: float = .01, max_p95_ms: float = 2000,
             environment: str = 'unknown', provenance: str = 'unknown') -> dict:
    if not tenant or minutes <= 0 or 60 * 24 * 7 < minutes:
        raise SLOError('tenant and bounded positive window required')
    if bucket_minutes <= 0 or minutes % bucket_minutes:
        raise SLOError('bucket minutes must evenly divide window')
    end = utc(now)
    start = end - timedelta(minutes=minutes)
    good, invalid, future = [], 0, 0
    for e in events:
        if not isinstance(e, dict) or e.get('tenant') != tenant:
            continue
        try:
            t = utc(e['timestamp'])
            latency = float(e['latency_ms'])
            status = int(e['status_code'])
            import math
            if not math.isfinite(latency) or latency < 0 or status < 100 or status > 599:
                raise ValueError('invalid request sample')
        except (KeyError, ValueError, TypeError):
            invalid += 1
            continue
        if t > end:
            future += 1
        elif start <= t <= end:
            good.append((t, latency, status))
    bucket_count = minutes // bucket_minutes
    filled = {min(bucket_count - 1, int((t - start).total_seconds() // (bucket_minutes * 60))) for t, _, _ in good}
    observed_coverage = len(filled) / bucket_count
    error_rate = sum(status >= 500 for _, _, status in good) / len(good) if good else None
    p95 = _percentile([latency for _, latency, _ in good], .95) if good else None
    reasons = []
    if environment != 'staging' or provenance != 'live':
        reasons.append('NONLIVE_OR_UNTRUSTED_TELEMETRY')
    if invalid or future:
        reasons.append('INVALID_OR_FUTURE_SAMPLES')
    if len(good) < min_samples:
        reasons.append('INSUFFICIENT_SAMPLES')
    if observed_coverage < coverage:
        reasons.append('INSUFFICIENT_BUCKET_COVERAGE')
    if error_rate is not None and error_rate > max_error_rate:
        reasons.append('ERROR_RATE_EXCEEDED')
    if p95 is not None and p95 > max_p95_ms:
        reasons.append('P95_LATENCY_EXCEEDED')
    unknown_codes = {'NONLIVE_OR_UNTRUSTED_TELEMETRY', 'INVALID_OR_FUTURE_SAMPLES', 'INSUFFICIENT_SAMPLES', 'INSUFFICIENT_BUCKET_COVERAGE'}
    status = 'UNKNOWN' if unknown_codes.intersection(reasons) else ('FAIL' if reasons else 'PASS')
    return {'tenant': tenant, 'environment': environment, 'provenance': provenance,
            'window_start': start.isoformat(), 'window_end': end.isoformat(),
            'window_minutes': minutes, 'samples': len(good), 'invalid_samples': invalid,
            'future_samples': future, 'bucket_coverage': round(observed_coverage, 6),
            'p95_ms': round(p95, 3) if p95 is not None else None,
            'error_rate': round(error_rate, 6) if error_rate is not None else None,
            'status': status, 'reasons': reasons}


def evaluate_pair(events: list[dict], *, tenant: str, now: str,
                  environment: str, provenance: str,
                  max_error_rate: float = .01, max_p95_ms: float = 2000) -> dict:
    """One-authoritative sample stream for 1h/24h; never fill missing buckets.

    A "live" provenance label must be backed by actual telemetry collection
    evidence. This calculation does not authenticate where samples came from.
    """
    windows = [evaluate(events, tenant=tenant, now=now, minutes=duration,
                        min_samples=(100 if duration == 60 else 1000),
                        environment=environment, provenance=provenance,
                        max_error_rate=max_error_rate, max_p95_ms=max_p95_ms)
               for duration in (60, 1440)]
    return {'tenant': tenant, 'environment': environment, 'provenance': provenance,
            'limits': {'max_error_rate': max_error_rate, 'max_p95_ms': max_p95_ms},
            'windows': windows,
            'status': 'PASS' if all(w['status'] == 'PASS' for w in windows) else 'BLOCK',
            'calculation_only': True}
