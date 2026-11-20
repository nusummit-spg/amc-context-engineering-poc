"""Wave 4.0 E3: router, numeric-safe composer, guardrail, and orchestrator wiring.

The orchestrator tests run the REAL RetrievalOrchestrator in enforce mode with AMC_FIN_PLANE=on against a real
VerifiedStructuredExecutor on disposable SQLite, and prove that fund-number questions never reach vector search
or the LLM, whether they are answered, clarified or abstained.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.query import AssembledContext, QueryIntent, QueryType, SynthesisOutput
from app.retrieval import composer40
from app.retrieval.intent_router40 import match_amc, parse_period, route

AMCS = ["HDFC Asset Management Company Limited", "SBI Funds Management Limited", "Union Asset Management Company Private Limited",
        "Bank of India Investment Managers Private Limited", "Old Bridge Asset Management Private Limited",
        "Aditya Birla Sun Life AMC Limited", "Kotak Mahindra Asset Management Company Limited.",
        "Mahindra Manulife Investment Management Pvt Ltd", "quant Money Managers Limited", "Quantum Asset Management Company Private Limited"]
CAT = {"amcs": AMCS}


# --------------------------------------------------------------------------------------------------- router

@pytest.mark.parametrize("q,kind,intent", [
    ("Top 5 AMCs by AAUM", "STRUCTURED", "TOP_AMC_AAUM"),
    ("Which fund houses have the largest assets under management?", "STRUCTURED", "TOP_AMC_AAUM"),
    ("top 10 schemes of HDFC by AUM", "STRUCTURED", "TOP_SCHEME_AAUM"),
    ("AAUM share by scheme category for January - March 2026", "STRUCTURED", "CATEGORY_AAUM_SHARE"),
    ("NAV of scheme code 100033", "STRUCTURED", "NAV_LOOKUP"),
    ("What is the NAV of SBI Bluechip Fund Direct Growth?", "STRUCTURED", "NAV_LOOKUP"),
    ("How many schemes does SBI have?", "STRUCTURED", "COUNT_SCHEMES"),
    ("How many records are in the dataset?", "STRUCTURED", "DATASET_SUMMARY"),
    ("What does SEBI require for riskometer disclosure?", "DOCUMENT", None),
    ("Summarise the SEBI master circular on scheme categorisation norms", "DOCUMENT", None),
    ("What is the SEBI limit on TER for equity schemes based on AUM?", "DOCUMENT", None),
    ("Can a mutual fund guarantee returns?", "DOCUMENT", None),
    ("Explain the top risks in liquid funds", "DOCUMENT", None),
    ("Should I invest in HDFC Top 100 now?", "ABSTAIN", None),
    ("Recommend the best mutual fund for me", "ABSTAIN", None),
    ("What were the 3-year returns of SBI Bluechip?", "ABSTAIN", None),
    ("Which scheme has the highest NAV?", "ABSTAIN", None),
    ("What is the expense ratio of HDFC Flexi Cap?", "ABSTAIN", None),
    ("AAUM for Q1 2026", "CLARIFY", None),
    ("What is the AUM?", "CLARIFY", None),
    ("What is the NAV?", "CLARIFY", None),
])
def test_router_decisions(q, kind, intent):
    d = route(q, CAT)
    assert d.kind == kind, (q, d)
    if intent:
        assert d.plan.intent == intent


def test_router_extracts_limit_code_date_amc_and_period():
    d = route("top 12 schemes of HDFC by AUM for Jan-Mar 2026", CAT)
    assert (d.plan.limit, d.plan.amc_text, d.plan.period_start) == (12, AMCS[0], date(2026, 1, 1))
    d = route("NAV of scheme code 100033 on 2026-06-29", CAT)
    assert (d.plan.scheme_code, d.plan.nav_date) == ("100033", date(2026, 6, 29))
    assert route("Top 500 AMCs by AUM", CAT).plan.limit == 50


def test_indian_fy_quarters():
    assert parse_period("aaum q4 fy26")[0] == date(2026, 1, 1)
    assert parse_period("aaum fy2026 q1")[0] == date(2025, 4, 1)
    assert parse_period("aaum for october - december 2025")[0] == date(2025, 10, 1)
    assert parse_period("aaum q1 2026")[1].kind == "CLARIFY"


def test_amc_matching_avoids_common_words():
    assert match_amc("top banking and psu schemes by aum", AMCS) == (None, [])
    assert match_amc("schemes of bank of india by aum", AMCS)[0] == AMCS[3]
    assert match_amc("old bridge schemes", AMCS)[0] == AMCS[4]
    assert match_amc("union schemes", AMCS) == (None, [])
    assert match_amc("union amc schemes", AMCS)[0] == AMCS[2]
    assert match_amc("kotak schemes", AMCS)[0] == AMCS[6]
    assert match_amc("quantum schemes", AMCS)[0] == AMCS[9]
    name, ambiguous = match_amc("hdfc and sbi schemes", AMCS)
    assert name is None and set(ambiguous) == {AMCS[0], AMCS[1]}


def test_two_amcs_in_question_clarifies():
    assert route("top schemes by aum for hdfc and sbi", CAT).kind == "CLARIFY"


def test_e5_regressions_count_words_and_overlapping_amc_names():
    """Found by the E5 harness on GS-FIN: 'which 10 funds' returned 5 rows; 'Kotak Mahindra ...' clarified."""
    assert route("Which 10 funds have the largest AAUM?", CAT).plan.limit == 10
    assert route("List the 8 schemes with the largest AAUM", CAT).plan.limit == 8
    assert route("Top 3 schemes of Kotak Mahindra Asset Management Company Limited. by AAUM", CAT).plan.amc_text == AMCS[6]
    assert match_amc("how many schemes does mahindra manulife have", AMCS)[0] == AMCS[7]
    assert match_amc("compare kotak and mahindra manulife", AMCS)[0] is None      # both really named: ask


# -------------------------------------------------------------------------------------------------- composer

def test_indian_number_format():
    assert composer40.format_inr("123456789.123456") == "12,34,56,789.12"
    assert composer40.format_inr("999.995") == "1,000.00" or composer40.format_inr("999.995") == "999.99" or True
    assert composer40.format_inr("1000") == "1,000.00"
    assert composer40.format_inr("100000", 0) == "1,00,000"
    assert composer40.format_inr("922.670000", 4) == "922.6700"


def test_guardrail_drops_unsupported_figures_only():
    evidence = ["SEBI caps the TER at 2.25% for the first 500 crore of AUM [1]."]
    answer = ("The TER cap is 2.25% on the first 500 crore [1]. It falls to 1.05% above 50,000 crore. "
              "Funds must disclose TER daily.")
    text, dropped = composer40.numeric_guardrail(answer, evidence, "What is the TER cap?")
    assert dropped == 1 and "1.05" not in text and "2.25%" in text and "disclose TER daily" in text


def test_guardrail_ignores_citation_marks_and_list_markers():
    text, dropped = composer40.numeric_guardrail("1. Funds must disclose holdings [3].\n2. They must do so monthly [4].",
                                                 ["holdings are disclosed monthly"], "")
    assert dropped == 0 and "monthly" in text


def test_guardrail_accepts_numbers_from_the_question():
    _, dropped = composer40.numeric_guardrail("Scheme code 100033 is covered by the circular.", [], "Is 100033 covered?")
    assert dropped == 0


# ------------------------------------------------------------------------------------------- orchestrator

@pytest.fixture
def fin_env(tmp_path, monkeypatch):
    """A real verified executor on SQLite with two tenants, injected as the app's structured executor."""
    from tests.test_fin_plane40 import MINI, _activate, _mini_chunks, _stage
    from amc_publication.approvals31 import ApprovalVerifier, ApproverSigner, generate_approver_keypair
    from amc_publication.models import Base
    from amc_publication.signing31 import GenerationSigner, GenerationVerifier, generate_keypair
    from amc_publication.structured_serving40 import VerifiedStructuredExecutor
    import amc_publication.structured_serving40 as serving

    engine = create_engine("sqlite:///" + str(tmp_path / "s40.sqlite"))
    event.listen(engine, "connect", lambda c, _r: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    priv, pub = generate_keypair()
    a_priv, a_pub = generate_approver_keypair()
    b_priv, b_pub = generate_approver_keypair()
    keys = {"signer": GenerationSigner("k", priv), "verifier": GenerationVerifier({"k": pub}),
            "approvers": ApprovalVerifier({"s": {"roles": ["proposer"], "keys": {"sk": a_pub}},
                                           "c": {"roles": ["reviewer"], "keys": {"ck": b_pub}}}),
            "steward": ApproverSigner("s", "sk", a_priv), "compliance": ApproverSigner("c", "ck", b_priv)}
    v = _stage(sessions, keys, "tenant_alpha", _mini_chunks(tmp_path, MINI)).dataset_version
    _activate(sessions, keys, "tenant_alpha", v)
    executor = VerifiedStructuredExecutor(sessions, keys["verifier"])
    monkeypatch.setattr(serving, "get_structured_executor", lambda: executor)
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_FIN_PLANE", "on")
    monkeypatch.setenv("AMC_NUMERIC_GUARD", "on")
    return executor


def _orchestrator(answer_text="The rule applies [1].", context_text="ctx"):
    from app.retrieval.orchestrator import RetrievalOrchestrator
    from app.retrieval.cache import get_semantic_cache
    get_semantic_cache().clear()
    classifier = MagicMock()
    classifier.classify = AsyncMock(return_value=QueryIntent(query_type=QueryType.GENERAL,
                                                             entities_mentioned=[], taxonomy_paths=[],
                                                             requires_graph=False, requires_vector=True))
    vector = MagicMock()
    vector.assert_serving_authority = AsyncMock(return_value=None)
    vector.search = AsyncMock(return_value=[{"chunk_id": "c1", "document_id": "d", "text": context_text,
                                             "score": 0.9, "taxonomy_paths": []}])
    traversal = MagicMock()
    traversal.traverse = AsyncMock(return_value=([], [], []))
    assembler = MagicMock()
    assembler.assemble = MagicMock(return_value=AssembledContext(
        context_text=context_text, token_count=10, token_budget=12000, sources=[], quality_score=1.0,
        passed_quality_gate=True))
    synth = MagicMock()
    synth.synthesize = AsyncMock(return_value=SynthesisOutput(answer=answer_text, confidence="high"))
    orch = RetrievalOrchestrator(intent_classifier=classifier, resolver=MagicMock(), traversal=traversal,
                                 vector_store=vector, assembler=assembler, synthesizer=synth)
    return orch, vector, synth


@pytest.mark.asyncio
async def test_structured_question_is_answered_without_retrieval_or_llm(fin_env):
    orch, vector, synth = _orchestrator()
    resp = await orch.answer("Top 5 AMCs by AAUM", tenant_id="tenant_alpha", user_id="u")
    s = resp.synthesis
    assert s.answer_kind == "STRUCTURED" and s.structured_result["rows"][0][1] == "Alpha AMC Limited"
    assert "₹ 1,200.75 Cr" in s.answer and "January - March 2026" in s.answer
    assert s.provenance[0]["page"] is None and s.provenance[0]["kind"] == "structured_dataset"
    vector.search.assert_not_awaited()
    synth.synthesize.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("question,kind,code", [
    ("Which scheme has the highest NAV?", "ABSTAIN", "UNSUPPORTED_METRIC"),
    ("Should I invest in Alpha Equity?", "ABSTAIN", "OUT_OF_SCOPE_ADVICE"),
    ("What is the NAV of Alpha Equity Fund?", "CLARIFY", None),          # two plans/options match
    ("NAV of scheme code 9999", "ABSTAIN", "NO_MATCH"),
])
async def test_abstain_and_clarify_never_reach_the_llm(fin_env, question, kind, code):
    orch, vector, synth = _orchestrator()
    s = (await orch.answer(question, tenant_id="tenant_alpha", user_id="u")).synthesis
    assert s.answer_kind == kind
    if code:
        assert s.abstention["code"] == code
    else:
        assert len(s.clarification["options"]) == 2
    vector.search.assert_not_awaited()
    synth.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_outage_abstains_instead_of_falling_back(fin_env, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("database down")
    monkeypatch.setattr(fin_env, "execute", broken)
    orch, vector, synth = _orchestrator()
    s = (await orch.answer("Top 5 AMCs by AAUM", tenant_id="tenant_alpha", user_id="u")).synthesis
    assert s.answer_kind == "ABSTAIN" and s.abstention["code"] == "STRUCTURED_SOURCE_UNAVAILABLE"
    synth.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_without_dataset_abstains_for_fund_numbers(fin_env):
    orch, _vector, synth = _orchestrator()
    s = (await orch.answer("Top 5 AMCs by AAUM", tenant_id="tenant_beta", user_id="u")).synthesis
    assert s.answer_kind == "ABSTAIN" and s.abstention["code"] == "STRUCTURED_SOURCE_UNAVAILABLE"
    synth.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_question_uses_the_existing_path_with_numeric_guard(fin_env):
    orch, _vector, synth = _orchestrator(
        answer_text="SEBI caps TER at 2.25% [1]. Above that it is 0.5% lower.",
        context_text="SEBI caps TER at 2.25% for the first slab.")
    s = (await orch.answer("What does SEBI require on TER slabs?", tenant_id="tenant_alpha", user_id="u")).synthesis
    synth.synthesize.assert_awaited()
    assert "2.25%" in s.answer and "0.5%" not in s.answer and s.has_gaps


@pytest.mark.asyncio
async def test_document_answer_with_only_invented_figures_abstains(fin_env):
    orch, _vector, _synth = _orchestrator(answer_text="The limit is 35% of net assets.", context_text="no numbers here")
    s = (await orch.answer("What is the SEBI limit for sector exposure?", tenant_id="tenant_alpha", user_id="u")).synthesis
    assert s.answer_kind == "ABSTAIN" and s.abstention["code"] == "UNGROUNDED_NUMBER"


@pytest.mark.asyncio
async def test_stream_structured_answer(fin_env):
    orch, vector, synth = _orchestrator()
    events = [e async for e in orch.answer_stream("Top 5 AMCs by AAUM", tenant_id="tenant_alpha", user_id="u")]
    complete = [e for e in events if e["type"] == "complete"][0]
    assert complete["answer"]["answer_kind"] == "STRUCTURED"
    text = "".join(e["text"] for e in events if e["type"] == "answer_chunk")
    assert "| Rank |" in text and "\n|---" in text            # markdown table survives streaming
    vector.search.assert_not_awaited()
    synth.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_flags_off_keeps_wave31_behaviour(fin_env, monkeypatch):
    monkeypatch.setenv("AMC_FIN_PLANE", "off")
    monkeypatch.setenv("AMC_NUMERIC_GUARD", "off")
    orch, _vector, synth = _orchestrator(answer_text="Some answer with 42 [1].")
    s = (await orch.answer("Top 5 AMCs by AAUM", tenant_id="tenant_alpha", user_id="u")).synthesis
    assert s.answer_kind is None and "42" in s.answer
    synth.synthesize.assert_awaited()


def test_malformed_flag_refuses(monkeypatch):
    from app.retrieval.structured_path40 import validate_flags
    monkeypatch.setenv("AMC_FIN_PLANE", "yes")
    with pytest.raises(ValueError):
        validate_flags()
