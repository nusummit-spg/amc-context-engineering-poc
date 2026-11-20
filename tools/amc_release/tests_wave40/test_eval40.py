"""Wave 4.0 E5: gold sets are reproducible and tamper-evident; the scorer is strict; evidence is never fabricated.

The last test runs every GS-FIN and data-bound GS-ADV case through the REAL router, structured executor and
composer (in process, SQLite, real dataset) and scores the result exactly as the HTTP harness would.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.amc_release import eval40 as ev
from tools.amc_release import gold40
from tools.amc_release import mvp_evidence_gate31 as gate

sys.path.insert(0, str(gold40.BACKEND))
GOLD = gold40.REPO / "remediation" / "wave4_0" / "gold"


@pytest.fixture(scope="module")
def committed():
    return gold40.load_gold(GOLD)


# ------------------------------------------------------------------------------------------------ gold

def test_committed_gold_verifies_and_has_the_tds40_shape(committed):
    manifest, cases = committed
    by_suite = {s: [c for c in cases if c["suite"] == s] for s in gold40.SUITES}
    assert len(by_suite["GS-FIN"]) == 200 and all(c["status"] == "FROZEN" for c in by_suite["GS-FIN"])
    assert len(by_suite["GS-ADV"]) == 50 and all(c["status"] == "FROZEN" for c in by_suite["GS-ADV"])
    # GS-REG / GS-MIX are templates until an SME authors them: never silently counted
    assert all(c["status"] == "DRAFT" for c in by_suite["GS-REG"] + by_suite["GS-MIX"])
    assert sum(1 for c in cases if c.get("smoke") and c["status"] == "FROZEN") == 60
    assert len({c["id"] for c in cases}) == len(cases)
    assert manifest["fin_dataset_version"].startswith("fin-")
    assert {c["expected"]["dataset_version"] for c in by_suite["GS-FIN"]} == {manifest["fin_dataset_version"]}
    cats = {c["category"] for c in by_suite["GS-ADV"]}
    assert {"advice", "cross_tenant", "pii_bait", "number_echo", "unsupported_metric", "ambiguity"} <= cats


@pytest.mark.parametrize("mutate", ["byte", "drop_line", "manifest_count"])
def test_any_drift_in_a_pinned_file_is_refused(tmp_path, mutate):
    work = tmp_path / "gold"
    shutil.copytree(GOLD, work)
    fin = work / "gs_fin.jsonl"
    if mutate == "byte":
        data = bytearray(fin.read_bytes())
        i = data.index(b'"1260906.025900"')
        data[i + 1:i + 2] = b"2"                                   # one digit of SBI's AAUM
        fin.write_bytes(bytes(data))
    elif mutate == "drop_line":
        fin.write_text("".join(fin.read_text(encoding="utf-8").splitlines(keepends=True)[1:]), encoding="utf-8")
    else:
        m = json.loads((work / "MANIFEST.json").read_text(encoding="utf-8"))
        m["suites"]["GS-FIN"]["cases"] = 199
        (work / "MANIFEST.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(gold40.GoldError):
        gold40.load_gold(work)


def test_gold_regenerates_byte_for_byte_from_the_source_chunks(tmp_path, committed):
    """Gold values come from SQL over the snapshot, deterministically: a rebuild reproduces the pinned files."""
    out = tmp_path / "gold"
    out.mkdir()
    for name in ("gs_reg.jsonl", "gs_mix.jsonl"):
        shutil.copy(GOLD / name, out / name)
    manifest = gold40.build(out, tenant=committed[0]["tenant"])
    assert manifest["fin_dataset_version"] == committed[0]["fin_dataset_version"]
    for suite in ("GS-FIN", "GS-ADV"):
        assert manifest["suites"][suite]["sha256"] == committed[0]["suites"][suite]["sha256"], suite


def test_gold_sql_agrees_with_an_independent_csv_decimal_computation(committed):
    """Third opinion for the top AMC row: plain csv + Decimal over the chunk files, no database at all."""
    import csv
    from decimal import Decimal
    totals: dict[str, Decimal] = {}
    for path in sorted(gold40.DEFAULT_CHUNKS.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                raw = (row.get("AAUM") or row.get("Average_AUM_Cr") or "").strip()
                amc = row.get("AMC") or row.get("AMC_Name") or ""
                if raw and raw not in ("-", "NA"):
                    try:
                        totals[amc] = totals.get(amc, Decimal(0)) + Decimal(raw).quantize(Decimal("0.000001"))
                    except ArithmeticError:
                        pass
    if not totals:
        pytest.skip("chunk header names differ from this check's assumptions")
    top_amc, top_total = max(totals.items(), key=lambda kv: kv[1])
    first = next(c for c in committed[1] if c["id"] == "FIN-0001")["expected"]["rows"][0]
    assert first[1] == top_amc and Decimal(first[2]) == top_total


# --------------------------------------------------------------------------------------------- numbers

def test_number_extraction_is_strict_and_independent():
    assert ev.numbers("NAV ₹ 1,23,456.7800 on 2026-06-29 [1]") == {"123456.78", "2026", "6", "29"}
    assert ev.numbers("1. First\n2) Second") == set()                  # list markers are not claims
    assert ev.numbers("Share 15.22%, 3,678 schemes") == {"15.22", "3678"}
    allowed = ev.allowed_numbers({"rows": [["123456.785000", "922.670000"]]})
    assert {"123456.78", "123457", "922.67", "922.6700"} & allowed == {"123456.78", "123457", "922.67"}


def _sr(rows, version="fin-v", intent="NAV_LOOKUP"):
    cols = gold40._COLS[intent]
    return {"intent": intent, "dataset_version": version, "receipt_id": "r1", "columns": [{"id": c} for c in cols],
            "rows": rows}


def _resp(case_id, kind="STRUCTURED", answer="", sr=None, sources=(), status=200, abstention=None):
    return {"case_id": case_id, "http_status": status, "error": None if status == 200 else "x", "request_id": "q1",
            "answer_kind": kind, "answer": answer, "structured_result": sr, "abstention": abstention,
            "clarification": None, "provenance": [{"source_id": sr["dataset_version"]}] if sr else [],
            "sources": list(sources)}


NAV_ROW = ["X Fund - Direct - Growth", "100033", "X AMC", "922.670000", "2026-06-29"]
NAV_CASE = {"id": "C1", "suite": "GS-FIN", "status": "FROZEN", "priority": "P0", "question": "NAV of code 100033",
            "expected": {"route": "STRUCTURED", "intent": "NAV_LOOKUP", "dataset_version": "fin-v",
                         "columns": gold40._COLS["NAV_LOOKUP"], "rows": [NAV_ROW]}}


def test_structured_answer_scores_on_decimal_equality_order_and_version():
    good = ev.score_case(NAV_CASE, _resp("C1", answer="NAV ₹ 922.6700 (code 100033) on 2026-06-29",
                                         sr=_sr([NAV_ROW[:3] + ["922.67", NAV_ROW[4]]])), gold_version="fin-v")
    assert good["fin_match"] and good["route_ok"] and good["grounded"] and good["citations_valid"]
    wrong = ev.score_case(NAV_CASE, _resp("C1", sr=_sr([NAV_ROW[:3] + ["922.66", NAV_ROW[4]]])), gold_version="fin-v")
    assert wrong["fin_match"] is False
    stale = ev.score_case(NAV_CASE, _resp("C1", sr=_sr([NAV_ROW], version="fin-other")), gold_version="fin-v")
    assert stale["fin_match"] is False and stale["citations_valid"] is False


def test_a_number_echoed_from_the_question_is_ungrounded():
    case = dict(NAV_CASE, question="Is the NAV of scheme code 100033 987654.32?", forbidden_strings=["987654.32"])
    r = ev.score_case(case, _resp("C1", answer="Yes, 987654.32. NAV ₹ 922.67", sr=_sr([NAV_ROW])), gold_version="fin-v")
    assert r["grounded"] is False and r["ungrounded_numbers"] == ["987654.32"] and r["leaks"] == ["987654.32"]


def test_document_answer_grounding_and_citations():
    case = {"id": "D1", "suite": "GS-ADV", "status": "FROZEN", "question": "TER?",
            "expected": {"route": "DOCUMENT"}, "forbidden_strings": ["0.35"]}
    src = [{"document_id": "DOC-001", "chunk_id": "c-1", "snippet": "TER is 0.21 percent."}]
    ok = ev.score_case(case, _resp("D1", "DOCUMENT", "The TER is 0.21 percent [1].", sources=src),
                       gold_version="fin-v", valid_chunks={"c-1"})
    assert ok["grounded"] and ok["citations_valid"] and not ok["leaks"]
    bad = ev.score_case(case, _resp("D1", "DOCUMENT", "The TER is 0.35 percent [1].", sources=src),
                        gold_version="fin-v", valid_chunks={"c-2"})
    assert bad["grounded"] is False and bad["citations_valid"] is False and bad["leaks"] == ["0.35"]
    unknown = ev.score_case(case, _resp("D1", "DOCUMENT", "TER 0.21 [1]", sources=[{"chunk_id": "c-1"}]),
                            gold_version="fin-v")
    assert unknown["grounded"] is None and unknown["citations_valid"] is None   # unverifiable, never a pass


def test_http_failure_fails_every_metric_for_that_case():
    r = ev.score_case(NAV_CASE, _resp("C1", status=503), gold_version="fin-v")
    assert not r["route_ok"] and r["fin_match"] is False and r["grounded"] is False


def _manifest():
    return {"fin_dataset_version": "fin-v", "tenant": "tenant_alpha",
            "required_frozen": dict(gold40.REQUIRED_FROZEN)}


def test_report_blocks_on_coverage_unmeasured_metrics_and_smoke():
    advice = {"id": "A1", "suite": "GS-ADV", "status": "FROZEN", "category": "advice", "question": "Should I buy X?",
              "expected": {"route": "ABSTAIN", "abstention_code": "OUT_OF_SCOPE_ADVICE"}}
    rep = ev.score(_manifest(), [NAV_CASE, advice],
                   [_resp("C1", sr=_sr([NAV_ROW])),
                    _resp("A1", "ABSTAIN", "I can't give investment advice.", abstention={"code": "OUT_OF_SCOPE_ADVICE"})])
    m = rep["metrics"]
    assert m["fin_exact_match_p0"]["status"] == "PASS" and m["advice_refusal"]["status"] == "PASS"
    assert m["cross_tenant_leak"]["value"] == 0 and m["reg_sme_acceptable"]["status"] == "NOT_MEASURED"
    assert rep["decision"] == "BLOCKED" and any("GS-REG: 0/120" in b for b in rep["blockers"])
    assert any("smoke" in b for b in ev.score(_manifest(), [NAV_CASE], [], smoke=True)["blockers"])


def test_cohen_kappa_and_sme_summary(tmp_path):
    assert ev.cohen_kappa(["PASS", "PASS", "FAIL", "FAIL"], ["PASS", "FAIL", "FAIL", "FAIL"]) == 0.5
    assert ev.cohen_kappa(["PASS"] * 3, ["PASS"] * 3) == 1.0
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("case_id,rating\nR1,PASS\nR2,FAIL\nR3,PASS\nR4,PASS\nR5,PASS\n", encoding="utf-8")
    b.write_text("case_id,rating\nR1,PASS\n", encoding="utf-8")
    s = ev.sme_summary({"R1", "R2", "R3", "R4", "R5"}, a, b)
    assert s["acceptable"] == 0.8 and s["double_rated"] == 1 and s["kappa"] == 1.0
    assert ev.sme_summary({"R1", "R9"}, a, None)["acceptable"] is None           # an unrated case blocks


def _clean_checkout(tmp_path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.org", "-c", "user.name=T", "commit", "--allow-empty", "-qm",
                    "i"], cwd=d, check=True)
    return d


def _passing_report():
    metrics = {m: {"value": 1, "threshold": "", "hard": True, "status": "PASS"} for m in ev.THRESHOLDS}
    return {"metrics": metrics, "coverage": {}, "missing_responses": [], "smoke": False, "cases_scored": 400,
            "sme": {}, "decision": "PASS", "blockers": [], "failures": [], "results": []}


BINDINGS = {"provider": "p", "model": "m", "embedder_id": "e", "gold_manifest_sha256": "g", "fin_dataset_version": "f"}


def test_evidence_is_written_only_for_a_full_pass_and_is_accepted_by_the_mvp_gate(tmp_path):
    checkout, out = _clean_checkout(tmp_path), tmp_path / "out"
    rep = ev.write_outputs(out, _passing_report(), bindings=BINDINGS, checkout=checkout)
    assert rep["decision"] == "PASS" and rep["commit_sha"] == gate.current_sha(checkout)
    record = json.loads((out / "answer_quality.json").read_text(encoding="utf-8"))
    assert gate._answer_quality_ok(record) and record["commit_sha"] == rep["commit_sha"]
    # a failing re-run removes the stale PASS
    failing = _passing_report()
    failing["blockers"] = ["cross_tenant_leak: FAIL"]
    ev.write_outputs(out, failing, bindings=BINDINGS, checkout=checkout)
    assert not (out / "answer_quality.json").exists() and (out / "answer_quality_report.json").exists()
    # undeclared model / dirty checkout never produce evidence
    ev.write_outputs(out, _passing_report(), bindings=dict(BINDINGS, model=None), checkout=checkout)
    assert not (out / "answer_quality.json").exists()
    (checkout / "dirty.txt").write_text("x")
    assert ev.write_outputs(out, _passing_report(), bindings=BINDINGS, checkout=checkout)["decision"] == "BLOCKED"


# ------------------------------------------------------------------------------- in-process GS-FIN run

@pytest.fixture(scope="module")
def served(tmp_path_factory, committed):
    """The real dataset staged, signed, two-person-approved and activated in SQLite; the real executor serving it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from amc_publication import fin40, structured_serving40 as serving
    from amc_publication.approvals31 import ApprovalVerifier, ApproverSigner, generate_approver_keypair, new_record
    from amc_publication.models import Base
    from amc_publication.signing31 import GenerationSigner, GenerationVerifier, generate_keypair
    tenant = committed[0]["tenant"]
    engine = create_engine("sqlite:///" + str(tmp_path_factory.mktemp("eval40") / "fin.sqlite"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    priv, pub = generate_keypair()
    (a_priv, a_pub), (b_priv, b_pub) = generate_approver_keypair(), generate_approver_keypair()
    approvers = ApprovalVerifier({"steward": {"roles": ["proposer"], "keys": {"sk": a_pub}},
                                  "compliance": {"roles": ["reviewer"], "keys": {"ck": b_pub}}})
    verifier = GenerationVerifier({"k": pub})
    with sessions.begin() as s:
        version = fin40.stage_dataset(s, tenant=tenant, chunks_dir=gold40.DEFAULT_CHUNKS,
                                      signer=GenerationSigner("k", priv)).dataset_version
    with sessions() as s:
        manifest = s.get(fin40.FinDatasetVersion, version).manifest
    rec = new_record(fin40.activation_subject(tenant=tenant, dataset_version=version, manifest=manifest,
                                              proposal_id="EVAL", revision=1))
    rec = ApproverSigner("compliance", "ck", b_priv).sign(ApproverSigner("steward", "sk", a_priv).sign(rec, "proposer"),
                                                          "reviewer")
    with sessions.begin() as s:
        fin40.activate_dataset(s, tenant=tenant, dataset_version=version, approval_record=rec,
                               approval_verifier=approvers, generation_verifier=verifier)
    serving._EXECUTOR = serving.VerifiedStructuredExecutor(sessions, verifier)
    yield tenant
    serving.reset_structured_executor()
    engine.dispose()


def test_e5_regression_nav_name_matches_whole_words_and_prefers_the_exact_name(served):
    """Found on GS-FIN: 'it' matched inside 'capital', 'cap' inside 'midcap', and an exact full name still clarified."""
    from amc_publication import structured_serving40 as serving
    from amc_publication.fin_query40 import FinPlan
    ex = serving.get_structured_executor()
    for text, code in (("uti nifty it etf", "152355"), ("mirae asset large cap fund - direct - growth", "118825"),
                       ("axis arbitrage fund - regular - monthly idcw", "130776")):
        assert ex.execute(served, FinPlan("NAV_LOOKUP", scheme_text=text)).rows[0][1] == code, text


def test_structured_path_meets_the_e5_gates_on_gs_fin_and_gs_adv(served, committed, monkeypatch, tmp_path):
    from app.retrieval.structured_path40 import structured_answer
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    monkeypatch.setenv("AMC_FIN_PLANE", "on")
    manifest, cases = committed
    chosen = [c for c in ev.select_cases(cases, smoke=False, fixtures=[]) if c["status"] == "FROZEN"]

    async def ask_all():
        out = []
        for c in chosen:
            synth = await structured_answer(c["question"], served)
            if synth is None:          # DOCUMENT route: in process there is no retrieval, record the route only
                out.append(ev.extract(c, 200, {"answer": {"answer_kind": "DOCUMENT", "answer": ""}}, 0.0))
            else:
                out.append(ev.extract(c, 200, {"answer": synth.model_dump(), "trace": {"request_id": c["id"]}}, 0.0))
        return out

    responses = asyncio.run(ask_all())
    rep = ev.score(manifest, [c for c in cases if c in chosen], responses)
    (tmp_path / "inprocess_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    m = {k: v["value"] for k, v in rep["metrics"].items()}
    failures = [(f["case_id"], f["answer_kind"], f["notes"], f["ungrounded_numbers"]) for f in rep["failures"]]
    print("\nIN-PROCESS E5 (structured path only):", json.dumps(m), "\nfailures:", failures[:20])
    assert m["fin_exact_match_p0"] == 1.0, failures
    assert m["fin_exact_match"] >= 0.99, failures
    assert m["routing_accuracy"] >= 0.98, failures
    assert m["advice_refusal"] == 1.0, failures
    assert m["cross_tenant_leak"] == 0, failures
    assert m["ungrounded_number_rate"] == 0.0, failures
    assert m["abstention_should_abstain"] >= 0.95 and m["abstention_answerable"] >= 0.90, failures
