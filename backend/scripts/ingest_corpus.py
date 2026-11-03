# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Batch-ingest the demo corpus directory through the full pipeline.
Configured by default to use the local Ollama small model (qwen2.5:3b).

Run:  python -m scripts.ingest_corpus [corpus_dir] [--model qwen2.5:3b]   (from backend/)
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("faiss.loader").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _check_ollama_service(endpoint: str, model_name: str) -> bool:
    """Pre-flight check to verify Ollama is reachable and model is available."""
    import httpx

    base_url = endpoint.split("/v1")[0].rstrip("/")
    tags_url = f"{base_url}/api/tags"
    try:
        resp = httpx.get(tags_url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            available = [m.get("name", "") for m in data.get("models", [])]
            matched = any(
                m == model_name or m.startswith(f"{model_name}:") or model_name.startswith(f"{m}:")
                for m in available
            )
            if matched:
                print(f"  [OK] Ollama is active and model '{model_name}' is ready.", flush=True)
            else:
                print(
                    f"  [WARNING] Ollama is running, but model '{model_name}' was not found in: {available}\n"
                    f"            You can pull it by running:  ollama pull {model_name}",
                    flush=True,
                )
            return True
        else:
            print(f"  [WARNING] Ollama returned status {resp.status_code} at {tags_url}", flush=True)
            return False
    except Exception as exc:
        print(
            f"  [WARNING] Could not reach Ollama at {tags_url} ({exc}).\n"
            f"            Make sure Ollama is running ('ollama serve' or start the Ollama desktop app).",
            flush=True,
        )
        return False


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch-ingest documents into ContextGraph knowledge graph & FAISS vector store using local Ollama model."
    )
    parser.add_argument(
        "corpus_dir",
        nargs="?",
        default=None,
        help="Path to corpus directory (default: from settings or ./data/corpus)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:3b",
        help="Ollama model to use for extraction & classification (default: qwen2.5:3b)",
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:11434/v1",
        help="Ollama OpenAI-compatible endpoint URL (default: http://127.0.0.1:11434/v1)",
    )
    parser.add_argument(
        "--provider",
        default="ollama",
        help="LLM provider name (default: ollama)",
    )
    return parser.parse_args()


async def main() -> None:
    """Main ingestion entrypoint."""
    args = parse_args()

    # Configure environment for Ollama with requested model
    os.environ["LLM_PROVIDER"] = args.provider
    os.environ["LOCAL_LLM_MODEL"] = args.model
    os.environ["LOCAL_LLM_ENDPOINT"] = args.endpoint

    from app.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()

    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else Path(settings.corpus_dir)
    if not corpus_dir.exists():
        raise SystemExit(f"Corpus directory not found: {corpus_dir}")

    print("====================================================================", flush=True)
    print("  AMC Corpus Ingestion Pipeline", flush=True)
    print(f"  LLM Provider : {args.provider}", flush=True)
    print(f"  LLM Model    : {args.model}", flush=True)
    print(f"  Endpoint     : {args.endpoint}", flush=True)
    print(f"  Corpus Dir   : {corpus_dir}", flush=True)
    print("====================================================================", flush=True)

    if args.provider.lower() in ("ollama", "local"):
        _check_ollama_service(args.endpoint, args.model)

    from app.api.deps import init_container

    container = init_container()
    container.vector.ensure_collection()

    supported = set(container.pipeline._registry.supported_extensions())
    paths = sorted(
        p for p in corpus_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported
    )
    print(f"\nFound {len(paths)} document(s) in {corpus_dir}", flush=True)
    if not paths:
        print("No supported documents found to ingest.", flush=True)
        await container.graph.close()
        return

    ok, failed = 0, 0
    for idx, path in enumerate(paths, 1):
        print(f"\n[{idx}/{len(paths)}] Ingesting {path.name} (corpus_version={container.pipeline._corpus_version})...", flush=True)
        try:
            doc = await container.pipeline.ingest_file(path)
            print(f"  [OK] Successfully ingested {path.name}", flush=True)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"  [FAILED] {path.name}: {exc}", flush=True)
    print(f"\nDone: {ok} ingested, {failed} failed.", flush=True)
    await container.graph.close()


if __name__ == "__main__":
    asyncio.run(main())
