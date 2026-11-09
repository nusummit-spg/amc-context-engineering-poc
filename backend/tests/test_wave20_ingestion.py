"""Existing AMC ingestion path compatibility; fake importer prevents writes."""
import csv
from pathlib import Path
import pytest
from amc_quality.manifest import build_chunk_manifest, attest_existing_chunks, verify_chunk_manifest, ManifestVerificationError
from amc_quality.ingestion_gate import guarded_ingest


def make_legacy(tmp_path, n=23):
    source = tmp_path / "original.csv"
    with source.open("w", newline="", encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["scheme","amount"])
        for i in range(n):w.writerow([str(i), f"{i}.25"])
    base=build_chunk_manifest(source, tmp_path / "built", rows_per_chunk=2)
    base.unlink()
    for i, chunk in enumerate(sorted(base.parent.glob("chunk_*.csv"))):
        chunk.rename(base.parent / f"mutual_fund_data_chunk_{i+1}.csv")
    return source, base.parent


class FakePipeline:
    def __init__(self, report=None, callback=None):
        self.report=report
        self.callback=callback
        self.calls=[]
    def ingest_chunks_directory(self, **kwargs):
        self.calls.append(kwargs)
        if self.callback: self.callback()
        if self.report is None:
            raise RuntimeError("must specify report")
        return self.report


def good_report(n):
    return {"reconciled":True,"activated":False,"processed_rows":n,
            "chunks_count":(n + 1)//2,"quarantined_rows":0}


def test_attest_legacy_12_chunks_and_wrapper(tmp_path):
    src, chunks=make_legacy(tmp_path)
    manifest=attest_existing_chunks(src,chunks)
    assert verify_chunk_manifest(src,manifest)["chunks"] == 12
    fake=FakePipeline(report=good_report(23))
    result=guarded_ingest(fake,source_csv=src,chunks_dir=chunks,manifest_path=manifest,
                          dataset_version="v1",activate=False)
    assert result["verified_ingestion"] and result["activated"] is False
    assert len(fake.calls) == 1 and fake.calls[0]["activate_upon_completion"] is False


def test_attest_legacy_reject_overwrite(tmp_path):
    src,chunks=make_legacy(tmp_path)
    attest_existing_chunks(src,chunks)
    with pytest.raises(FileExistsError): attest_existing_chunks(src,chunks)


def test_attest_legacy_detect_tampered_reordered(tmp_path):
    src,chunks=make_legacy(tmp_path)
    # Swap chunk file content, while each CSV remains syntactically valid
    p=chunks / "mutual_fund_data_chunk_1.csv"
    q=chunks / "mutual_fund_data_chunk_2.csv"
    tmp=chunks / "swap.tmp"
    p.rename(tmp); q.rename(p); tmp.rename(q)
    with pytest.raises(ManifestVerificationError, match="full ordered"):
        attest_existing_chunks(src,chunks)


def test_guarded_ingest_wrong_chunk_count_fails_before_call(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    (chunks / "mutual_fund_data_chunk_10.csv").unlink()
    fake=FakePipeline(report=good_report(23))
    with pytest.raises(ManifestVerificationError):
        guarded_ingest(fake,source_csv=src,chunks_dir=chunks,manifest_path=m,dataset_version="v1")
    assert not fake.calls


def test_guarded_ingest_refuses_default_old_manifest(tmp_path):
    src,chunks=make_legacy(tmp_path)
    fake=FakePipeline(report=good_report(23))
    with pytest.raises(ManifestVerificationError, match="explicit"):
        guarded_ingest(fake,source_csv=src,chunks_dir=chunks,manifest_path=chunks/"manifest.json",dataset_version="v1")
    assert not fake.calls


def test_guarded_ingest_prevents_activation_on_quarantine(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    r=good_report(23);r["quarantined_rows"]=1
    with pytest.raises(ManifestVerificationError, match="quarantine"):
        guarded_ingest(FakePipeline(report=r),source_csv=src,chunks_dir=chunks,
                       manifest_path=m,dataset_version="v1")


def test_guarded_ingest_prevents_activation_on_false_reconciliation(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    r=good_report(23);r["reconciled"]=False
    with pytest.raises(ManifestVerificationError, match="reconciliation"):
        guarded_ingest(FakePipeline(report=r),source_csv=src,chunks_dir=chunks,
                       manifest_path=m,dataset_version="v1")


def test_guarded_ingest_detects_changed_source_during_ingestion(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    def tamper(): src.write_bytes(src.read_bytes()+b"bad")
    fake=FakePipeline(report=good_report(23), callback=tamper)
    with pytest.raises(ManifestVerificationError, match="source bytes"):
        guarded_ingest(fake,source_csv=src,chunks_dir=chunks,manifest_path=m,dataset_version="v1")
    assert len(fake.calls)==1 and fake.calls[0]["activate_upon_completion"] is False


def test_guarded_ingest_cannot_activate_even_if_valid(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    with pytest.raises(ManifestVerificationError, match="automatic activation is disabled"):
        guarded_ingest(FakePipeline(report=good_report(23)),source_csv=src,chunks_dir=chunks,
                       manifest_path=m,dataset_version="v1",activate=True)


def test_guarded_ingest_quarantines_false_activated_report(tmp_path):
    src,chunks=make_legacy(tmp_path)
    m=attest_existing_chunks(src,chunks)
    r=good_report(23);r["activated"]=True
    with pytest.raises(ManifestVerificationError, match="reconciliation"):
        guarded_ingest(FakePipeline(report=r),source_csv=src,chunks_dir=chunks,
                       manifest_path=m,dataset_version="v1")
