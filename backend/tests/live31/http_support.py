"""Helpers for the live HTTP suite: run the real app as a process, seed users, log in, call it."""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def random_secret(n: int = 24) -> str:
    return secrets.token_urlsafe(n)


class AppServer:
    """The real FastAPI app under uvicorn, in AMC_VERIFIED_SERVING_MODE=enforce by default."""

    def __init__(self, *, database_url: str, faiss_root: Path, llm_url: str, log_path: Path,
                 mode: str = "enforce", extra_env: dict | None = None, public_keys_file: Path | None = None):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = log_path
        self.secret = random_secret(36)
        env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "AMC_MIGRATION_DATABASE_URL")}
        env.update({
            "AMC_VERIFIED_SERVING_MODE": mode, "QUERY_ENGINE": "v2",
            "DATABASE_URL": database_url, "AMC_MIGRATION_DATABASE_URL": database_url,
            "AMC_VERIFIED_FAISS_ROOT": str(faiss_root),
            "AUTH_SECRET_KEY": self.secret,
            "GROQ_API_KEY": "local-stub-key-not-a-secret", "GROQ_BASE_URL": llm_url,
            "ENVIRONMENT": "development",
            "PYTHONPATH": f"{BACKEND}{os.pathsep}{BACKEND.parent}", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        })
        if public_keys_file is not None:      # the trusted PUBLIC keys; a serving host never gets a signing key
            env["AMC_VERIFIED_FAISS_PUBLIC_KEYS"] = str(public_keys_file)
        else:
            env.pop("AMC_VERIFIED_FAISS_PUBLIC_KEYS", None)
        env.update(extra_env or {})
        self.env = env
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 150.0) -> "AppServer":
        self._log = open(self.log_path, "ab")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tests.live31.serve_app31", str(self.port)],
            cwd=str(BACKEND), env=self.env, stdout=self._log, stderr=subprocess.STDOUT)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("app exited during startup:\n" + self.log_tail(40))
            try:
                if httpx.get(self.base + "/health", timeout=2).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        self.stop()
        raise RuntimeError("app did not become healthy:\n" + self.log_tail(40))

    def _tree(self):
        """The launcher AND the real server. On Windows the venv's python.exe is a small launcher that
        starts the interpreter as a CHILD, so acting on proc.pid alone leaves the server running."""
        import psutil
        try:
            root = psutil.Process(self.proc.pid)
            return [root] + root.children(recursive=True)
        except psutil.NoSuchProcess:
            return []

    def stop(self):
        if self.proc and self.proc.poll() is None:
            procs = self._tree()
            for p in procs:
                try:
                    p.terminate()
                except Exception:        # noqa: BLE001
                    pass
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                pass
            for p in procs:
                try:
                    p.kill()
                except Exception:        # noqa: BLE001
                    pass
        if getattr(self, "_log", None):
            self._log.close()

    def kill(self):
        """Hard kill of the whole tree: simulates the process dying with no shutdown hooks."""
        if self.proc and self.proc.poll() is None:
            for p in self._tree():
                try:
                    p.kill()
                except Exception:        # noqa: BLE001
                    pass
            self.proc.wait(20)

    def rss_mb(self) -> float:
        """Resident memory of the launcher plus the real server."""
        return round(sum(p.memory_info().rss for p in self._tree()) / 1e6, 1)

    def log_tail(self, n: int = 60) -> str:
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-n:])
        except OSError:
            return ""

    def log_text(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")
        except OSError:
            return ""

    def client(self, **kw) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=kw.pop("timeout", 60), **kw)


def seed_user(engine, *, username: str, password: str, tenant: str | None, role: str = "Analyst",
              status: str = "Active") -> None:
    """Insert a user through the app's real ORM model and real password hashing."""
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy.orm import sessionmaker
    from app.auth.security import hash_password
    from app.schemas.auth_users_table import AuthUser
    with sessionmaker(bind=engine).begin() as s:
        s.add(AuthUser(username=username, password_hash=hash_password(password), display_name=username.title(),
                       role=role, department="QA", email=f"{username}@example.invalid",
                       avatar_initials=username[:2].upper(), status=status, tenant_id=tenant))


def login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sse_events(response: httpx.Response) -> list[dict]:
    """Parse an SSE body into [{event, data}] (data kept as text)."""
    events, cur = [], {"event": "message", "data": []}
    for line in response.iter_lines():
        if line == "":
            if cur["data"]:
                events.append({"event": cur["event"], "data": "\n".join(cur["data"])})
            cur = {"event": "message", "data": []}
        elif line.startswith("event:"):
            cur["event"] = line[6:].strip()
        elif line.startswith("data:"):
            cur["data"].append(line[5:].lstrip())
    if cur["data"]:
        events.append({"event": cur["event"], "data": "\n".join(cur["data"])})
    return events
