"""
Ingestion pipeline orchestrator — [Documents] -> [Parser] -> [Chunker] -> [PII Scrub]
from the architecture diagram. Stops short of [Embedder] (owned by vector/).

This is the boundary Lambda: it can run standalone (e.g. triggered by an S3
ObjectCreated event on the AMC/ bucket) and hands its output either to:
  (a) the extraction/ Lambda for unstructured chunks (NER path), or
  (b) graph/cypher_library.py's direct ETL writer for structured chunks.

See lambda_handlers/ingestion_handler.py for the AWS Lambda entrypoint.
"""
import os
from typing import List

from ingestion.parsers import get_parser, ParsedSection
from ingestion.chunker import chunk_sections, Chunk
from ingestion.pii import scrub_sections


def parse_file(filepath: str) -> List[ParsedSection]:
    parser = get_parser(filepath)
    if parser is None:
        print(f"[pipeline] no parser for {filepath}, skipping")
        return []
    return parser.parse(filepath)


def run_ingestion(filepaths: List[str]) -> dict:
    """
    Returns {"unstructured_chunks": [...], "structured_chunks": [...]} —
    pre-split so the caller (Lambda glue / Step Functions) can route each
    list to the right next stage without re-inspecting route_hint itself.
    """
    all_sections: List[ParsedSection] = []
    for fp in filepaths:
        all_sections.extend(parse_file(fp))

    scrubbed = scrub_sections(all_sections)
    chunks: List[Chunk] = chunk_sections(scrubbed)

    unstructured = [c for c in chunks if c.route_hint == "unstructured"]
    structured = [c for c in chunks if c.route_hint == "structured"]

    print(
        f"[pipeline] {len(filepaths)} files -> {len(chunks)} chunks "
        f"({len(unstructured)} unstructured -> NER path, {len(structured)} structured -> direct ETL)"
    )
    return {"unstructured_chunks": unstructured, "structured_chunks": structured}


def run_ingestion_for_directory(directory: str) -> dict:
    filepaths = [
        os.path.join(directory, f) for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    ]
    return run_ingestion(filepaths)


if __name__ == "__main__":
    import sys
    result = run_ingestion_for_directory(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    print(f"unstructured={len(result['unstructured_chunks'])} structured={len(result['structured_chunks'])}")