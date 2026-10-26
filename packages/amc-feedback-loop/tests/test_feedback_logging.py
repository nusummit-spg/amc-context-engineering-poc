# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_logging.py — Comprehensive tests for logging mechanism in amc-feedback-loop.
Tests terminal execution tracing, step formatting, persistent dual-format file logging (.log and .jsonl),
directory auto-creation/reuse, and integration with RecordBuilder and Server.
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import pytest

from feedback_loop.logging import (
    DetailedConsoleFormatter,
    DetailedFileFormatter,
    JSONFormatter,
    ensure_log_directory,
    get_feedback_logger,
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
    setup_feedback_logging,
)
from feedback_loop.adapters.db import InMemoryDatabaseAdapter
from feedback_loop.adapters.evidence import InMemoryEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    RatingType,
)
from feedback_loop.orchestrator import RecordBuilder


def test_ensure_log_directory_creates_and_reuses(tmp_path):
    """Verify log directory is automatically created if missing, and reused if present.

    Args:
        tmp_path: Filesystem path to the tmp.
    """
    target_dir = tmp_path / "dynamic_logs" / "nested"
    assert not target_dir.exists()

    # First call: creates directory
    resolved = ensure_log_directory(target_dir / "feedback_loop.log")
    assert target_dir.exists()
    assert resolved == (target_dir / "feedback_loop.log").resolve()

    # Second call: reuses existing directory without error
    resolved2 = ensure_log_directory(target_dir / "feedback_loop.log")
    assert target_dir.exists()
    assert resolved2 == resolved


def test_console_and_file_formatters():
    """Verify terminal and file formatters output timestamp, level, component, step, and file:line."""
    console_fmt = DetailedConsoleFormatter()
    file_fmt = DetailedFileFormatter()

    logger = logging.getLogger("feedback_loop.test_formatter")
    record = logger.makeRecord(
        name="feedback_loop.test_formatter",
        level=logging.INFO,
        fn="test_file.py",
        lno=42,
        msg="Execution step test message",
        args=(),
        exc_info=None,
        extra={"step": "STEP1_CLASSIFICATION", "component": "test_component"},
    )

    console_out = console_fmt.format(record)
    assert "[INFO   ]" in console_out or "INFO" in console_out
    assert "[test_component]" in console_out
    assert "[STEP: STEP1_CLASSIFICATION]" in console_out
    assert "test_file.py:42" in console_out
    assert "Execution step test message" in console_out

    file_out = file_fmt.format(record)
    assert "[test_component]" in file_out
    assert "[STEP: STEP1_CLASSIFICATION]" in file_out
    assert "test_file.py:42" in file_out


def test_json_formatter_produces_structured_schema():
    """Verify JSONFormatter outputs valid JSON with step, component, and file_path fields."""
    formatter = JSONFormatter()
    logger = logging.getLogger("feedback_loop.test_json")

    record = logger.makeRecord(
        name="feedback_loop.test_json",
        level=logging.WARNING,
        fn="orchestrator.py",
        lno=120,
        msg="Threshold breached",
        args=(),
        exc_info=None,
        extra={"step": "STEP3_ROUTER", "component": "feedback_loop.router", "custom_id": "fb_123"},
    )

    json_str = formatter.format(record)
    data = json.loads(json_str)

    assert data["level"] == "WARNING"
    assert data["logger"] == "feedback_loop.test_json"
    assert data["component"] == "feedback_loop.router"
    assert data["step"] == "STEP3_ROUTER"
    assert "orchestrator.py:120" in data["file_path"]
    assert data["message"] == "Threshold breached"
    assert data["custom_id"] == "fb_123"
    assert "timestamp" in data


def test_persistent_logging_to_log_and_jsonl(tmp_path):
    """Verify setup_feedback_logging writes both .log and .jsonl files with step details.

    Args:
        tmp_path: Filesystem path to the tmp.
    """
    log_dir = tmp_path / "test_logs"
    text_log = log_dir / "custom_feedback.log"
    json_log = log_dir / "custom_feedback.jsonl"

    setup_feedback_logging(
        level="INFO",
        log_file=str(text_log),
        enable_file_logging=True,
        json_log_file=str(json_log),
        enable_json_logging=True,
        log_dir=str(log_dir),
    )

    test_logger = get_feedback_logger("worker")
    log_step_info(test_logger, "TEST_STEP_A", "Sample log message for persistence test")
    log_step_warning(test_logger, "TEST_STEP_B", "Warning log message")

    assert text_log.exists()
    assert json_log.exists()

    text_content = text_log.read_text(encoding="utf-8")
    assert "[STEP: TEST_STEP_A]" in text_content
    assert "[STEP: TEST_STEP_B]" in text_content
    assert "Sample log message for persistence test" in text_content

    json_lines = [json.loads(line) for line in json_log.read_text(encoding="utf-8").strip().split("\n")]
    assert len(json_lines) >= 2
    steps = [jl.get("step") for jl in json_lines]
    assert "TEST_STEP_A" in steps
    assert "TEST_STEP_B" in steps


def test_record_builder_end_to_end_logging(tmp_path):
    """Verify RecordBuilder execution emits step logs across all pipeline stages.

    Args:
        tmp_path: Filesystem path to the tmp.
    """
    log_dir = tmp_path / "pipeline_logs"
    text_log = log_dir / "feedback_loop.log"
    json_log = log_dir / "feedback_loop.jsonl"

    setup_feedback_logging(
        level="INFO",
        log_file=str(text_log),
        json_log_file=str(json_log),
        log_dir=str(log_dir),
    )

    config = FeedbackLoopConfig()
    db = InMemoryDatabaseAdapter()
    evidence = InMemoryEvidenceAdapter()

    evidence.seed_snapshot(
        EvidenceSnapshot(
            response_id="resp_log_001",
            original_query="What is the TER of Axis Bluechip Fund?",
            response_text="The TER is 0.79% under direct plan.",
            entity_name="Axis Bluechip Fund",
            evidence_selected=[
                EvidenceChunk(
                    chunk_id="chk_001",
                    content="Axis Bluechip Fund TER is 0.82% according to recent circular.",
                )
            ],
        )
    )

    builder = RecordBuilder(config, db, evidence)
    record = FeedbackRecord(
        feedback_id="fb_log_001",
        session_id="sess_log_001",
        response_id="resp_log_001",
        user_id="analyst",
        feedback_type=FeedbackType.CORRECTION,
        rating=RatingType.NEGATIVE,
        notes="Actually the TER is 0.82%, not 0.79%",
        entity_name="Axis Bluechip Fund",
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
    )

    unified = builder.build(record)
    assert unified is not None

    # Inspect persistent files
    assert text_log.exists()
    assert json_log.exists()

    text_content = text_log.read_text(encoding="utf-8")
    assert "[STEP: BUILD_START]" in text_content
    assert "[STEP: STEP2_START]" in text_content
    assert "[STEP: STEP3_START]" in text_content
    assert "[STEP: STEP4_START]" in text_content
    assert "[STEP: BUILD_COMPLETE]" in text_content

    json_lines = [json.loads(line) for line in json_log.read_text(encoding="utf-8").strip().split("\n")]
    steps = [jl.get("step") for jl in json_lines]
    assert "BUILD_START" in steps
    assert "BUILD_COMPLETE" in steps
