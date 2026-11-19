"""Wave 4.0 (TDS-40 E1): verified serving of structured (fin) answers.

For every request:
  1. pin   - read the tenant's active fin pointer + receipt (fin40.current_pin);
  2. prove - verify the Ed25519 signature over the stored manifest and that the stored rows still hash to the
             signed content hash. The proof is cached per (version, manifest digest) so it runs once per process
             per activation, not per request;
  3. run   - execute the typed plan against exactly that version (tenant + version applied in SQL);
  4. recheck - re-read the pin; if it changed (activation, rollback) while the query ran, refuse to release.

Any failure in 1, 2 or 4 raises ServingDenied; a plan the data cannot answer raises FinQueryError. Callers turn
both into an abstention and never fall back to vector search or an LLM for a structured question.
"""
from __future__ import annotations

import threading

from sqlalchemy.orm import Session

from .fin40 import DOMAIN, FinDatasetVersion, current_pin, verify_dataset
from .fin_query40 import FinPlan, FinQueryError, FinResult, catalog, run_plan
from .serving27 import ServingDenied
from .types import Conflict, VerificationFailed


class VerifiedStructuredExecutor:
    def __init__(self, sessions, verifier, *, domain: str = DOMAIN):
        if verifier is None:
            raise ServingDenied("structured serving requires trusted public keys")
        self._sessions = sessions
        self._verifier = verifier
        self._domain = domain
        self._proven: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def _pin_and_prove(self, s: Session, tenant: str):
        try:
            pin = current_pin(s, tenant, self._domain)
        except Conflict as exc:
            raise ServingDenied(f"structured data unavailable: {exc}") from exc
        key = (pin.dataset_version, pin.manifest_sha256)
        if key not in self._proven:
            ds = s.get(FinDatasetVersion, pin.dataset_version)
            try:
                verify_dataset(s, ds, self._verifier)
            except VerificationFailed as exc:
                raise ServingDenied(f"structured dataset failed verification: {exc}") from exc
            with self._lock:
                self._proven.add(key)
        return pin

    def execute(self, tenant: str, plan: FinPlan) -> FinResult:
        if not isinstance(tenant, str) or not tenant.strip():
            raise ServingDenied("authenticated tenant required for structured serving")
        with self._sessions() as s:
            pin = self._pin_and_prove(s, tenant)
            result = run_plan(s, pin, plan)
        with self._sessions() as s:
            try:
                after = current_pin(s, tenant, self._domain)
            except Conflict as exc:
                raise ServingDenied("structured authority changed during the request") from exc
        if after != pin:
            raise ServingDenied("structured authority changed during the request")
        return result

    def catalog(self, tenant: str) -> dict:
        with self._sessions() as s:
            pin = self._pin_and_prove(s, tenant)
            return catalog(s, pin)

    def forget_proofs(self) -> None:
        with self._lock:
            self._proven.clear()


_EXECUTOR: VerifiedStructuredExecutor | None = None


def get_structured_executor() -> VerifiedStructuredExecutor:
    """Process-wide executor bound to the app's PostgreSQL engine and the trusted FAISS/fin public keys."""
    global _EXECUTOR
    if _EXECUTOR is None:
        from sqlalchemy.orm import sessionmaker
        from app.core.database import engine
        from .signing31 import verifier_from_env
        try:
            verifier = verifier_from_env()
        except ValueError as exc:
            raise ServingDenied(f"structured serving keys are invalid: {exc}") from exc
        _EXECUTOR = VerifiedStructuredExecutor(sessionmaker(bind=engine), verifier)
    return _EXECUTOR


def reset_structured_executor() -> None:
    global _EXECUTOR
    _EXECUTOR = None


__all__ = ["VerifiedStructuredExecutor", "get_structured_executor", "reset_structured_executor",
           "FinPlan", "FinQueryError", "FinResult", "ServingDenied"]
