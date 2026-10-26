# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
query_evidence_recorder.py
==========================
Phase 3 of the Schema & Audit roadmap (Docs/02-Architecture-and-Design/SCHEMA_AND_AUDIT_STRUCTURE.md
Part 1.4 / Part 4 "Phase 3: Audit Trail & Query Evidence").

Records one **query_evidence** record per Chat-tab turn as JSON on disk, using
the exact column names of the ``query_evidence`` table from
``Docs/02-Architecture-and-Design/SQL_SCHEMA_IMPLEMENTATION.sql`` as the top-level keys. The file is the
file-based equivalent of that table, so a later ``init_audit_schema.py`` load
is a straight column-for-column insert.

Scope — deliberately narrow:
  * **Chat tab only.** /query and /chat/title are not recorded here.
  * **ContextGraph only.** ``retrieval_mode`` is always ``"contextgraph"``;
    traditional-RAG turns are never written, and on ``mode="both"`` only the
    ContextGraph half is captured (``traditional_result_json`` stays ``null``).

Layout — one JSON file per chat session, next to logs/chat_sessions/::

    backend/logs/chat_query_evidence/
        chat_evidence_<session_id>.json

Each file is a single JSON document::

    {
      "schema_version": "1.0",
      "table": "query_evidence",
      "retrieval_mode": "contextgraph",
      "generated_by": "...",
      "session": { ...sessions table columns... },
      "query_evidence": [ { ...query_evidence table columns... }, ... ]
    }

The five ``*_json`` columns are stored as **nested JSON objects** rather than
escaped strings: the destination is a JSON log, so nesting keeps the file
readable and diffable. ``json.dumps()`` on any one of them yields exactly the
TEXT/JSONB value the table expects.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

logger = logging.getLogger("app.query_evidence")

SCHEMA_VERSION = "1.0"
GENERATED_BY = "context_engineering.chat.contextgraph"
RETRIEVAL_MODE = "contextgraph"

# backend/  (…/backend/app/retrieval/query_evidence_recorder.py -> parents[2])
_BASE_DIR = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = Path(
    os.environ.get("CHAT_QUERY_EVIDENCE_DIR", _BASE_DIR / "logs" / "chat_query_evidence")
)

# Feature flag — set CHAT_QUERY_EVIDENCE_ENABLED=0 to disable recording.
def _enabled() -> bool:
    """Enabled.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    return os.environ.get("CHAT_QUERY_EVIDENCE_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


# Column order of query_evidence in SQL_SCHEMA_IMPLEMENTATION.sql. Every record
# is emitted with these keys, in this order, so the JSON reads like the table.
QUERY_EVIDENCE_COLUMNS: tuple[str, ...] = (
    # Identifiers
    "response_id",
    "session_id",
    "user_id",
    "tenant_id",
    "request_id",
    # Query metadata
    "query_text",
    "query_type",
    "query_intent",
    # Retrieval mode
    "retrieval_mode",
    "serving_engine",
    # Full JSON content
    "assembled_context_json",
    "synthesis_output_json",
    "graph_highlight_json",
    "traditional_result_json",
    # Performance & quality
    "latency_ms",
    "retrieval_latency_ms",
    "synthesis_latency_ms",
    "quality_score",
    "confidence_level",
    # Audit linking
    "audit_id",
    "linked_violations_json",
    # Feedback & corrections
    "has_feedback",
    "feedback_summary_json",
    # Metadata
    "created_at",
    "archived",
)

# sessions table (SQL_SCHEMA_IMPLEMENTATION.sql line 445).
SESSION_COLUMNS: tuple[str, ...] = (
    "session_id",
    "user_id",
    "tenant_id",
    "created_at",
    "updated_at",
    "ended_at",
    "audit_id",
)

_VALID_CONFIDENCE = ("high", "medium", "low")

_write_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    """UTC timestamp, ISO-8601 with a trailing Z — matches the manifest format.

    Returns:
        str: Resulting str instance.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _confidence_level(label: Any) -> Optional[str]:
    """Normalise a confidence label to the CHECK-constrained high|medium|low.

    Args:
        label (Any): The label.

    Returns:
        Optional[str]: Matching object or record if found, None otherwise.
    """
    text = str(label or "").lower()
    if not text:
        return None
    if text in _VALID_CONFIDENCE:
        return text
    if "high" in text:
        return "high"
    if "medium" in text or "moderate" in text:
        return "medium"
    if "low" in text:
        return "low"
    return None


