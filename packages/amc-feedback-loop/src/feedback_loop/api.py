"""
Public API  the only surface the host application imports.

    from feedback_loop import start_feedback_loop, FeedbackLoopConfig

start_feedback_loop() is a thin wrapper that constructs IngestService
and calls on_ingest().  For high-volume deployments the host application
should construct IngestService once at startup and call on_ingest() directly
to avoid rebuilding the service graph on every call.
"""

from __future__ import annotations

import structlog

from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.ingest import IngestService

logger = structlog.get_logger(__name__)


def start_feedback_loop(
    feedback_id: str,
    session_id: str,
    response_id: str,
    source: str,
    config: FeedbackLoopConfig,
    db: AbstractDatabaseAdapter,
    evidence_adapter: AbstractEvidenceAdapter,
) -> bool:
    """Primary entry point invoked by the host application (AMC) after a
    feedback_records row has been inserted.

    Parameters
    ----------
    feedback_id      : PK of the feedback_records row (UUID string)
    session_id       : User session UUID
    response_id      : UUID of the AMC response being evaluated
    source           : 'active' | 'passive'
    config           : FeedbackLoopConfig  all thresholds and settings
    db               : Concrete AbstractDatabaseAdapter implementation
    evidence_adapter : Concrete AbstractEvidenceAdapter implementation

    Returns
    -------
    True    record built and written to unified_evaluation_records
    False   row was a duplicate or already processed (non-error)

    Raises
    ------
    KeyError       feedback_id not found in feedback_records
    Exception      unrecoverable build failure (ingestion_status set to 'failed')

    Usage (host app)
    ----------------
    from feedback_loop import start_feedback_loop, FeedbackLoopConfig
    from adapters import YourDBAdapter, YourEvidenceAdapter

    config   = FeedbackLoopConfig()
    db       = YourDBAdapter(dsn="postgresql://...")
    evidence = YourEvidenceAdapter(amc_base_url="https://amc.internal")

    start_feedback_loop(
        feedback_id="fb_9c4f1a",
        session_id="sess_2201",
        response_id="resp_9c4f1a",
        source="active",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )

    High-volume usage (construct once at startup)
    ---------------------------------------------
    from ingest import IngestService

    ingest_svc = IngestService(config, db, evidence)   # build once
    ingest_svc.on_ingest(feedback_id, session_id, response_id, source)

    Args:
        feedback_id (str): Unique identifier of the feedback.
        session_id (str): Unique identifier of the session.
        response_id (str): Unique identifier of the response.
        source (str): The source.
        config (FeedbackLoopConfig): Configuration dictionary or settings object.
        db (AbstractDatabaseAdapter): Database session instance.
        evidence_adapter (AbstractEvidenceAdapter): The evidence adapter.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    svc = IngestService(config=config, db=db, evidence_adapter=evidence_adapter)
    return svc.on_ingest(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        source=source,
    )

