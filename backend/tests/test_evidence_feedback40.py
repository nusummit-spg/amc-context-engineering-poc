"""Wave 4.0 E9/E7: evidence recorded by the fence before release, feedback bound to the caller's own evidence,
readiness and the perimeter additions."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from amc_publication import evidence40 as ev
from amc_publication.models import Base
from amc_publication.request_fence29 import VerifiedOrchestratorFence29
from amc_publication.serving27 import ServingDenied
from app.models.query import SynthesisOutput

KEY = ("tenant_alpha", "gen-1", "gen-1", 3, "work-1", "rcpt-1")


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "ev40.sqlite"))
    event.listen(engine, "connect", lambda c, _r: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def enforce(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_QE_POSTGRES", "on")
    monkeypatch.setenv("AMC_PILOT_FEEDBACK", "on")


class _Reader:
    def __init__(self):
        self.calls = 0

    async def assert_serving_authority(self, tenant):
        self.calls += 1
        return SimpleNamespace(tenant=tenant, generation_id="gen-1", digest="gen-1", epoch=3, work_id="work-1",
                               receipt_id="rcpt-1")


def _delegate(synth: SynthesisOutput, request_id="req-1"):
    d = SimpleNamespace()
    trace = SimpleNamespace(request_id=request_id, serving_engine="v2_structured", request_total_ms=12.5)
    d.answer = AsyncMock(return_value=SimpleNamespace(synthesis=synth, trace=trace))

    async def stream(*_a, **_k):
        yield {"type": "answer_chunk", "text": "x"}
        yield {"type": "complete", "answer": synth.model_dump(), "trace": {"request_id": request_id + "-s"}}
    d.answer_stream = stream
    return d


STRUCTURED = SynthesisOutput(answer="table", answer_kind="STRUCTURED", provenance=[{"source_id": "fin-v1"}],
                             structured_result={"dataset_version": "fin-v1", "receipt_id": "fr-1",
                                                "result_set_hash": "sha256:abc"})


@pytest.mark.asyncio
async def test_fence_records_evidence_before_release(sessions, enforce):
    fence = VerifiedOrchestratorFence29(_delegate(STRUCTURED), _Reader(), evidence_sessions=sessions)
    await fence.answer(query="Top AMCs, mail me at a@b.com", tenant_id="tenant_alpha", user_id="alice")
    with sessions() as s:
        row = s.get(ev.QueryEvidence40, "req-1")
    assert (row.tenant, row.user_id, row.answer_kind, row.channel) == ("tenant_alpha", "alice", "STRUCTURED", "answer")
    assert (row.faiss_generation_id, row.faiss_receipt_id) == ("gen-1", "rcpt-1")
    assert (row.fin_dataset_version, row.fin_receipt_id, row.structured_result_hash) == ("fin-v1", "fr-1", "sha256:abc")
    assert "a@b.com" not in row.question_scrubbed and len(row.answer_sha256) == 64


@pytest.mark.asyncio
async def test_stream_evidence_recorded_from_complete_frame(sessions, enforce):
    fence = VerifiedOrchestratorFence29(_delegate(STRUCTURED), _Reader(), evidence_sessions=sessions)
    frames = [f async for f in fence.answer_stream(query="q", tenant_id="tenant_alpha", user_id="alice")]
    assert frames[-1]["type"] == "complete"
    with sessions() as s:
        assert s.get(ev.QueryEvidence40, "req-1-s").channel == "stream"


@pytest.mark.asyncio
async def test_answer_withheld_when_evidence_cannot_be_written(sessions, enforce, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(ev, "record", broken)
    fence = VerifiedOrchestratorFence29(_delegate(STRUCTURED), _Reader(), evidence_sessions=sessions)
    with pytest.raises(ServingDenied, match="withheld"):
        await fence.answer(query="q", tenant_id="tenant_alpha", user_id="alice")
    frames = []
    with pytest.raises(ServingDenied):
        async for f in fence.answer_stream(query="q", tenant_id="tenant_alpha", user_id="alice"):
            frames.append(f)
    assert frames == []                                   # nothing released, not even partial chunks


@pytest.mark.asyncio
async def test_evidence_off_by_default(sessions, monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.delenv("AMC_QE_POSTGRES", raising=False)
    fence = VerifiedOrchestratorFence29(_delegate(STRUCTURED), _Reader(), evidence_sessions=sessions)
    await fence.answer(query="q", tenant_id="tenant_alpha", user_id="alice")
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(ev.QueryEvidence40)) == 0


def _seed(sessions, request_id="req-1", tenant="tenant_alpha", user="alice"):
    row = ev.evidence_row(tenant=tenant, user_id=user, channel="answer", generation_key=KEY, question="q",
                          synthesis=STRUCTURED, trace={"request_id": request_id})
    ev.record(sessions, row)


def test_feedback_binds_to_own_evidence_only(sessions):
    _seed(sessions)
    with sessions.begin() as s:
        ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", rating="DOWN",
                           reason="WRONG_NUMBER", comment="call me on 9876543210")
    with sessions() as s:
        fb = s.scalars(select(ev.PilotFeedback40)).one()
    assert fb.reason == "WRONG_NUMBER" and "9876543210" not in fb.comment_scrubbed
    for tenant, user in (("tenant_alpha", "bob"), ("tenant_beta", "alice")):
        with pytest.raises(ev.FeedbackRefused) as err:
            with sessions.begin() as s:
                ev.submit_feedback(s, tenant=tenant, user_id=user, request_id="req-1", rating="UP",
                                   reason="HELPFUL", comment=None)
        assert err.value.status == 404                    # same answer as a missing request: no existence leak
    with pytest.raises(ev.FeedbackRefused) as err:
        with sessions.begin() as s:
            ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="nope", rating="UP",
                               reason="HELPFUL", comment=None)
    assert err.value.status == 404


def test_feedback_once_per_answer_and_validated(sessions):
    _seed(sessions)
    with sessions.begin() as s:
        ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", rating="UP",
                           reason="HELPFUL", comment=None)
    with pytest.raises(ev.FeedbackRefused) as err:
        with sessions.begin() as s:
            ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", rating="DOWN",
                               reason="OTHER", comment=None)
    assert err.value.status == 409
    for bad in ({"rating": "MEH"}, {"reason": "ANGRY"}, {"comment": "x" * 1001}):
        args = {"rating": "UP", "reason": "HELPFUL", "comment": None, **bad}
        with pytest.raises(ev.FeedbackRefused) as err:
            with sessions.begin() as s:
                ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", **args)
        assert err.value.status == 422


def test_feedback_changes_no_other_table(sessions):
    _seed(sessions)
    with sessions() as s:
        before = {t.name: s.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}
    with sessions.begin() as s:
        ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", rating="DOWN",
                           reason="OUTDATED", comment=None)
    with sessions() as s:
        after = {t.name: s.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}
    changed = {k for k in after if after[k] != before[k]}
    assert changed == {"pilot_feedback_v40"}


def test_feedback_export_is_read_only_join(sessions):
    _seed(sessions)
    with sessions.begin() as s:
        ev.submit_feedback(s, tenant="tenant_alpha", user_id="alice", request_id="req-1", rating="DOWN",
                           reason="WRONG_CITATION", comment="wrong doc")
    with sessions() as s:
        pack = ev.export_feedback(s, "tenant_alpha")
        assert ev.export_feedback(s, "tenant_beta") == []
    assert pack[0]["reason"] == "WRONG_CITATION" and pack[0]["fin_dataset_version"] == "fin-v1"


# ------------------------------------------------------------------------------------------- perimeter + routes

def test_perimeter_admits_w40_routes_only_as_designed(monkeypatch):
    from app.api.pilot_perimeter31 import is_pilot_route_allowed
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_PILOT_FEEDBACK", "off")
    assert is_pilot_route_allowed("GET", "/api/ready")
    assert not is_pilot_route_allowed("POST", "/api/ready")
    assert not is_pilot_route_allowed("POST", "/api/feedback/v40")
    monkeypatch.setenv("AMC_PILOT_FEEDBACK", "on")
    assert is_pilot_route_allowed("POST", "/api/feedback/v40")
    assert not is_pilot_route_allowed("GET", "/api/feedback/v40")
    assert not is_pilot_route_allowed("POST", "/api/feedback")              # legacy feedback stays denied
    assert not is_pilot_route_allowed("POST", "/api/feedback/v40/../admin")


def test_readiness_reports_not_ready_with_reasons(monkeypatch):
    from app.api.routes.pilot40 import readiness_checks
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "off")
    monkeypatch.delenv("AMC_PILOT_TENANTS", raising=False)
    checks = readiness_checks()
    assert checks["verified_mode"]["ok"] is False
    assert checks["tenants"] == {"ok": False, "detail": "AMC_PILOT_TENANTS is not set"}
    assert checks["database"]["ok"] is False                       # not a migrated PostgreSQL
    assert set(checks) == {"verified_mode", "database", "trusted_keys", "provider_policy", "neo4j", "tenants"}
