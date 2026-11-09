"""Standalone quality tests: no actual production data or services required."""
import csv
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import pytest

from amc_quality.manifest import build_chunk_manifest, verify_chunk_manifest, ManifestVerificationError
from amc_quality.provenance import write_ledger, verify_ledger, ProvenanceError
from amc_quality.financial import (FinancialQualityReadModel, FinancialPolicyBlocked,
                                   FinancialAmbiguityError, FinancialIntegrityError)
from amc_quality.cli import main


def ident(i):
    return sha256(f"row:{i}".encode()).hexdigest()


def csv_source(tmp_path, lines=5, bom=False, unicode=False):
    src = tmp_path / "source.csv"
    with src.open("w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scheme", "name", "note"])
        for i in range(lines):
            w.writerow([f"scheme{i}", "नमस्ते" if unicode else f"name{i}", "line1\nline2" if i == 1 else str(i)])
    return src


@pytest.fixture
def manifest_env(tmp_path):
    src = csv_source(tmp_path, lines=5)
    manifest = build_chunk_manifest(src, tmp_path / "chunks", rows_per_chunk=2)
    return src, manifest


def test_manifest_valid(manifest_env):
    src, m = manifest_env
    out = verify_chunk_manifest(src, m)
    assert (out["rows"], out["chunks"], out["verified"]) == (5, 3, True)


def test_manifest_does_not_mutate_source(manifest_env):
    src, m = manifest_env
    before = src.read_bytes()
    verify_chunk_manifest(src, m)
    assert src.read_bytes() == before


def test_manifest_source_tamper(manifest_env):
    src, m = manifest_env
    src.write_bytes(src.read_bytes() + b"bad")
    with pytest.raises(ManifestVerificationError, match="source bytes"):
        verify_chunk_manifest(src, m)


def test_manifest_chunk_tamper(manifest_env):
    src, m = manifest_env
    c = m.parent / "chunk_000000.csv"
    c.write_bytes(c.read_bytes() + b"bad")
    with pytest.raises(ManifestVerificationError, match="chunk bytes"):
        verify_chunk_manifest(src, m)


def test_manifest_reordered_chunk_without_hash_mismatch(manifest_env):
    src, m = manifest_env
    data = json.loads(m.read_text())
    data["chunks"][0], data["chunks"][1] = data["chunks"][1], data["chunks"][0]
    data["chunks"][0]["sequence"], data["chunks"][1]["sequence"] = 0, 1
    m.write_text(json.dumps(data))
    with pytest.raises(ManifestVerificationError, match="logical CSV"):
        verify_chunk_manifest(src, m)


def test_manifest_missing_chunk(manifest_env):
    src, m = manifest_env
    (m.parent / "chunk_000001.csv").unlink()
    with pytest.raises(ManifestVerificationError, match="missing chunk"):
        verify_chunk_manifest(src, m)


def test_manifest_path_traversal(manifest_env):
    src, m = manifest_env
    data = json.loads(m.read_text())
    data["chunks"][0]["file"] = "../source.csv"
    m.write_text(json.dumps(data))
    with pytest.raises(ManifestVerificationError, match="filename"):
        verify_chunk_manifest(src, m)


def test_manifest_row_count_fraud(manifest_env):
    src, m = manifest_env
    data = json.loads(m.read_text())
    data["chunks"][0]["rows"] += 1
    m.write_text(json.dumps(data))
    with pytest.raises(ManifestVerificationError, match="row count"):
        verify_chunk_manifest(src, m)


def test_manifest_declared_hash_not_sufficient(manifest_env):
    src, m = manifest_env
    data = json.loads(m.read_text())
    data["source_sha256"] = "0" * 64
    m.write_text(json.dumps(data))
    with pytest.raises(ManifestVerificationError, match="source bytes"):
        verify_chunk_manifest(src, m)


def test_manifest_missing_source(manifest_env):
    src, m = manifest_env
    src.unlink()
    with pytest.raises(ManifestVerificationError, match="source file unavailable"):
        verify_chunk_manifest(src, m)


def test_manifest_duplicate_header(tmp_path):
    s = tmp_path / "x.csv"
    s.write_text("a,a\n1,2\n")
    with pytest.raises(ManifestVerificationError, match="header"):
        build_chunk_manifest(s, tmp_path / "parts")


def test_manifest_bad_row_columns(tmp_path):
    s = tmp_path / "x.csv"
    s.write_text("a,b\n1,2,3\n")
    with pytest.raises(ManifestVerificationError, match="column count"):
        build_chunk_manifest(s, tmp_path / "parts")


