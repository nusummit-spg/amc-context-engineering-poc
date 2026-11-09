"""CSV manifest producer and independently verified ingest gate (read-only verifier).

Claims checked: actual source bytes, each chunk's actual bytes, exact CSV header,
per-chunk and total row counts, ordered row-by-row equality against source.
A hash's *shape* is never used as proof of a matching file.
"""
from __future__ import annotations
from contextlib import contextmanager
import csv
from hashlib import sha256
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
from typing import Iterator
from uuid import uuid4


class ManifestVerificationError(ValueError):
    pass


def _digest(path: Path) -> tuple[str, int]:
    h = sha256()
    size = 0
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


@contextmanager
def _csv_rows(path: Path) -> Iterator[tuple[list[str], Iterator[list[str]]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                raise ManifestVerificationError(f"CSV is empty: {path.name}")
            if not header or any(not col.strip() for col in header) or len(set(header)) != len(header):
                raise ManifestVerificationError(f"invalid/duplicate CSV header: {path.name}")
            yield header, _validated(reader, len(header), path.name)
    except (UnicodeDecodeError, csv.Error) as ex:
        raise ManifestVerificationError(f"CSV cannot be parsed: {path.name}") from ex


def _validated(reader, n: int, name: str):
    for i, row in enumerate(reader, 2):
        if len(row) != n:
            raise ManifestVerificationError(f"invalid column count in {name}, row {i}")
        yield row


def _safe_chunk(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not (re.fullmatch(r"chunk_[0-9]{6}\.csv", name) or
                                         re.fullmatch(r"mutual_fund_data_chunk_[0-9]{1,6}\.csv", name)):

        raise ManifestVerificationError("invalid chunk filename; no absolute/traversal paths allowed")
    p = root / name
    if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
        raise ManifestVerificationError("chunk symlink/path escapes trusted directory")
    return p


def _write_atomic_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, sort_keys=True, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def build_chunk_manifest(source_csv: str | Path, destination: str | Path,
                         *, rows_per_chunk: int = 1000) -> Path:
    """Make deterministic CSV chunks and a manifest; refuses existing outputs.

    Output is a new directory so an accidental invocation cannot mutate existing
    ingestion data. A manifest is *not* a steward approval or an activation permit.
    """
    src = Path(source_csv).resolve(strict=True)
    dst = Path(destination)
    if not src.is_file() or src.suffix.lower() != ".csv":
        raise ManifestVerificationError("source must be a CSV file")
    if isinstance(rows_per_chunk, bool) or not isinstance(rows_per_chunk, int) or rows_per_chunk <= 0:
        raise ValueError("rows_per_chunk must be a positive integer")
    if dst.exists():
        raise FileExistsError("destination already exists; refusing overwrite")
    if dst.resolve().is_relative_to(src.parent) and dst.resolve() == src:
        raise ValueError("destination must not be source")
    dst.mkdir(parents=True)
    generated = []
    count = 0
    active_handle = None
    writer = None
    current_name = None
    current_rows = 0
    try:
        with _csv_rows(src) as (header, rows):
            for row in rows:
                if writer is None or current_rows >= rows_per_chunk:
                    if active_handle is not None:
                        active_handle.flush()
                        os.fsync(active_handle.fileno())
                        active_handle.close()
                        chunk = dst / current_name
                        digest, size = _digest(chunk)
                        generated.append({"sequence": len(generated), "file": current_name,
                                          "sha256": digest, "bytes": size, "rows": current_rows})
                    current_name = f"chunk_{len(generated):06d}.csv"
                    active_handle = (dst / current_name).open("w", encoding="utf-8", newline="")
                    writer = csv.writer(active_handle, lineterminator="\n")
                    writer.writerow(header)
                    current_rows = 0
                writer.writerow(row)
                current_rows += 1
                count += 1
        if active_handle is not None:
            active_handle.flush()
            os.fsync(active_handle.fileno())
            active_handle.close()
            chunk = dst / current_name
            digest, size = _digest(chunk)
            generated.append({"sequence": len(generated), "file": current_name,
                              "sha256": digest, "bytes": size, "rows": current_rows})
        src_hash, src_size = _digest(src)
        payload = {"schema": "amc.csv-manifest.v2", "source_sha256": src_hash,
                   "source_bytes": src_size, "columns": header, "total_rows": count,
                   "chunk_count": len(generated), "num_chunks": len(generated), "chunks": generated}
        manifest = dst / "manifest.amc-v2.json"
        _write_atomic_json(manifest, payload)
        return manifest
    except Exception:
        if active_handle is not None and not active_handle.closed:
            active_handle.close()
        for p in dst.glob("chunk_*.csv"):
            p.unlink(missing_ok=True)
        (dst / "manifest.amc-v2.json").unlink(missing_ok=True)
        try:
            dst.rmdir()
        except OSError:
            pass
        raise


def _check_sha(d: object) -> bool:
    return isinstance(d, str) and bool(re.fullmatch(r"[0-9a-f]{64}", d))


def verify_chunk_manifest(source_csv: str | Path, manifest_path: str | Path,
                          *, expected_manifest_sha256: str | None = None) -> dict:
    """Fail closed if any byte, declared count, header or logical row differs.

    No activation occurs. Intended to be called BEFORE staging and ingestion.
    Source and chunk files MUST still exist, even when their digest syntax is valid.
    """
    source, manifest_file = Path(source_csv), Path(manifest_path)
    try:
        manifest_digest, _ = _digest(manifest_file)
    except OSError as exc:
        raise ManifestVerificationError("manifest unavailable") from exc
    if expected_manifest_sha256 is not None and manifest_digest != expected_manifest_sha256:
        raise ManifestVerificationError("manifest SHA-256 differs from external audit anchor")
    try:
        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestVerificationError("manifest unreadable or invalid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != "amc.csv-manifest.v2":
        raise ManifestVerificationError("unknown manifest schema")
    chunks = raw.get("chunks")
    if not isinstance(chunks, list) or not isinstance(raw.get("columns"), list):
        raise ManifestVerificationError("missing chunks/columns")
    if any(isinstance(raw.get(k), bool) or not isinstance(raw.get(k), int) or raw[k] < 0
           for k in ("source_bytes", "total_rows", "chunk_count")):
        raise ManifestVerificationError("invalid source count/bytes")
    if raw["chunk_count"] != len(chunks) or raw.get("num_chunks") != len(chunks) or not _check_sha(raw.get("source_sha256")):
        raise ManifestVerificationError("chunk count or source digest is invalid")
    try:
        actual_sha, actual_bytes = _digest(source)
    except OSError as exc:
        raise ManifestVerificationError("source file unavailable") from exc
    if (actual_sha, actual_bytes) != (raw["source_sha256"], raw["source_bytes"]):
        raise ManifestVerificationError("actual source bytes/hash differ from manifest")
    root = manifest_file.parent.resolve()
    seen = set()
    chunk_total = 0
    with _csv_rows(source) as (source_header, source_rows):
        if source_header != raw["columns"]:
            raise ManifestVerificationError("source header mismatch")
        sentinel = object()
        for i, ent in enumerate(chunks):
            if not isinstance(ent, dict) or ent.get("sequence") != i:
                raise ManifestVerificationError("chunk sequence mismatch")
            name = ent.get("file")
            if name in seen:
                raise ManifestVerificationError("duplicate chunk")
            seen.add(name)
            file = _safe_chunk(root, name)
            if not file.is_file():
                raise ManifestVerificationError("missing chunk")
            sha, size = _digest(file)
            if not _check_sha(ent.get("sha256")) or (sha, size) != (ent["sha256"], ent.get("bytes")):
                raise ManifestVerificationError(f"chunk bytes/hash mismatch: {name}")
            if isinstance(ent.get("rows"), bool) or not isinstance(ent.get("rows"), int) or ent["rows"] <= 0:
                raise ManifestVerificationError("invalid chunk row count")
            with _csv_rows(file) as (header, rows):
                if header != source_header:
                    raise ManifestVerificationError("chunk header mismatch")
                n = 0
                for row in rows:
                    expected = next(source_rows, sentinel)
                    if expected is sentinel or expected != row:
                        raise ManifestVerificationError(f"logical CSV rows diverge: {name}:{n+1}")
                    n += 1
                if n != ent["rows"]:
                    raise ManifestVerificationError(f"chunk row count mismatch: {name}")
                chunk_total += n
        if next(source_rows, sentinel) is not sentinel:
            raise ManifestVerificationError("not all source rows are covered")
    if chunk_total != raw["total_rows"]:
        raise ManifestVerificationError("total row count mismatch")
    return {"verified": True, "manifest_sha256": manifest_digest, "source_sha256": actual_sha, "source_bytes": actual_bytes,
            "rows": chunk_total, "chunks": len(chunks), "schema": raw["schema"]}


def attest_existing_chunks(source_csv: str | Path, chunks_dir: str | Path) -> Path:
    """Attest existing AMC `mutual_fund_data_chunk_N.csv` files in-place.

    Does not rewrite chunk bytes. Refuses to sign if order, source bytes, row
    count, header or logical rows differ. Does NOT activate an ingested version.
    """
    source = Path(source_csv).resolve(strict=True)
    directory = Path(chunks_dir).resolve(strict=True)
    manifest = directory / "manifest.amc-v2.json"
    if manifest.exists():
        raise FileExistsError("manifest exists; refuse to overwrite previously audited evidence")
    paths = list(directory.glob("mutual_fund_data_chunk_*.csv"))
    if not paths:
        raise ManifestVerificationError("no existing AMC chunk files to attest")
    if any(not re.fullmatch(r"mutual_fund_data_chunk_[0-9]{1,6}\.csv", p.name) for p in paths):
        raise ManifestVerificationError("unexpected/unsafe legacy chunk name")
    paths.sort(key=lambda p: int(p.stem.rsplit("_", 1)[-1]))
    indices = [int(p.stem.rsplit("_", 1)[-1]) for p in paths]
    if len(set(indices)) != len(indices) or indices != list(range(indices[0], indices[0] + len(indices))):
        raise ManifestVerificationError("legacy chunks are not a contiguous numeric sequence")
    if any(p.is_symlink() for p in paths):
        raise ManifestVerificationError("symlink chunk refused")
    digest, size = _digest(source)
    payload = {"schema": "amc.csv-manifest.v2", "source_sha256": digest,
               "source_bytes": size, "total_rows": 0, "columns": [],
               "chunks": [], "chunk_count": len(paths), "num_chunks": len(paths)}
    with _csv_rows(source) as (header, src_rows):
        payload["columns"] = header
        sentinel = object()
        for seq, p in enumerate(paths):
            hash_, nbytes = _digest(p)
            count = 0
            with _csv_rows(p) as (chunk_header, rows):
                if header != chunk_header:
                    raise ManifestVerificationError("legacy chunk header does not match source")
                for row in rows:
                    expected = next(src_rows, sentinel)
                    if expected is sentinel or expected != row:
                        raise ManifestVerificationError("legacy chunks are not a full ordered copy of source")
                    count += 1
            if not count:
                raise ManifestVerificationError("empty legacy chunk not accepted")
            payload["chunks"].append({"sequence": seq, "file": p.name,
                                      "sha256": hash_, "bytes": nbytes, "rows": count})
            payload["total_rows"] += count
        if next(src_rows, sentinel) is not sentinel:
            raise ManifestVerificationError("legacy chunks do not cover all source rows")
    _write_atomic_json(manifest, payload)
    try:
        verify_chunk_manifest(source, manifest)
    except Exception:
        manifest.unlink(missing_ok=True)
        raise
    return manifest