def _as_int_ms(value: Any) -> Optional[int]:
    """As int ms.

    Args:
        value (Any): The value.

    Returns:
        Optional[int]: Matching object or record if found, None otherwise.
    """
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    """As float.

    Args:
        value (Any): The value.

    Returns:
        Optional[float]: Matching object or record if found, None otherwise.
    """
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_session_filename(session_id: str) -> str:
    """Strip any path component — session_id reaches us from the request body.

    Args:
        session_id (str): Unique identifier of the session.

    Returns:
        str: Resulting str instance.
    """
    safe = Path(str(session_id or "unknown")).name.strip() or "unknown"
    return f"chat_evidence_{safe}.json"


def _dump(value: Any) -> Any:
    """Best-effort conversion of pydantic models / sets to JSON-safe values.

    Args:
        value (Any): The value.

    Returns:
        Any: Resulting Any instance.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            pass
    if isinstance(value, Mapping):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_dump(v) for v in value]
    return str(value)


# ─────────────────────────────────────────────────────────────────────────
# JSON column builders (Part 1.4 payload shapes)
# ─────────────────────────────────────────────────────────────────────────

def build_assembled_context_json(
    sources: Sequence[Mapping[str, Any]],
    *,
    context_text: str = "",
    quality_score: Optional[float] = None,
    passed_quality_gate: Optional[bool] = None,
) -> dict[str, Any]:
    """``{context_text, sources: [...], quality_score, passed_quality_gate}``.

    Args:
        sources (Sequence[Mapping[str, Any]]): Collection or list of sources.
        context_text (str): The context text.
        quality_score (Optional[float]): The quality score.
        passed_quality_gate (Optional[bool]): The passed quality gate.

    Returns:
        dict[str, Any]: Dictionary containing result data or status.
    """
    normalised: list[dict[str, Any]] = []
    for i, s in enumerate(sources or []):
        s = _dump(s) or {}
        page = s.get("page_number", s.get("page"))
        normalised.append({
            "source_index": s.get("source_index", i + 1),
            "document_id": s.get("document_id") or s.get("name") or s.get("document_title"),
            "chunk_id": s.get("chunk_id") or f"src.{i + 1}",
            "document_title": s.get("document_title") or s.get("name") or s.get("document_id"),
            "page_number": page,
            "snippet": s.get("snippet") or "",
            "score": _as_float(s.get("score")),
        })
    return {
        "context_text": context_text or "",
        "sources": normalised,
        "quality_score": quality_score,
        "passed_quality_gate": passed_quality_gate,
    }


def build_synthesis_output_json(
    answer: Any,
    *,
    confidence: Optional[str] = None,
    compliance_note: str = "",
    citations: Optional[Sequence[Mapping[str, Any]]] = None,
    structured_rows: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    """``{answer, confidence, citations: [...], structured_rows, compliance_note}``.

    ``answer`` may be a SynthesisOutput / dict (as produced by both the legacy
    and the v2 path) or a plain string.

    Args:
        answer (Any): The answer.
        confidence (Optional[str]): The confidence.
        compliance_note (str): The compliance note.
        citations (Optional[Sequence[Mapping[str, Any]]]): Collection or list of citations.
        structured_rows (Optional[Sequence[Any]]): Collection or list of structured rows.

    Returns:
        dict[str, Any]: Dictionary containing result data or status.
    """
    payload = _dump(answer)
    if isinstance(payload, Mapping):
        answer_text = payload.get("answer") or payload.get("answer_markdown") or ""
        confidence = confidence or payload.get("confidence")
        compliance_note = compliance_note or payload.get("compliance_note") or ""
        if citations is None:
            citations = payload.get("citations") or []
        if structured_rows is None:
            structured_rows = payload.get("structured_rows") or payload.get("metrics") or []
    else:
        answer_text = payload or ""

    flat_citations: list[dict[str, Any]] = []
    for i, c in enumerate(citations or []):
        c = _dump(c) or {}
        # Legacy shape is {marker, source: {...}}; v2 is already flat.
        src = c.get("source") if isinstance(c.get("source"), Mapping) else c
        flat_citations.append({
            "source_index": _as_int_ms(c.get("marker")) or c.get("source_index") or i + 1,
            "document_id": src.get("document_id") or src.get("document_name"), # type: ignore
            "document_title": src.get("document_name") or src.get("document_title"), # type: ignore
            "page_number": src.get("page_number", src.get("page")), # type: ignore
            "verbatim_text": src.get("verbatim_text") or src.get("snippet") or "", # type: ignore
        })

    return {
        "answer": answer_text,
        "confidence": _confidence_level(confidence),
        "citations": flat_citations,
        "structured_rows": _dump(list(structured_rows or [])),
        "compliance_note": compliance_note or "",
    }


def build_graph_highlight_json(graph_highlight: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """``{node_names, relationships, entities, labels}`` — the four schema keys.

    Edge lists and the embedded telemetry blob carried by the API response are
    dropped: they are UI payload, and ``latency_*``/``quality_score`` already
    capture the telemetry the schema asks for.

    Args:
        graph_highlight (Optional[Mapping[str, Any]]): The graph highlight.

    Returns:
        Optional[dict[str, Any]]: Dictionary containing result data or status.
    """
    if not graph_highlight:
        return None
    gh = _dump(graph_highlight) or {}
    return {
        "node_names": list(gh.get("node_names") or []),
        "relationships": list(gh.get("relationships") or []),
        "entities": list(gh.get("entities") or []),
        "labels": list(gh.get("labels") or []),
    }


# ─────────────────────────────────────────────────────────────────────────
# recorder
# ─────────────────────────────────────────────────────────────────────────

class QueryEvidenceRecorder:
    """Append ContextGraph chat turns to a per-session query_evidence JSON file."""

    def __init__(self, evidence_dir: Path | str | None = None) -> None:
        """Initialize a new instance of QueryEvidenceRecorder.

        Args:
            evidence_dir (Path | str | None): The evidence dir.
        """
        self.evidence_dir = Path(evidence_dir) if evidence_dir else EVIDENCE_DIR

    # -- public API ------------------------------------------------------

    def record(
        self,
        *,
        response_id: str,
        session_id: str,
        query_text: str,
        assembled_context_json: Mapping[str, Any],
        synthesis_output_json: Mapping[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        query_type: Optional[str] = None,
        query_intent: Optional[str] = None,
        serving_engine: Optional[str] = None,
        graph_highlight_json: Optional[Mapping[str, Any]] = None,
        latency_ms: Optional[int] = None,
        retrieval_latency_ms: Optional[int] = None,
        synthesis_latency_ms: Optional[int] = None,
        quality_score: Optional[float] = None,
        confidence_level: Optional[str] = None,
        audit_id: Optional[str] = None,
        linked_violations: Optional[Iterable[str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Write one query_evidence record to both JSON logs and data.db. Returns it, or None if not recorded.

        SECURITY: user_id is now MANDATORY. Never record evidence without
        associating it to an authenticated user and verifying session ownership.

        Args:
            response_id (str): Unique identifier of the response.
            session_id (str): Unique identifier of the session.
            query_text (str): The query text.
            assembled_context_json (Mapping[str, Any]): The assembled context json.
            synthesis_output_json (Mapping[str, Any]): The synthesis output json.
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            request_id (Optional[str]): Unique identifier of the request.
            query_type (Optional[str]): The query type.
            query_intent (Optional[str]): The query intent.
            serving_engine (Optional[str]): The serving engine.
            graph_highlight_json (Optional[Mapping[str, Any]]): The graph highlight json.
            latency_ms (Optional[int]): Collection or list of latency ms.
            retrieval_latency_ms (Optional[int]): Collection or list of retrieval latency ms.
            synthesis_latency_ms (Optional[int]): Collection or list of synthesis latency ms.
            quality_score (Optional[float]): The quality score.
            confidence_level (Optional[str]): The confidence level.
            audit_id (Optional[str]): Unique identifier of the audit.
            linked_violations (Optional[Iterable[str]]): Collection or list of linked violations.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing result data or status.
        """
        if not _enabled():
            return None

        if not user_id or not str(user_id).strip():
            logger.error("Attempted to record query_evidence without user_id (response_id=%s)", response_id)
            return None  # SECURITY: Refuse to record anonymous evidence

        try:
            record = {
                "response_id": response_id,
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "request_id": request_id,
                "query_text": query_text,
                "query_type": query_type,
                "query_intent": query_intent,
                # ContextGraph-only by construction — see module docstring.
                "retrieval_mode": RETRIEVAL_MODE,
                "serving_engine": serving_engine,
                "assembled_context_json": _dump(assembled_context_json),
                "synthesis_output_json": _dump(synthesis_output_json),
                "graph_highlight_json": _dump(graph_highlight_json),
                "traditional_result_json": None,
                "latency_ms": _as_int_ms(latency_ms),
                "retrieval_latency_ms": _as_int_ms(retrieval_latency_ms),
                "synthesis_latency_ms": _as_int_ms(synthesis_latency_ms),
                "quality_score": _as_float(quality_score),
                "confidence_level": _confidence_level(confidence_level),
                "audit_id": audit_id,
                "linked_violations_json": list(linked_violations or []),
                # Feedback arrives later via /feedback; the recorder writes the
                # schema default and the feedback route can flip it.
                "has_feedback": False,
                "feedback_summary_json": None,
                "created_at": _utc_now(),
                "archived": False,
            }
            record = {k: record[k] for k in QUERY_EVIDENCE_COLUMNS}

            # Verify session ownership before recording
            try:
                from app.core.database import SessionLocal
                from app.schemas.chat_sessions_table import ChatSession
                from app.schemas.models import _now_iso

                db = SessionLocal()
                try:
                    session_record = db.query(ChatSession).filter_by(session_id=session_id).first()

                    if session_record:
                        # Session exists: verify it belongs to this user
                        if session_record.user_id != user_id:
                            logger.error(
                                "User %s attempted to record evidence in session %s owned by %s",
                                user_id, session_id, session_record.user_id,
                            )
                            return None  # SECURITY: Reject cross-user evidence recording

                        if tenant_id and session_record.tenant_id != tenant_id:
                            logger.error(
                                "Tenant mismatch: evidence tenant=%s, session tenant=%s",
                                tenant_id, session_record.tenant_id,
                            )
                            return None
                    else:
                        # New session: create it with proper ownership
                        now_str = _now_iso()
                        new_session = ChatSession(
                            session_id=session_id,
                            user_id=user_id,
                            tenant_id=tenant_id,
                            created_at=now_str,
                            updated_at=now_str,
                        )
                        db.add(new_session)
                        db.commit()
                finally:
                    db.close()
            except Exception as session_check_exc:
                logger.error("Session ownership check failed: %s", session_check_exc)
                return None

            # Write to JSON logs (legacy)
            self._append(record, user_id=user_id, tenant_id=tenant_id)

            # Also write to data.db (single source of truth)
            try:
                self._write_to_data_db(record)
            except Exception as db_exc:
                logger.debug("Could not write QueryEvidence to data.db (not critical): %s", db_exc)

            return record
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("query_evidence recording skipped: %s", exc)
            return None

    def record_contextgraph_turn(
        self,
        *,
        session_id: str,
        query_text: str,
        result: Mapping[str, Any],
        hybrid: Mapping[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None,
        serving_engine: str = "legacy",
        request_id: Optional[str] = None,
        audit_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Adapter for the legacy engine: ``retrieval.hybrid_graphrag`` result
        (``result``) plus the assembled ``hybrid`` payload the chat route
        returns to the UI.

        Args:
            session_id (str): Unique identifier of the session.
            query_text (str): The query text.
            result (Mapping[str, Any]): The result.
            hybrid (Mapping[str, Any]): The hybrid.
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            serving_engine (str): The serving engine.
            request_id (Optional[str]): Unique identifier of the request.
            audit_id (Optional[str]): Unique identifier of the audit.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing result data or status.
        """
        if not _enabled():
            return None
        try:
            telemetry = (result.get("telemetry_breakdown") or {}) if result else {}
            sources = _with_scores(
                hybrid.get("sources") or [],
                (hybrid.get("graph_highlight") or {}).get("provenance") or [],
            )
            confidence = _confidence_level(result.get("confidence_label"))
            quality_score = _quality_score(telemetry, sources)
            passed_gate = _passed_quality_gate(telemetry, sources)
            total_ms, retrieval_ms, synthesis_ms = _split_latency(
                hybrid.get("latency_ms"), telemetry
            )

            return self.record(
                response_id=hybrid.get("response_id"), # type: ignore
                session_id=session_id,
                request_id=request_id or hybrid.get("interaction_id"),
                query_text=query_text,
                query_type=result.get("query_type"),
                query_intent=telemetry.get("domain_intent"),
                serving_engine=serving_engine,
                assembled_context_json=build_assembled_context_json(
                    sources,
                    context_text=_context_text(sources),
                    quality_score=quality_score,
                    passed_quality_gate=passed_gate,
                ),
                synthesis_output_json=build_synthesis_output_json(
                    hybrid.get("answer") or result.get("answer"),
                    confidence=confidence,
                    compliance_note=result.get("confidence_reason") or "",
                ),
                graph_highlight_json=build_graph_highlight_json(hybrid.get("graph_highlight")),
                latency_ms=total_ms,# type: ignore
                retrieval_latency_ms=retrieval_ms,# type: ignore
                synthesis_latency_ms=synthesis_ms, # type: ignore
                quality_score=quality_score,
                confidence_level=confidence,
                audit_id=audit_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("query_evidence recording skipped: %s", exc)
            return None

    def record_v2_contextgraph_turn(
        self,
        *,
        session_id: str,
        query_text: str,
        hybrid: Mapping[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None,
        intent: Any = None,
        trace: Any = None,
        serving_engine: str = "v2",
        audit_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Adapter for the v2 orchestrator path (``container.orchestrator.answer``).

        Args:
            session_id (str): Unique identifier of the session.
            query_text (str): The query text.
            hybrid (Mapping[str, Any]): The hybrid.
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            intent (Any): Classified query intent.
            trace (Any): The trace.
            serving_engine (str): The serving engine.
            audit_id (Optional[str]): Unique identifier of the audit.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing result data or status.
        """
        if not _enabled():
            return None
        try:
            tr = _dump(trace) or {}
            intent_d = _dump(intent) or {}
            sources = hybrid.get("sources") or []
            answer = hybrid.get("answer") or {}
            confidence = _confidence_level(
                (answer or {}).get("confidence") if isinstance(answer, Mapping) else None
            )
            # The v2 orchestrator supplies a real quality_score on its trace.
            quality_score = _as_float(tr.get("quality_score"))

            total_ms = _as_float(hybrid.get("latency_ms")) or _as_float(tr.get("request_total_ms"))
            synthesis_ms = _as_float(tr.get("generation_ms"))
            retrieval_ms = (
                None if (total_ms is None or synthesis_ms is None)
                else max(0.0, total_ms - synthesis_ms)
            )

            return self.record(
                response_id=hybrid.get("response_id"), # type: ignore
                session_id=session_id,
                request_id=tr.get("request_id") or hybrid.get("interaction_id"),
                query_text=query_text,
                query_type=intent_d.get("query_type") if isinstance(intent_d, Mapping) else None,
                query_intent=intent_d.get("intent") or intent_d.get("domain_intent")
                if isinstance(intent_d, Mapping) else None,
                serving_engine=serving_engine,
                assembled_context_json=build_assembled_context_json(
                    sources,
                    context_text=_context_text(sources),
                    quality_score=quality_score,
                    passed_quality_gate=tr.get("quality_gate_passed"),
                ),
                synthesis_output_json=build_synthesis_output_json(answer, confidence=confidence),
                graph_highlight_json=build_graph_highlight_json(hybrid.get("graph_highlight")),
                latency_ms=total_ms,# type: ignore
                retrieval_latency_ms=retrieval_ms,# type: ignore
                synthesis_latency_ms=synthesis_ms,# type: ignore
                quality_score=quality_score,
                confidence_level=confidence,
                audit_id=audit_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("query_evidence recording skipped: %s", exc)
            return None

    def mark_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_summary: Mapping[str, Any],
    ) -> bool:
        """Flip ``has_feedback`` / fill ``feedback_summary_json`` for one record.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            feedback_summary (Mapping[str, Any]): The feedback summary.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if not _enabled():
            return False
        path = self._path(session_id)
        with _write_lock:
            doc = self._read(path)
            if doc is None:
                return False
            for rec in doc.get("query_evidence", []):
                if rec.get("response_id") == response_id:
                    rec["has_feedback"] = True
                    rec["feedback_summary_json"] = _dump(feedback_summary)
                    doc["session"]["updated_at"] = _utc_now()
                    self._write(path, doc)
                    return True
        return False

    # -- file plumbing ---------------------------------------------------

    def _path(self, session_id: str) -> Path:
        """Path.

        Args:
            session_id (str): Unique identifier of the session.

        Returns:
            Path: Resulting Path instance.
        """
        return self.evidence_dir / _safe_session_filename(session_id)

    def _read(self, path: Path) -> Optional[dict[str, Any]]:
        """Read.

        Args:
            path (Path): Filesystem path or resource path.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing result data or status.
        """
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            return doc if isinstance(doc, dict) else None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("query_evidence log %s unreadable, starting fresh: %s", path.name, exc)
            return None

    def _write(self, path: Path, doc: Mapping[str, Any]) -> None:
        """Atomic replace so a concurrent reader never sees a half-written file.

        Args:
            path (Path): Filesystem path or resource path.
            doc (Mapping[str, Any]): The doc.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".qe_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _append(self, record: Mapping[str, Any], *, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
        """Append.

        Args:
            record (Mapping[str, Any]): The record.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
        path = self._path(record["session_id"])
        now = record.get("created_at") or _utc_now()
        with _write_lock:
            doc = self._read(path) or {
                "schema_version": SCHEMA_VERSION,
                "table": "query_evidence",
                "retrieval_mode": RETRIEVAL_MODE,
                "generated_by": GENERATED_BY,
                "session": {
                    "session_id": record["session_id"],
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "created_at": now,
                    "updated_at": now,
                    "ended_at": None,
                    "audit_id": record.get("audit_id"),
                },
                "query_evidence": [],
            }
            session = doc.setdefault("session", {})
            for col in SESSION_COLUMNS:
                session.setdefault(col, None)
            session["session_id"] = record["session_id"]
            session["updated_at"] = now
            if user_id and not session.get("user_id"):
                session["user_id"] = user_id
            if tenant_id and not session.get("tenant_id"):
                session["tenant_id"] = tenant_id
            if record.get("audit_id") and not session.get("audit_id"):
                session["audit_id"] = record["audit_id"]

            doc.setdefault("query_evidence", []).append(dict(record))
            self._write(path, doc)
        logger.info(
            "query_evidence recorded response_id=%s session=%s -> %s",
            record.get("response_id"), record.get("session_id"), path.name,
        )

    def _write_to_data_db(self, record: Mapping[str, Any]) -> None:
        """Write query_evidence record to data.db (single source of truth).

        This ensures QueryEvidence is immediately available in data.db when a response
        is generated, without waiting for sync from JSON logs.

        Args:
            record (Mapping[str, Any]): The record.
        """
        try:
            from app.core.database import SessionLocal
            from app.schemas.query_evidence_table import QueryEvidence
            
            db = SessionLocal()
            try:
                # Check if record already exists
                existing = db.query(QueryEvidence).filter_by(
                    response_id=record.get("response_id")
                ).first()
                
                if not existing:
                    # Create new QueryEvidence record in data.db
                    qe = QueryEvidence(
                        response_id=record.get("response_id"),
                        session_id=record.get("session_id"),
                        user_id=record.get("user_id"),
                        tenant_id=record.get("tenant_id"),
                        request_id=record.get("request_id"),
                        query_text=record.get("query_text"),
                        query_type=record.get("query_type"),
                        query_intent=record.get("query_intent"),
                        retrieval_mode=record.get("retrieval_mode", "contextgraph"),
                        serving_engine=record.get("serving_engine"),
                        assembled_context_json=record.get("assembled_context_json"),
                        synthesis_output_json=record.get("synthesis_output_json"),
                        graph_highlight_json=record.get("graph_highlight_json"),
                        traditional_result_json=record.get("traditional_result_json"),
                        latency_ms=record.get("latency_ms"),
                        retrieval_latency_ms=record.get("retrieval_latency_ms"),
                        synthesis_latency_ms=record.get("synthesis_latency_ms"),
                        quality_score=record.get("quality_score"),
                        confidence_level=record.get("confidence_level"),
                        audit_id=record.get("audit_id"),
                        linked_violations_json=record.get("linked_violations_json"),
                        has_feedback=False,
                        feedback_summary_json=None,
                        created_at=record.get("created_at"),
                        archived=False,
                    )
                    db.add(qe)
                    db.commit()
                    logger.debug("QueryEvidence written to data.db: response_id=%s", record.get("response_id"))
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Could not write QueryEvidence to data.db: %s", exc)



# ─────────────────────────────────────────────────────────────────────────
# derived metrics
# ─────────────────────────────────────────────────────────────────────────

def _context_text(sources: Sequence[Mapping[str, Any]]) -> str:
    """The verbatim context that was put in front of the LLM, joined per source.

    Args:
        sources (Sequence[Mapping[str, Any]]): Collection or list of sources.

    Returns:
        str: Resulting str instance.
    """
    parts = []
    for i, s in enumerate(sources or []):
        s = _dump(s) or {}
        text = s.get("verbatim_text") or s.get("snippet") or ""
        if text:
            parts.append(f"[{i + 1}] {text}")
    return "\n\n".join(parts)


def _with_scores(
    sources: Sequence[Mapping[str, Any]], provenance: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Backfill ``score`` onto sources from the parallel provenance list.

    ``SourceAttribution`` carries no score, but the graph_highlight provenance
    list is built from the same citation list in the same order, and does. The
    value is the engine's raw retrieval score (a FAISS distance on the legacy
    path, so it can be negative) — recorded as-is for audit ranking, never
    rescaled into a quality number. Falls back to whatever the source already
    has when the two lists do not line up.

    Args:
        sources (Sequence[Mapping[str, Any]]): Collection or list of sources.
        provenance (Sequence[Mapping[str, Any]]): The provenance.

    Returns:
        list[dict[str, Any]]: List of resulting items or records.
    """
    out: list[dict[str, Any]] = []
    for i, s in enumerate(sources or []):
        s = dict(_dump(s) or {})
        if s.get("score") is None and i < len(provenance):
            p = _dump(provenance[i]) or {}
            # Only borrow when it is the same document/page, so a length or
            # ordering mismatch cannot attach a score to the wrong source.
            same = (
                p.get("document_title") or p.get("name")
            ) == (s.get("document_title") or s.get("document_id"))
            if same:
                s["score"] = _as_float(p.get("score"))
        out.append(s)
    return out


def _ledger(telemetry: Mapping[str, Any]) -> Mapping[str, Any]:
    """Ledger.

    Args:
        telemetry (Mapping[str, Any]): The telemetry.

    Returns:
        Mapping[str, Any]: Dictionary containing result data or status.
    """
    return telemetry.get("cross_validation_ledger") or {}


def _quality_score(
    telemetry: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]
) -> Optional[float]:
    """``quality_score`` — the cross-validation ledger's groundedness score.

    That is the engine's own 0.0-1.0 answer-quality measure (the fraction of
    claims corroborated by cited evidence), so it is used directly. Raw
    retrieval scores are deliberately NOT a fallback: on the legacy path they
    are FAISS distances (e.g. -2.57), not similarities, and squashing those
    into 0-1 would fabricate a quality number.

    Args:
        telemetry (Mapping[str, Any]): The telemetry.
        sources (Sequence[Mapping[str, Any]]): Collection or list of sources.

    Returns:
        Optional[float]: Matching object or record if found, None otherwise.
    """
    score = _as_float(_ledger(telemetry).get("groundedness_score"))
    if score is None:
        return None
    if not sources:
        return 0.0
    return round(max(0.0, min(1.0, score)), 4)


# Cross-validation verdicts that count as passing the quality gate.
# cross_validation.py grades a live answer VERIFIED (groundedness >= 0.75 and
# no contradictions) / PARTIALLY_SUPPORTED / UNVERIFIED / INSUFFICIENT_EVIDENCE;
# the intent-cache path re-serves a pre-verified answer as SUPPORTED. Only the
# two passing verdicts are listed — anything else is a fail, including a status
# added later, which is the safe default for an audit record.
_QUALITY_GATE_PASS_STATUSES = frozenset({"VERIFIED", "SUPPORTED"})


def _passed_quality_gate(
    telemetry: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]
) -> Optional[bool]:
    """Cross-validation verdict — a passing status, with at least one source.

    The legacy ledger reports this under ``status``; ``evidence_status`` is
    accepted too, since that is the spelling the cache-hit path emits.

    Args:
        telemetry (Mapping[str, Any]): The telemetry.
        sources (Sequence[Mapping[str, Any]]): Collection or list of sources.

    Returns:
        Optional[bool]: Matching object or record if found, None otherwise.
    """
    ledger = _ledger(telemetry)
    status = str(ledger.get("status") or ledger.get("evidence_status") or "").upper()
    if not status:
        return None
    return status in _QUALITY_GATE_PASS_STATUSES and bool(sources)