def test_manifest_reject_overwrite(manifest_env):
    src, m = manifest_env
    with pytest.raises(FileExistsError):
        build_chunk_manifest(src, m.parent)


def test_manifest_multiline_bom_unicode(tmp_path):
    src = csv_source(tmp_path, bom=True, unicode=True)
    m = build_chunk_manifest(src, tmp_path / "parts", rows_per_chunk=1)
    assert verify_chunk_manifest(src, m)["rows"] == 5


def test_manifest_zero_rows(tmp_path):
    src = csv_source(tmp_path, lines=0)
    m = build_chunk_manifest(src, tmp_path / "parts")
    assert verify_chunk_manifest(src, m)["rows"] == 0


def test_manifest_bad_manifest_count(manifest_env):
    s, m = manifest_env
    d = json.loads(m.read_text()); d["chunk_count"] = 4
    m.write_text(json.dumps(d))
    with pytest.raises(ManifestVerificationError, match="chunk count"):
        verify_chunk_manifest(s, m)


def test_manifest_no_symlinks(manifest_env):
    s, m = manifest_env
    c = m.parent / "chunk_000000.csv"
    backup = m.parent / "backup.csv"
    c.rename(backup)
    try:
        c.symlink_to(backup)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not available in this test OS")
    with pytest.raises(ManifestVerificationError, match="symlink"):
        verify_chunk_manifest(s, m)


def test_manifest_missing_columns(manifest_env):
    s, m = manifest_env
    d=json.loads(m.read_text()); d["columns"]=None; m.write_text(json.dumps(d))
    with pytest.raises(ManifestVerificationError, match="missing chunks/columns"):
        verify_chunk_manifest(s, m)


def test_ledger_80_contributors(tmp_path):
    ids = [ident(i) for i in range(80)]
    p = tmp_path / "ledger.jsonl"
    rec = write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=ids)
    assert rec.contributors == 80
    assert verify_ledger(p, expected_sha256=rec.digest_sha256).contributors == 80
    assert len(p.read_text().splitlines()) == 82


def test_ledger_tamper(tmp_path):
    p = tmp_path / "ledger.jsonl"
    rec = write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[ident(1)])
    p.write_text(p.read_text().replace(ident(1), ident(2)))
    with pytest.raises(ProvenanceError, match="digest differs"):
        verify_ledger(p, expected_sha256=rec.digest_sha256)


def test_ledger_missing_footer(tmp_path):
    p = tmp_path / "ledger.jsonl"
    rec = write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[ident(1)])
    p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ProvenanceError, match="incomplete"):
        verify_ledger(p, expected_sha256=rec.digest_sha256)


def test_ledger_does_not_overwrite(tmp_path):
    p = tmp_path / "ledger.jsonl"
    write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[])
    with pytest.raises(FileExistsError):
        write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[])


def test_ledger_invalid_id(tmp_path):
    with pytest.raises(ProvenanceError, match="SHA-256"):
        write_ledger(tmp_path / "x.jsonl", dataset_version="v1", query_id="q1", source_row_ids=["bad"])
    assert not (tmp_path / "x.jsonl").exists()


def test_ledger_wrong_version(tmp_path):
    p = tmp_path / "x.jsonl"
    rec = write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[ident(1)])
    with pytest.raises(ProvenanceError, match="version mismatch"):
        verify_ledger(p, expected_sha256=rec.digest_sha256, expected_dataset_version="v2")


def test_ledger_wrong_query(tmp_path):
    p = tmp_path / "x.jsonl"
    rec = write_ledger(p, dataset_version="v1", query_id="q1", source_row_ids=[ident(1)])
    with pytest.raises(ProvenanceError, match="identity mismatch"):
        verify_ledger(p, expected_sha256=rec.digest_sha256, expected_query_id="q2")


def test_ledger_invalid_external_anchor(tmp_path):
    with pytest.raises(ProvenanceError, match="externally anchored"):
        verify_ledger(tmp_path / "x", expected_sha256="bad")


