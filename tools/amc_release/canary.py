"""Strict read-only staging canary probe; never deploys or rolls anything back.

Important: urllib follows redirects by default, which could leave a staging
hostname allowlist and issue an unauthorised GET. This adapter refuses redirects
BEFORE following them, and rejects mutation-like paths and unhealthy JSON.
"""
from __future__ import annotations
import json
import re
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from .common import iso_now, digest


class CanaryError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_readonly(req: Request, timeout: int):
    return build_opener(_NoRedirect()).open(req, timeout=timeout)


def _path_is_allowed(p: str) -> bool:
    if not p.startswith('/') or '//' in p or '\\' in p or any(x in p for x in ('?', '#', '%', '..')):
        return False
    if p in {'/health', '/api/health', '/api/status', '/api/query/health'}:
        return True
    return re.fullmatch(r'/api/publication/status/[A-Za-z0-9_-]{1,64}', p) is not None


def probe(base_url: str, *, paths: list[str], timeout: int = 6,
          allowed_hostname: str) -> dict:
    u = urlsplit(base_url)
    if (u.scheme != 'https' or not allowed_hostname or u.hostname != allowed_hostname
            or u.port not in (None, 443) or u.query or u.fragment or u.username or u.password
            or u.path not in ('', '/')):
        raise CanaryError('HTTPS staging origin must exactly match explicit allowlisted hostname')
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise CanaryError('timeout must be 1–30 seconds')
    if not paths or not all(isinstance(p, str) and _path_is_allowed(p) for p in paths):
        raise CanaryError('use only approved read-only health/status paths; no encoded paths or queries')
    results = []
    for p in paths:
        try:
            req = Request(f'https://{allowed_hostname}{p}', method='GET',
                          headers={'Accept': 'application/json', 'Cache-Control': 'no-cache'})
            with _open_readonly(req, timeout) as response:
                status = response.status
                raw = response.read(256 * 1024 + 1)
                redirected = response.geturl() != req.full_url if callable(getattr(response, 'geturl', None)) else False
            if len(raw) > 256 * 1024 or redirected:
                raise CanaryError('redirect or oversized response rejected')
            content = json.loads(raw)
            reported_status = str(content.get('status', 'ok')).lower() if isinstance(content, dict) else ''
            is_healthy = isinstance(content, dict) and content.get('healthy') is not False \
                and reported_status not in {'failed', 'fail', 'error', 'unhealthy', 'down'} \
                and not bool(content.get('error'))
            success = 200 <= status <= 299 and is_healthy
            results.append({'path': p, 'http_status': status, 'body_sha256': digest(content),
                            'status': 'PASS' if success else 'FAIL'})
        except (CanaryError, HTTPError, URLError, ValueError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            results.append({'path': p, 'status': 'FAIL', 'error_type': type(exc).__name__})
    return {'at': iso_now(), 'environment': 'staging', 'mode': 'read_only',
            'hostname': allowed_hostname, 'sha256_of_target': digest(base_url),
            'results': results,
            'status': 'PASS' if all(x['status'] == 'PASS' for x in results) else 'FAIL',
            'release_authorized': False}
