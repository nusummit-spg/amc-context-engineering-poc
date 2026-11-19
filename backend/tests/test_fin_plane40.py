"""Wave 4.0 E1/E2: verified structured (fin) plane on disposable SQLite.

The same module runs on PostgreSQL in tests/live40 (real row locks); here we prove the logic: reconciliation,
exactness, signatures, two-person approval, atomic activation, rollback-by-reactivation, tenant isolation,
mid-request authority change and tamper detection.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import sessionmaker

from amc_publication import fin40 as fin
from amc_publication.approvals31 import ApprovalRefused, ApprovalVerifier, ApproverSigner, generate_approver_keypair, new_record
from amc_publication.fin_query40 import FinPlan, FinQueryError
from amc_publication.models import Base
from amc_publication.serving27 import ServingDenied
from amc_publication.signing31 import GenerationSigner, GenerationVerifier, generate_keypair
from amc_publication.structured_serving40 import VerifiedStructuredExecutor
from amc_publication.types import Conflict, VerificationFailed

CHUNKS = Path(__file__).resolve().parents[1] / "data" / "source_docs" / "chunks"
HEADER = ",".join(fin.EXPECTED_HEADER)


def _mini_chunks(tmp: Path, rows: list[str], name="mini") -> Path:
    d = tmp / name
    d.mkdir()
    (d / "c1.csv").write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "original_rows": len(rows), "chunk_count": 1,
        "chunks": [{"chunk_num": 1, "filename": "c1.csv", "rows": len(rows), "start_row": 1, "end_row": len(rows)}]}))
    return d


MINI = [
    "1001,Alpha Equity Fund,Alpha AMC Limited,Open Ended,Equity Scheme - Large Cap Fund,Alpha Equity Fund - Direct Plan - Growth,500,100.123456,2026-06-29,1000.5,January - March 2026,INF1,-,INF1,2010-01-01,",
    "1002,Alpha Equity Fund,Alpha AMC Limited,Open Ended,Equity Scheme - Large Cap Fund,Alpha Equity Fund - Regular Plan - IDCW Payout,500,90.5,2026-06-29,200.25,January - March 2026,INF2,-,INF2,2010-01-01,",
    "2001,Beta Debt Fund,Beta AMC Limited,Open Ended,Debt Scheme - Liquid Fund,Beta Debt Fund - Direct - Growth,500,1500.0000004,2026-06-29,1200.75,January - March 2026,INF3,-,INF3,2012-01-01,",
    "2002,Beta Debt Fund,Beta AMC Limited,Open Ended,Debt Scheme - Liquid Fund,Beta Debt Fund - Regular - Growth,500,1490,2026-06-29,,,INF4,-,INF4,2012-01-01,",
]


@pytest.fixture
def keys():
    priv, pub = generate_keypair()
    a_priv, a_pub = generate_approver_keypair()
    b_priv, b_pub = generate_approver_keypair()
    approvers = ApprovalVerifier({
        "steward": {"roles": ["proposer"], "keys": {"steward-k": a_pub}},
        "compliance": {"roles": ["reviewer"], "keys": {"compliance-k": b_pub}},
    })
    return {"signer": GenerationSigner("pub-k", priv), "verifier": GenerationVerifier({"pub-k": pub}),
            "approvers": approvers, "steward": ApproverSigner("steward", "steward-k", a_priv),
            "compliance": ApproverSigner("compliance", "compliance-k", b_priv)}


@pytest.fixture
def db(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "fin40.sqlite"))

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):              # PostgreSQL enforces FKs; make SQLite do the same here
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _approve(keys, sessions, tenant, version, proposal="P1", revision=1):
    with sessions() as s:
        manifest = s.get(fin.FinDatasetVersion, version).manifest
    subject = fin.activation_subject(tenant=tenant, dataset_version=version, manifest=manifest,
                                     proposal_id=proposal, revision=revision)
    rec = new_record(subject)
    rec = keys["steward"].sign(rec, "proposer")
    return keys["compliance"].sign(rec, "reviewer")


def _stage(sessions, keys, tenant, chunks):
    with sessions.begin() as s:
        return fin.stage_dataset(s, tenant=tenant, chunks_dir=chunks, signer=keys["signer"])


def _activate(sessions, keys, tenant, version, **kw):
    record = _approve(keys, sessions, tenant, version, **kw)
    with sessions.begin() as s:
        return fin.activate_dataset(s, tenant=tenant, dataset_version=version, approval_record=record,
                                    approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])


# ------------------------------------------------------------------------------------------------ staging

def test_stage_real_dataset_reconciles_every_row(db, keys):
    report = _stage(db, keys, "tenant_alpha", CHUNKS)
    assert (report.expected_rows, report.parsed_rows) == (16245, 16245)
    assert report.valid_rows + report.rejected_rows == 16245
    assert report.rejected_rows == 0 and report.aaum_periods[0]["label"] == "January - March 2026"
    with db() as s:
        assert s.scalar(select(func.count()).select_from(fin.FinPlanOption)) == 16245
        assert s.get(fin.FinDatasetVersion, report.dataset_version).status == "STAGED"
        assert s.scalar(select(func.count()).select_from(fin.FinActiveDataset)) == 0     # staging never activates


def test_restaging_identical_content_is_idempotent(db, keys, tmp_path):
    chunks = _mini_chunks(tmp_path, MINI)
    first = _stage(db, keys, "T", chunks)
    second = _stage(db, keys, "T", chunks)
    assert second.already_staged and second.dataset_version == first.dataset_version


def test_changed_content_creates_new_version(db, keys, tmp_path):
    a = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI, "a"))
    b = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI[:3] + [MINI[3].replace("1490", "1491")], "b"))
    assert a.dataset_version != b.dataset_version


@pytest.mark.parametrize("breakage", ["missing_chunk", "row_count", "header", "gap"])
def test_reconciliation_failures_stage_nothing(db, keys, tmp_path, breakage):
    d = _mini_chunks(tmp_path, MINI)
    m = json.loads((d / "manifest.json").read_text())
    if breakage == "missing_chunk":
        (d / "c1.csv").unlink()
    elif breakage == "row_count":
        m["chunks"][0]["rows"] = m["original_rows"] = m["chunks"][0]["end_row"] = 5
    elif breakage == "header":
        (d / "c1.csv").write_text("A,B\n1,2\n2,3\n3,4\n4,5\n")
    elif breakage == "gap":
        m["chunks"][0]["start_row"] = 2
    (d / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(Conflict):
        _stage(db, keys, "T", d)
    with db() as s:
        assert s.scalar(select(func.count()).select_from(fin.FinDatasetVersion)) == 0


def test_invalid_rows_are_rejected_with_reason_not_dropped(db, keys, tmp_path):
    rows = MINI + ["1001,Dup,Alpha AMC Limited,Open Ended,X,Dup - Growth,1,1,2026-06-29,1,January - March 2026,-,-,-,,",
                   "abc,Bad,Alpha AMC Limited,Open Ended,X,Bad - Growth,1,1,2026-06-29,1,January - March 2026,-,-,-,,",
                   "3001,Q,Alpha AMC Limited,Open Ended,X,Q - Growth,1,1,2026-06-29,5,Spring 2026,-,-,-,,"]
    report = _stage(db, keys, "T", _mini_chunks(tmp_path, rows))
    assert report.rejected_rows == 3
    assert report.rejection_reasons == {"BAD_AAUM_PERIOD": 1, "BAD_SCHEME_CODE": 1, "DUPLICATE_SCHEME_CODE": 1}
    assert report.valid_rows + report.rejected_rows == report.parsed_rows == 7


def test_stage_requires_signer(db, tmp_path):
    with pytest.raises(Conflict, match="signing key"):
        with db.begin() as s:
            fin.stage_dataset(s, tenant="T", chunks_dir=_mini_chunks(tmp_path, MINI), signer=None)


def test_exact_decimal_round_trip_and_rounding_is_counted(db, keys, tmp_path):
    report = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI))
    assert report.values_rounded == 1                      # 1500.0000004 -> 1500.000000
    with db() as s:
        nav = s.scalar(select(fin.FinNavObservation.nav_micro).where(fin.FinNavObservation.plan_option_id == "amfi:1001"))
    assert fin.micro_to_decimal(nav) == Decimal("100.123456")


def test_plan_option_rules():
    assert fin.classify_plan_option("X Fund - Direct Plan - Growth") == ("DIRECT", "GROWTH")
    assert fin.classify_plan_option("X Fund -Regular - IDCW") == ("REGULAR", "IDCW")
    assert fin.classify_plan_option("X Fund - Dividend Reinvestment") == ("UNSPECIFIED", "IDCW_REINVEST")
    assert fin.classify_plan_option("X Fund") == ("UNSPECIFIED", "UNSPECIFIED")


def test_aaum_period_parsing():
    assert fin.parse_aaum_period("January - March 2026")[:2] == (date(2026, 1, 1), date(2026, 3, 31))
    assert fin.parse_aaum_period("October - December 2025")[1] == date(2025, 12, 31)
    with pytest.raises(fin.RowRejected):
        fin.parse_aaum_period("Q1 2026")


# ---------------------------------------------------------------------------------------------- activation

def test_activation_requires_valid_two_person_approval(db, keys, tmp_path):
    v = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI)).dataset_version
    one = keys["steward"].sign(new_record(fin.activation_subject(
        tenant="T", dataset_version=v, manifest={"x": 1}, proposal_id="P", revision=1)), "proposer")
    with pytest.raises(ApprovalRefused):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record=one,
                                 approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
    with pytest.raises(Conflict, match="trust store"):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record={}, approval_verifier=None,
                                 generation_verifier=keys["verifier"])
    with db() as s:
        assert s.get(fin.FinActiveDataset, ("T", fin.DOMAIN)) is None


def test_approval_for_another_version_is_refused(db, keys, tmp_path):
    a = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI, "a")).dataset_version
    b = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI[:2], "b")).dataset_version
    record_for_a = _approve(keys, db, "T", a)
    with pytest.raises(ApprovalRefused):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=b, approval_record=record_for_a,
                                 approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])


def test_activation_is_atomic_and_approval_cannot_be_replayed(db, keys, tmp_path):
    v = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI)).dataset_version
    record = _approve(keys, db, "T", v)
    with db.begin() as s:
        receipt = fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record=record,
                                       approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
    with db() as s:
        pin = fin.current_pin(s, "T")
        assert (pin.dataset_version, pin.receipt_id, pin.epoch) == (v, receipt.id, 1)
        assert receipt.proposer == "steward" and receipt.reviewer == "compliance"
        claim = s.execute(select(fin.FinActiveDataset)).scalar_one()
        assert claim.dataset_version == v
    with pytest.raises(Conflict):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record=record,
                                 approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])


def test_failure_inside_activation_leaves_previous_version_serving(db, keys, tmp_path, monkeypatch):
    a = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI, "a")).dataset_version
    _activate(db, keys, "T", a)
    b = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI[:3], "b")).dataset_version
    record = _approve(keys, db, "T", b, proposal="P2")

    def boom(*_a, **_k):
        raise RuntimeError("crash before release")
    monkeypatch.setattr(fin, "_release_scope", boom)
    with pytest.raises(RuntimeError):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=b, approval_record=record,
                                 approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])
    with db() as s:
        assert fin.current_pin(s, "T").dataset_version == a
        assert s.get(fin.FinDatasetVersion, b).status == "STAGED"
        assert s.get(fin.FinDatasetVersion, a).status == "ACTIVE"


def test_rollback_is_reactivation_with_its_own_approval(db, keys, tmp_path):
    a = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI, "a")).dataset_version
    b = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI[:3], "b")).dataset_version
    _activate(db, keys, "T", a, proposal="P1")
    _activate(db, keys, "T", b, proposal="P2")
    with db() as s:
        assert s.get(fin.FinDatasetVersion, a).status == "RETIRED"
    receipt = _activate(db, keys, "T", a, proposal="P3")
    assert receipt.previous_dataset_version == b
    with db() as s:
        pin = fin.current_pin(s, "T")
        assert (pin.dataset_version, pin.epoch) == (a, 3)


@pytest.mark.parametrize("tamper", ["row_value", "manifest", "signature", "revoked_key"])
def test_tampering_blocks_activation(db, keys, tmp_path, tamper):
    v = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI)).dataset_version
    record = _approve(keys, db, "T", v)
    verifier = keys["verifier"]
    with db.begin() as s:
        if tamper == "row_value":
            s.execute(update(fin.FinNavObservation).where(fin.FinNavObservation.plan_option_id == "amfi:1001")
                      .values(nav_micro=999))
        elif tamper == "manifest":
            ds = s.get(fin.FinDatasetVersion, v)
            ds.manifest = {**ds.manifest, "counts": {**ds.manifest["counts"], "rejected": 0, "valid": 99}}
        elif tamper == "signature":
            ds = s.get(fin.FinDatasetVersion, v)
            ds.signature = {**ds.signature, "signature": ds.signature["signature"][::-1]}
    if tamper == "revoked_key":
        verifier = GenerationVerifier({"pub-k": keys["signer"].public_key_b64}, revoked=["pub-k"])
    with pytest.raises((VerificationFailed, ApprovalRefused)):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="T", dataset_version=v, approval_record=record,
                                 approval_verifier=keys["approvers"], generation_verifier=verifier)


def test_dataset_of_one_tenant_cannot_be_activated_for_another(db, keys, tmp_path):
    v = _stage(db, keys, "tenant_alpha", _mini_chunks(tmp_path, MINI)).dataset_version
    record = _approve(keys, db, "tenant_alpha", v)
    with pytest.raises(Conflict):
        with db.begin() as s:
            fin.activate_dataset(s, tenant="tenant_beta", dataset_version=v, approval_record=record,
                                 approval_verifier=keys["approvers"], generation_verifier=keys["verifier"])


# ------------------------------------------------------------------------------------------------- serving

@pytest.fixture
def served(db, keys, tmp_path):
    a = _stage(db, keys, "tenant_alpha", _mini_chunks(tmp_path, MINI, "alpha")).dataset_version
    _activate(db, keys, "tenant_alpha", a)
    beta_rows = [r.replace("Alpha", "Gamma") for r in MINI[:2]]
    b = _stage(db, keys, "tenant_beta", _mini_chunks(tmp_path, beta_rows, "beta")).dataset_version
    _activate(db, keys, "tenant_beta", b)
    return VerifiedStructuredExecutor(db, keys["verifier"]), a


def test_nav_lookup_exact_with_provenance(served):
    ex, version = served
    r = ex.execute("tenant_alpha", FinPlan("NAV_LOOKUP", scheme_code="1001"))
    assert r.rows[0][3] == "100.123456" and r.as_of == {"nav_date": "2026-06-29"}
    assert r.dataset_version == version and r.row_anchor_count == 1 and r.result_set_hash.startswith("sha256:")


def test_top_amc_aaum_is_exact_and_echoes_period_and_exclusions(served):
    ex, _ = served
    r = ex.execute("tenant_alpha", FinPlan("TOP_AMC_AAUM", limit=5))
    # Alpha = 1000.5 + 200.25 = 1200.75; Beta = 1200.75 (its plan without AAUM is excluded and counted).
    # Exact tie -> deterministic tie-break by amc_id ascending.
    assert [row[1] for row in r.rows] == ["Alpha AMC Limited", "Beta AMC Limited"]
    assert [row[2] for row in r.rows] == ["1200.750000", "1200.750000"]
    assert [row[3] for row in r.rows] == ["50.00", "50.00"]
    assert r.as_of["aaum_period"] == "January - March 2026"
    assert r.exclusions["plan_options_without_aaum_for_period"] == 1
    assert ex.execute("tenant_alpha", FinPlan("TOP_AMC_AAUM", limit=5)).result_set_hash == r.result_set_hash


def test_category_share_and_scheme_count(served):
    ex, _ = served
    r = ex.execute("tenant_alpha", FinPlan("CATEGORY_AAUM_SHARE"))
    # Both categories total 1200.75 -> tie broken by category name ascending.
    assert [row[1] for row in r.rows] == ["Debt Scheme - Liquid Fund", "Equity Scheme - Large Cap Fund"]
    assert sum(Decimal(row[3]) for row in r.rows) == Decimal("100.00")
    c = ex.execute("tenant_alpha", FinPlan("COUNT_SCHEMES", amc_text="alpha"))
    assert c.rows == [[1, 2]] and c.filters_applied == {"amc": "Alpha AMC Limited"}


def test_ambiguous_name_returns_candidates_not_a_guess(served):
    ex, _ = served
    with pytest.raises(FinQueryError) as err:
        ex.execute("tenant_alpha", FinPlan("NAV_LOOKUP", scheme_text="alpha equity"))
    assert err.value.code == "AMBIGUOUS_QUERY" and len(err.value.options) == 2


def test_nav_for_a_date_the_dataset_does_not_hold(served):
    ex, _ = served
    with pytest.raises(FinQueryError) as err:
        ex.execute("tenant_alpha", FinPlan("NAV_LOOKUP", scheme_code="1001", nav_date=date(2026, 1, 1)))
    assert err.value.code == "INCOMPATIBLE_PERIODS"


def test_unknown_period_and_unknown_intent(served):
    ex, _ = served
    with pytest.raises(FinQueryError) as err:
        ex.execute("tenant_alpha", FinPlan("TOP_AMC_AAUM", period_start=date(2025, 4, 1)))
    assert err.value.code == "INCOMPATIBLE_PERIODS"
    with pytest.raises(FinQueryError) as err:
        ex.execute("tenant_alpha", FinPlan("XIRR"))
    assert err.value.code == "UNSUPPORTED_METRIC"


def test_tenant_isolation(served):
    ex, _ = served
    with pytest.raises(FinQueryError) as err:
        ex.execute("tenant_beta", FinPlan("NAV_LOOKUP", scheme_code="2001"))     # alpha-only code
    assert err.value.code == "NO_MATCH"
    r = ex.execute("tenant_beta", FinPlan("TOP_AMC_AAUM"))
    assert [row[1] for row in r.rows] == ["Gamma AMC Limited"]
    with pytest.raises(ServingDenied):
        ex.execute("tenant_gamma", FinPlan("DATASET_SUMMARY"))
    with pytest.raises(ServingDenied):
        ex.execute("", FinPlan("DATASET_SUMMARY"))


def test_serving_refuses_tampered_rows_on_first_proof(db, keys, tmp_path):
    v = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI)).dataset_version
    _activate(db, keys, "T", v)
    with db.begin() as s:
        s.execute(update(fin.FinAaumObservation).values(aaum_micro_cr=1))
    with pytest.raises(ServingDenied, match="verification"):
        VerifiedStructuredExecutor(db, keys["verifier"]).execute("T", FinPlan("TOP_AMC_AAUM"))


def test_authority_change_during_request_is_refused(db, keys, tmp_path, monkeypatch):
    a = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI, "a")).dataset_version
    b = _stage(db, keys, "T", _mini_chunks(tmp_path, MINI[:3], "b")).dataset_version
    _activate(db, keys, "T", a)
    ex = VerifiedStructuredExecutor(db, keys["verifier"])
    import amc_publication.structured_serving40 as serving
    real = serving.run_plan

    def run_then_switch(s, pin, plan):
        out = real(s, pin, plan)
        _activate(db, keys, "T", b, proposal="P2")
        return out
    monkeypatch.setattr(serving, "run_plan", run_then_switch)
    with pytest.raises(ServingDenied, match="changed"):
        ex.execute("T", FinPlan("DATASET_SUMMARY"))


def test_no_float_in_the_fin_path():
    root = Path(__file__).resolve().parents[1] / "amc_publication"
    for name in ("fin40.py", "fin_query40.py", "structured_serving40.py"):
        assert "float(" not in (root / name).read_text(encoding="utf-8"), name


def test_real_dataset_top_amcs_matches_independent_decimal_sum(db, keys):
    """Gold computed independently with csv + Decimal, never from the system under test."""
    import csv
    from collections import defaultdict
    v = _stage(db, keys, "tenant_alpha", CHUNKS).dataset_version
    _activate(db, keys, "tenant_alpha", v)
    totals = defaultdict(Decimal)
    for f in sorted(CHUNKS.glob("*.csv")):
        for row in csv.DictReader(f.open(encoding="utf-8-sig")):
            if row["Average_AUM_Cr"].strip() and row["AAUM_Quarter"].strip():
                totals[row["AMC"].strip()] += Decimal(row["Average_AUM_Cr"]).quantize(Decimal("0.000001"))
    gold = sorted(totals.items(), key=lambda kv: (-kv[1], fin.slug(kv[0])))[:5]
    r = VerifiedStructuredExecutor(db, keys["verifier"]).execute("tenant_alpha", FinPlan("TOP_AMC_AAUM", limit=5))
    assert [(row[1], Decimal(row[2])) for row in r.rows] == [(n, t.quantize(Decimal("0.000001"))) for n, t in gold]
