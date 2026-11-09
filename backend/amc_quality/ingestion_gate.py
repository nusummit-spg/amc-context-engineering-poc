"""Adapter for existing app.tabular.csv_excel_loader.IngestionPipeline.

Read source, attest chunks, execute *without activation*, reattest source
post-ingestion, then optionally activate. This wrapper is not transactional
across filesystem + SQLite: call with immutable source and locked directory in
production; refuse if a writer can change files during the ingestion window.
"""
from pathlib import Path
from .manifest import verify_chunk_manifest, ManifestVerificationError


def guarded_ingest(pipeline, *, source_csv, chunks_dir, manifest_path,
                   dataset_version, activate: bool = False) -> dict:
    """Fail closed for unverified source or legacy chunk-count mismatch.

    Requires a genuine manifest.amc-v2.json, including independent original
    source SHA and exact row comparison. Never silently uses 16245/22 defaults.
    """
    src = Path(source_csv)
    chunk_dir = Path(chunks_dir)
    manifest = Path(manifest_path)
    if manifest.name != "manifest.amc-v2.json":
        raise ManifestVerificationError("Wave 2.0 verified manifest must be explicit")
    before = verify_chunk_manifest(src, manifest)
    if not dataset_version or not isinstance(dataset_version, str):
        raise ValueError("explicit dataset version required")
    expected_legacy_names = [p.name for p in sorted(chunk_dir.glob("mutual_fund_data_chunk_*.csv"),
                                  key=lambda p: int(p.stem.rsplit("_", 1)[-1]))]
    import json
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    names = [c["file"] for c in declared["chunks"]]
    if names != expected_legacy_names:
        raise ManifestVerificationError("manifest files must match exact legacy ingestion glob/order")
    # Existing ingestion code may persist records before the post-check. It must
    # never activate an unverified dataset; deactivation/recovery still requires
    # the application owner's transactional ingestion design.
    report = pipeline.ingest_chunks_directory(chunks_dir=chunk_dir, manifest_path=manifest,
                                              dataset_version=dataset_version,
                                              activate_upon_completion=False)
    after = verify_chunk_manifest(src, manifest)
    if before != after:
        raise ManifestVerificationError("source/chunks changed while ingesting; refuse activation")
    if (report.get("activated") is not False or report.get("reconciled") is not True or
            report.get("processed_rows") != before["rows"] or report.get("chunks_count") != before["chunks"] or
            report.get("quarantined_rows") != 0):
        raise ManifestVerificationError("ingestion reconciliation or quarantine failure; refuse activation")
    if activate:
        # Production must additionally require durable steward review and
        # authorized activation; this is for a disposable local POC only.
        raise ManifestVerificationError("automatic activation is disabled in Wave 2.0; request explicit reviewed activation")
    return {"verified_ingestion": True, "dataset_version": dataset_version,
            "manifest": after, "ingestion": report, "activated": False}