def _split_latency(
    total_ms: Any, telemetry: Mapping[str, Any]
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (total, retrieval, synthesis) ms measured on a single clock.

    The legacy ``telemetry_breakdown`` stage timers overlap — the NER, graph,
    vector and rerank windows are not disjoint, so they sum to more than the
    real end-to-end time (8451ms of stages for a 5007ms request). Summing them
    would emit a ``retrieval_latency_ms`` larger than ``latency_ms``. Retrieval
    is therefore derived as total minus synthesis: disjoint by construction,
    and it can never exceed the total.

    Args:
        total_ms (Any): Collection or list of total ms.
        telemetry (Mapping[str, Any]): The telemetry.

    Returns:
        tuple[Optional[float], Optional[float], Optional[float]]: Matching object or record if found, None otherwise.
    """
    total = _as_float(total_ms)
    if total is None:
        total = _as_float(telemetry.get("latency_total_pipeline_ms"))
    synthesis = _as_float(telemetry.get("latency_llm_generation_ms"))
    if total is None:
        return None, None, synthesis
    retrieval = None if synthesis is None else max(0.0, total - synthesis)
    return total, retrieval, synthesis


# Module-level singleton — the recorder is stateless apart from its directory.
_recorder: Optional[QueryEvidenceRecorder] = None


def get_recorder() -> QueryEvidenceRecorder:
    """Retrieve recorder.

    Returns:
        QueryEvidenceRecorder: Resulting QueryEvidenceRecorder instance.
    """
    global _recorder
    if _recorder is None:
        _recorder = QueryEvidenceRecorder()
    return _recorder
