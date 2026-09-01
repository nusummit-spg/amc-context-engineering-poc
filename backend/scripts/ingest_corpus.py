# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Batch-ingest the demo corpus directory through the full pipeline.

Run:  python -m scripts.ingest_corpus [corpus_dir]   (from backend/)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import init_container  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> None:
    corpus_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_settings().corpus_dir)
    if not corpus_dir.exists():
        raise SystemExit(f"Corpus directory not found: {corpus_dir}")

    container = init_container()
    container.vector.ensure_collection()

    supported = set(container.pipeline._registry.supported_extensions())
    paths = sorted(
        p for p in corpus_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported
    )
    print(f"Found {len(paths)} document(s) in {corpus_dir}")

    ok, failed = 0, 0
    for path in paths:
        try:
            await container.pipeline.ingest_file(path)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"  FAILED {path.name}: {exc}")
    print(f"Done: {ok} ingested, {failed} failed.")
    await container.graph.close()


if __name__ == "__main__":
    asyncio.run(main())