@pytest.fixture
def financial_db(tmp_path):
    db = tmp_path / "typed.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
        CREATE TABLE dataset_versions (dataset_version TEXT PRIMARY KEY,status TEXT NOT NULL);
        CREATE TABLE active_version (id INTEGER PRIMARY KEY,dataset_version TEXT);
        CREATE TABLE source_rows (source_row_id TEXT PRIMARY KEY,dataset_version TEXT,
        validation_status TEXT,scheme_code TEXT,amc_id TEXT,amc_display_name TEXT,
        scheme_id TEXT,plan_option_id TEXT,nav_per_unit TEXT,nav_date TEXT);
        CREATE TABLE nav_observations (observation_id TEXT PRIMARY KEY,source_row_id TEXT,
        dataset_version TEXT,scheme_code TEXT,plan_option_id TEXT,nav_per_unit TEXT,nav_date TEXT);
        INSERT INTO dataset_versions VALUES ('v1','ACTIVE');
        INSERT INTO dataset_versions VALUES ('v2','STAGED');
        INSERT INTO active_version VALUES (1,'v1');
        """)
        for i in range(80):
            amc = "amc_a" if i < 70 else "amc_b"
            row = (ident(i), "v1", "VALID" if i != 79 else "QUARANTINED", "100033",
                   amc, "AMC A" if amc == "amc_a" else "AMC B",
                   f"scheme_{i//2}", f"plan_{i}", "922.67", "2026-06-29")
            c.execute("INSERT INTO source_rows VALUES (?,?,?,?,?,?,?,?,?,?)", row)
        c.execute("INSERT INTO nav_observations VALUES (?,?,?,?,?,?,?)", ("ob_0", ident(0), "v1", "100033", "plan_0", "922.670", "2026-06-29"))
    return db


def model(db):
    return FinancialQualityReadModel(db)


def test_count_full_ledger(financial_db, tmp_path):
    ans = model(financial_db).count_valid_rows(ledger_path=tmp_path / "p.jsonl")
    assert ans.rows == [{"valid_rows": 79}]
    assert ans.contributor_count == 79
    assert verify_ledger(ans.ledger_path, expected_sha256=ans.contributors_sha256).contributors == 79


def test_count_deterministic(financial_db, tmp_path):
    a = model(financial_db).count_valid_rows(ledger_path=tmp_path / "a")
    b = model(financial_db).count_valid_rows(ledger_path=tmp_path / "b")
    assert a.result_sha256 == b.result_sha256
    assert a.contributors_sha256 == b.contributors_sha256


def test_nav_exact_pairing(financial_db, tmp_path):
    ans=model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",ledger_path=tmp_path / "x")
    assert ans.rows[0]["nav_per_unit"] == "922.670"
    assert ans.contributor_count == 1
    assert ans.rows[0]["source_row_id"] == ident(0)


def test_nav_ambiguous(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("INSERT INTO nav_observations VALUES (?,?,?,?,?,?,?)", ("ob_1", ident(1), "v1", "100033", "plan_1", "922.67", "2026-06-29"))
    with pytest.raises(FinancialAmbiguityError, match="AMBIGUOUS_NAV"):
        model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",ledger_path=tmp_path / "x")


def test_nav_explicit_plan_resolves_ambiguous(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("INSERT INTO nav_observations VALUES (?,?,?,?,?,?,?)", ("ob_1", ident(1), "v1", "100033", "plan_1", "922.67", "2026-06-29"))
    ans=model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",plan_option_id="plan_1",ledger_path=tmp_path / "x")
    assert ans.rows[0]["plan_option_id"] == "plan_1"


def test_nav_duplicate_same_plan_blocked(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("INSERT INTO nav_observations VALUES (?,?,?,?,?,?,?)", ("ob_dup", ident(0), "v1", "100033", "plan_0", "922.67", "2026-06-29"))
    with pytest.raises(FinancialAmbiguityError):
        model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",plan_option_id="plan_0",ledger_path=tmp_path / "x")


def test_nav_mismatch_blocked(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("UPDATE nav_observations SET nav_per_unit='999' WHERE observation_id='ob_0'")
    with pytest.raises(FinancialIntegrityError, match="source NAV differs"):
        model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",ledger_path=tmp_path / "x")


def test_nav_wrong_source_plan_blocked(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("UPDATE nav_observations SET plan_option_id='wrong' WHERE observation_id='ob_0'")
    with pytest.raises(FinancialIntegrityError, match="SOURCE_PAIRING_FAILED"):
        model(financial_db).exact_nav(scheme_code="100033",nav_date="2026-06-29",ledger_path=tmp_path / "x")


def test_nav_missing_blocked(financial_db, tmp_path):
    with pytest.raises(FinancialIntegrityError, match="NO_MATCH"):
        model(financial_db).exact_nav(scheme_code="1",nav_date="2026-06-29",ledger_path=tmp_path / "x")


def test_nav_bad_date(financial_db, tmp_path):
    with pytest.raises(ValueError, match="ISO"):
        model(financial_db).exact_nav(scheme_code="1",nav_date="yesterday",ledger_path=tmp_path / "x")


def test_reject_staged_version(financial_db, tmp_path):
    with pytest.raises(FinancialIntegrityError, match="DATASET_NOT_ACTIVE"):
        model(financial_db).count_valid_rows(ledger_path=tmp_path / "x",dataset_version="v2")


def test_reject_unactive_dataset_status(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("UPDATE dataset_versions SET status='RECONCILED' WHERE dataset_version='v1'")
    with pytest.raises(FinancialIntegrityError, match="DATASET_NOT_ACTIVE"):
        model(financial_db).count_valid_rows(ledger_path=tmp_path / "x")


def test_no_active_version(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("DELETE FROM active_version")
    with pytest.raises(FinancialIntegrityError, match="NO_ACTIVE_VERSION"):
        model(financial_db).count_valid_rows(ledger_path=tmp_path / "x")


def test_top_amc_scheme_count_not_aaum(financial_db, tmp_path):
    ans=model(financial_db).top_amcs_by_scheme_count(ledger_path=tmp_path / "x",limit=2)
    assert ans.metric_id == "distinct_scheme_count"
    assert ans.rows[0]["amc_id"] == "amc_a"
    assert ans.rows[0]["distinct_scheme_count"] == 35
    assert ans.contributor_count == 79
    assert all("aaum" not in str(k).lower() for row in ans.rows for k in row)


def test_top_amc_limit_excludes_other_contributors(financial_db, tmp_path):
    ans=model(financial_db).top_amcs_by_scheme_count(ledger_path=tmp_path / "x",limit=1)
    assert ans.contributor_count == 70


def test_top_amc_alias_collision(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("UPDATE source_rows SET amc_display_name='Another Name' WHERE source_row_id=?", (ident(0),))
    with pytest.raises(FinancialAmbiguityError, match="ALIAS_CONFLICT"):
        model(financial_db).top_amcs_by_scheme_count(ledger_path=tmp_path / "x")


def test_top_amc_missing_canonical_identity(financial_db, tmp_path):
    with sqlite3.connect(financial_db) as c:
        c.execute("UPDATE source_rows SET scheme_id=NULL WHERE source_row_id=?", (ident(0),))
    with pytest.raises(FinancialIntegrityError, match="UNCANONICAL_IDENTITY"):
        model(financial_db).top_amcs_by_scheme_count(ledger_path=tmp_path / "x")


def test_top_amc_bad_limit(financial_db, tmp_path):
    with pytest.raises(ValueError, match="limit"):
        model(financial_db).top_amcs_by_scheme_count(ledger_path=tmp_path / "x",limit=-1)


def test_aaum_unapproved_even_with_forged_kwarg():
    with pytest.raises(FinancialPolicyBlocked, match="METRIC_POLICY_BLOCKED"):
        FinancialQualityReadModel.aggregate_aaum(steward_approved=True, approval_receipt="fake")


def test_no_file_financial():
    with pytest.raises(FileNotFoundError):
        FinancialQualityReadModel("/never/existed/typed.db")


def test_cli_manifest_roundtrip(tmp_path, capsys):
    s = csv_source(tmp_path)
    out = tmp_path / "chunked"
    assert main(["manifest-build", str(s), str(out), "--rows-per-chunk", "2"]) == 0
    assert main(["manifest-check", str(s), str(out / "manifest.amc-v2.json")]) == 0
    assert (out / "manifest.amc-v2.json").exists()


def test_cli_error_code(tmp_path, capsys):
    assert main(["manifest-check", str(tmp_path / "absent.csv"), str(tmp_path / "absent.json")]) == 2
    assert '"ok": false' in capsys.readouterr().err


def test_manifest_external_anchor_success(manifest_env):
    src, manifest = manifest_env
    digest = sha256(manifest.read_bytes()).hexdigest()
    assert verify_chunk_manifest(src, manifest, expected_manifest_sha256=digest)["manifest_sha256"] == digest


def test_manifest_external_anchor_mismatch(manifest_env):
    src, manifest = manifest_env
    with pytest.raises(ManifestVerificationError, match="external audit anchor"):
        verify_chunk_manifest(src, manifest, expected_manifest_sha256="0"*64)
