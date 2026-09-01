# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""AWS Lambda entrypoint for the parser stage.

Triggered by S3 ObjectCreated on the corpus bucket. For each uploaded file it
runs the stateless ingestion steps (parse -> chunk -> PII scrub) via the shared
`ingestion` package and writes the resulting chunks as JSON under processed/.
EC2 then reads processed/ to embed (FAISS) + extract entities + write the graph.
"""
import dataclasses
import json
import os
import urllib.parse

import boto3

from ingestion.pipeline import run_ingestion

s3 = boto3.client("s3")

PROCESSED_PREFIX = os.environ.get("PROCESSED_PREFIX", "processed/")


def lambda_handler(event, context):
    results = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])

        # Skip our own outputs to avoid a trigger loop.
        if key.startswith(PROCESSED_PREFIX):
            continue

        tmp = f"/tmp/{os.path.basename(key)}"
        s3.download_file(bucket, key, tmp)

        out = run_ingestion([tmp])
        payload = {
            "source_key": key,
            "unstructured_chunks": [dataclasses.asdict(c) for c in out["unstructured_chunks"]],
            "structured_chunks": [dataclasses.asdict(c) for c in out["structured_chunks"]],
        }

        out_key = f"{PROCESSED_PREFIX}{key}.json"
        s3.put_object(
            Bucket=bucket,
            Key=out_key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json",
        )
        n = len(payload["unstructured_chunks"]) + len(payload["structured_chunks"])
        print(f"[lambda] {key} -> {out_key} ({n} chunks)")
        results.append({"source": key, "processed": out_key, "chunks": n})

    return {"processed": results}
