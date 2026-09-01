# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Sync new source documents from S3 into DATA_DIR, then run the indexer.

Usage (inside the api container, from /app):
    python -m app.engine.reindex_from_s3 [--rebuild]

Idempotent on both ends:
  - S3 download skips files whose local size already matches (cheap re-run).
  - build_index.build() skips sources already present in the FAISS pickle
    (see build_index.py's `already_done_sources`), so only genuinely new
    documents get parsed/embedded/graph-extracted (LLM cost is incurred only
    for new files).

Requires CORPUS_BUCKET set and the instance IAM role to have s3:GetObject /
s3:ListBucket on that bucket (see deploy/deploy.sh's s3-corpus-read policy).
"""
from __future__ import annotations

import argparse

import boto3

from app.engine import build_index, config


def sync_corpus() -> int:
    if not config.CORPUS_BUCKET:
        print("[reindex] CORPUS_BUCKET not set — skipping S3 sync.", flush=True)
        return 0

    s3 = boto3.client("s3")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.CORPUS_BUCKET):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            suffix = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
            if suffix not in config.SUPPORTED_EXTS:
                continue

            dest = config.DATA_DIR / key.split("/")[-1]
            if dest.exists() and dest.stat().st_size == obj["Size"]:
                continue  # already synced, unchanged

            print(f"[reindex] downloading s3://{config.CORPUS_BUCKET}/{key} -> {dest}", flush=True)
            s3.download_file(config.CORPUS_BUCKET, key, str(dest))
            downloaded += 1

    print(f"[reindex] sync complete — {downloaded} file(s) downloaded.", flush=True)
    return downloaded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="ignore cache, rebuild everything")
    ap.add_argument("--no-sync", action="store_true", help="skip the S3 sync step")
    args = ap.parse_args()

    if not args.no_sync:
        sync_corpus()

    build_index.build(rebuild=args.rebuild, use_gemini=True)


if __name__ == "__main__":
    main()
