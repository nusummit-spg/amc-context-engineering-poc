"""
Semantic chunker — operates on ParsedSection objects. Structured sections
(route_hint == "structured") pass through untouched, one "chunk" per row
batch, since they don't need sentence-level splitting. Unstructured sections
get greedy sentence-boundary packing.
"""
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any

from ingestion.parsers.base import ParsedSection

MAX_CHUNK_CHARS = 1800
MIN_CHUNK_CHARS = 200
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_file: str
    section_label: str
    route_hint: str
    order: int
    structured_rows: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _chunk_unstructured(section: ParsedSection) -> List[Chunk]:
    sentences = _split_sentences(section.text)
    chunks, buffer, buffer_len, order = [], [], 0, 0

    def flush():
        nonlocal buffer, buffer_len, order
        if buffer:
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4())[:8], text=" ".join(buffer),
                    source_file=section.source_file, section_label=section.heading,
                    route_hint="unstructured", order=order, metadata=section.metadata,
                )
            )
            order += 1
            buffer, buffer_len = [], 0

    for sentence in sentences:
        if buffer_len + len(sentence) > MAX_CHUNK_CHARS and buffer_len >= MIN_CHUNK_CHARS:
            flush()
        buffer.append(sentence)
        buffer_len += len(sentence)
    flush()
    return chunks


def _chunk_structured(section: ParsedSection, batch_size: int = 500) -> List[Chunk]:
    """Batches rows so downstream ETL writes to Neo4j in manageable transactions."""
    chunks = []
    rows = section.structured_rows
    for order, i in enumerate(range(0, len(rows), batch_size)):
        batch = rows[i : i + batch_size]
        chunks.append(
            Chunk(
                chunk_id=str(uuid.uuid4())[:8],
                text=f"[{len(batch)} structured rows]",
                source_file=section.source_file, section_label=section.heading,
                route_hint="structured", order=order,
                structured_rows=batch, metadata=section.metadata,
            )
        )
    return chunks


def chunk_sections(sections: List[ParsedSection]) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for section in sections:
        if not section.text.strip() and not section.structured_rows:
            continue
        if section.route_hint == "structured":
            all_chunks.extend(_chunk_structured(section))
        else:
            all_chunks.extend(_chunk_unstructured(section))
    return all_chunks