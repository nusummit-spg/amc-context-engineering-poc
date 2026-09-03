# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""User repository — today backed by a JSON file, tomorrow a database.

`AuthService` only ever talks to the `UserRepository` protocol below. To
migrate to a real database later, write a new class (e.g. `SqlUserRepository`)
that implements `get_by_username`, wire it up in `app/api/deps.py` in place
of `JSONUserRepository`, and nothing else in the auth module, the routes, or
the React frontend needs to change — the API contract (`/api/auth/login`
request/response shape) stays identical.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger("auth")

DEFAULT_USERS_PATH = Path(__file__).resolve().parent / "data" / "users.json"


class AuthUserRecord:
    """Internal representation of a stored user — includes the password hash.

    Never returned directly from an API route; routes always map this to
    the public `UserPublic` schema first so the hash never leaves the
    server process.
    """

    __slots__ = (
        "username",
        "password_hash",
        "display_name",
        "role",
        "department",
        "email",
        "avatar_initials",
        "status",
    )

    def __init__(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        department: str = "",
        email: str = "",
        avatar_initials: str = "",
        status: str = "Active",
    ) -> None:
        self.username = username
        self.password_hash = password_hash
        self.display_name = display_name
        self.role = role
        self.department = department
        self.email = email
        self.avatar_initials = avatar_initials or "".join(w[0] for w in display_name.split()[:2]).upper()
        self.status = status


class UserRepository(Protocol):
    """Contract every user repository implementation must satisfy."""

    def get_by_username(self, username: str) -> Optional[AuthUserRecord]:
        ...


class JSONUserRepository:
    """Loads user records (including password hashes) from a JSON file.

    The file is read lazily and cached in memory, with a lock guarding
    reloads so concurrent requests never see a half-written file. Call
    `reload()` (e.g. from an admin action) to pick up changes without
    restarting the process.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        if path:
            p = Path(path)
            if not p.exists() and not p.is_absolute():
                # Resolve relative to repo root, backend, or app dir if not found in cwd
                candidates = [
                    Path(__file__).resolve().parent.parent.parent / p,
                    Path(__file__).resolve().parent.parent / p,
                    Path(__file__).resolve().parent / "data" / p.name,
                    DEFAULT_USERS_PATH,
                ]
                for cand in candidates:
                    if cand.exists():
                        p = cand
                        break
            self._path = p
        else:
            self._path = DEFAULT_USERS_PATH
        self._lock = threading.Lock()
        self._users: dict[str, AuthUserRecord] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            # Fallback to DEFAULT_USERS_PATH if current _path doesn't exist
            if DEFAULT_USERS_PATH.exists() and self._path != DEFAULT_USERS_PATH:
                self._path = DEFAULT_USERS_PATH

        if not self._path.exists():
            logger.warning("Auth user store not found at %s — no users can log in", self._path)
            self._users = {}
            self._loaded = True
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not read auth user store %s: %s", self._path, exc)
            self._users = {}
            self._loaded = True
            return

        users: dict[str, AuthUserRecord] = {}
        for entry in raw.get("users", []):
            try:
                record = AuthUserRecord(
                    username=entry["username"],
                    password_hash=entry["password_hash"],
                    display_name=entry.get("display_name", entry["username"]),
                    role=entry.get("role", ""),
                    department=entry.get("department", ""),
                    email=entry.get("email", ""),
                    avatar_initials=entry.get("avatar_initials", ""),
                    status=entry.get("status", "Active"),
                )
            except KeyError as exc:
                logger.warning("Skipping malformed user record in %s: missing %s", self._path, exc)
                continue
            users[record.username.lower()] = record

        self._users = users
        self._loaded = True
        logger.info("Loaded %d user record(s) from %s", len(users), self._path)

    def get_by_username(self, username: str) -> Optional[AuthUserRecord]:
        self._ensure_loaded()
        clean = (username or "").strip().lower()
        if not clean:
            return None
        if clean in self._users:
            return self._users[clean]
        # Interoperability: support both dot and underscore username formats
        if "." in clean:
            alt = clean.replace(".", "_")
            if alt in self._users:
                return self._users[alt]
        if "_" in clean:
            alt = clean.replace("_", ".")
            if alt in self._users:
                return self._users[alt]
        return None

