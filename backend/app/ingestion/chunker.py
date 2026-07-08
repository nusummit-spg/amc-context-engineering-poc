"""WS2 — Semantic chunking engine: heading-aware, clause-aware, max ~400 tokens.

Strategy:
  1. Chunk within section boundaries (never merge across headings).
  2. Split oversized sections on sentence/clause boundaries.
  3. Keep [TABLE] blocks intact where possible.
Token counts use a chars/4 approximation — good enough for budget control;
exact counting isn't needed at chunk granularity.
"""
import re

from app.schemas.documents import Chunk, Document

_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(])")


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_long_text(text: str, max_tokens: int) -> list[str]:
    if approx_tokens(text) <= max_tokens:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _SENTENCE_RE.split(text):
        st = approx_tokens(sentence)
        if current and current_tokens + st > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += st
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_document(document: Document, max_tokens: int = 400) -> list[Chunk]:
    chunks: list[Chunk] = []
    order = 0
    for section in document.sections:
        if not section.text.strip():
            continue
        header = f"[{document.title or document.filename}"
        if section.title:
            header += f" — {section.title}"
        header += "]\n"

        # Keep table blocks as standalone chunks; chunk prose separately.
        blocks = re.split(r"(\[TABLE\]\n(?:.*\n?)*?)(?=\n\n|\Z)", section.text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            budget = max_tokens - approx_tokens(header)
            for piece in _split_long_text(block, max(budget, 50)):
                text = header + piece
                chunks.append(Chunk(
                    document_id=document.document_id,
                    section_id=section.section_id,
                    text=text,
                    token_count=approx_tokens(text),
                    order=order,
                    metadata={"section_title": section.title, **section.metadata},
                ))
                order += 1
    return chunks
