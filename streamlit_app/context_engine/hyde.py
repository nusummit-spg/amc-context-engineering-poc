"""
hyde.py
========
Hypothetical Document Embeddings (HyDE).

Users search in "question space" ("What are the SEBI rules for algos?"), but
the FAISS index stores "answer space" prose (dense circular/guideline text).
That mismatch degrades retrieval on abstract or legal-sounding queries.

Before vector search, a fast LLM writes a short hypothetical passage that
would answer the question, formatted like the real corpus (SEBI circular /
AMFI guideline / scheme disclosure). That hypothetical text — not the raw
query — is what gets embedded and searched: answer-shaped text sits much
closer in embedding space to the real answer-shaped prose in the index than
a short question does.
"""
from __future__ import annotations

import time
from typing import Tuple

import config
import llm_text_client

_HYDE_PROMPT = """Write a short hypothetical excerpt (under 150 words) that would
answer the question below, as if it were an official SEBI circular, AMFI
guideline, or mutual fund scheme disclosure document. Do not include any
conversational filler such as "Here is the excerpt" or "Based on the
question" — output only the raw hypothetical passage text.

QUESTION: {question}

HYPOTHETICAL EXCERPT:"""


def generate_hypothetical_document(query: str) -> Tuple[str, float]:
    """Returns (hypothetical_text, latency_ms).

    Falls back to the original query text if the LLM call fails or returns
    nothing — a no-op substitution, so HyDE can never make retrieval worse
    than not running it at all."""
    t0 = time.perf_counter()
    prompt = _HYDE_PROMPT.format(question=query)
    text, _usage = llm_text_client.call_llm_with_usage(
        prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=300)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    hypothetical = text.strip() if text and text.strip() else query
    print(f"  [hyde] Generated hypothetical doc in {latency_ms:.1f}ms", flush=True)
    return hypothetical, latency_ms
