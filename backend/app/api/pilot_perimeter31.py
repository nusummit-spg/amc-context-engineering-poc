"""AMC Wave 3.1: fail-closed verified pilot HTTP perimeter.

AMC_VERIFIED_SERVING_MODE=enforce admits only the reviewed pilot endpoints.
This does not replace tenant auth, publication receipts or runtime acceptance.
"""
from __future__ import annotations
import os

_ALLOWED = frozenset({
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/query"), ("POST", "/api/query/v2"),
    ("POST", "/api/query/stream"),
    ("POST", "/api/chat"), ("POST", "/api/chat/query"),
    ("POST", "/api/chat/v2"), ("POST", "/api/chat/stream"),
    ("GET", "/health"), ("GET", "/api/health"),
    ("GET", "/"), ("GET", "/chat"), ("GET", "/login"),
})
_STATIC_READ_PREFIXES = ("/assets/", "/static-files/")
_PUBLICATION_STATUS_PREFIX = "/api/publication/status/"


def is_pilot_route_allowed(method: str, path: str) -> bool:
    """Method and path policy; no unreviewed raw files, data or admin mutations."""
    if not isinstance(method, str) or not isinstance(path, str):
        return False
    if "\\" in path or "//" in path or "%" in path or "\x00" in path or any(part in (".", "..") for part in path.split("/")):
        return False
    if method == "OPTIONS":
        return True
    if (method, path) in _ALLOWED:
        return True
    if _w40_route_allowed(method, path):
        return True
    if method != "GET":
        return False
    if any(path.startswith(prefix) for prefix in _STATIC_READ_PREFIXES):
        return True
    if path.startswith(_PUBLICATION_STATUS_PREFIX):
        work_id = path[len(_PUBLICATION_STATUS_PREFIX):]
        return bool(work_id) and "/" not in work_id and len(work_id) <= 128
    return False

def _w40_route_allowed(method: str, path: str) -> bool:
    """Wave 4.0 reviewed additions (TDS-40 §5.4), each behind its ADR and flag; NOT in _ALLOWED so the
    frontend parity list changes only when the UI for them ships.

    ADR40-04  GET  /api/ready        always (body is {ready: bool}; detail only for reviewer/admin roles)
    ADR40-03  POST /api/feedback/v40 only with AMC_PILOT_FEEDBACK=on
    """
    if (method, path) == ("GET", "/api/ready"):
        return True
    if (method, path) == ("POST", "/api/feedback/v40"):
        from amc_publication.evidence40 import feedback_enabled
        return feedback_enabled()
    return False


def legacy_services_allowed() -> bool:
    """Allow background and unverified startup mutations only when mode is off."""
    mode = os.environ.get("AMC_VERIFIED_SERVING_MODE", "off")
    if mode not in ("off", "enforce"):
        raise RuntimeError("Invalid AMC_VERIFIED_SERVING_MODE; refusing application startup")
    return mode == "off"


class VerifiedPilotPerimeter31:
    """ASGI middleware, with exact-mode and exact-route enforcement."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind == "lifespan":
            await self.app(scope, receive, send)
            return
        mode = os.environ.get("AMC_VERIFIED_SERVING_MODE", "off")
        if mode == "off":
            await self.app(scope, receive, send)
            return
        if mode == "enforce" and kind == "http":
            if is_pilot_route_allowed(scope.get("method", ""), scope.get("path", "")):
                await self.app(scope, receive, send)
                return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if kind == "http":
            payload = b'{"detail":"Unreviewed route disabled in verified pilot mode"}'
            headers = [(b"content-type", b"application/json"),
                       (b"content-length", str(len(payload)).encode("ascii")),
                       (b"cache-control", b"no-store")]
            await send({"type": "http.response.start", "status": 503, "headers": headers})
            await send({"type": "http.response.body", "body": payload})
            return
        await self.app(scope, receive, send)
