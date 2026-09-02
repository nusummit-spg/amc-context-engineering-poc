"""
context_memory.py
===================
Multi-turn chat support: resolves ambiguous follow-up queries ("Why is
their limit higher?") into self-contained ones using recent conversation
history, and compresses history into a compact block for prompt injection
so multi-turn conversations don't snowball token usage turn over turn.
"""
from __future__ import annotations
import os

from app.engine import config
from app.engine import llm_text_client


def get_max_history_turns() -> int:
    return int(os.environ.get("MAX_HISTORY_TURNS", "4"))


def resolve_coreferences(query: str, history: list[dict]) -> str:
    """
    Uses an LLM pre-pass to resolve ambiguous pronouns (e.g. "they", "it") in the
    new query using conversation history. If the query is already explicit,
    returns it unchanged. Falls back to the original query on any failure.
    """
    if not history:
        return query

    recent_history = history[-get_max_history_turns():]
    history_str = "\n".join(f"{turn['role'].capitalize()}: {turn['content']}" for turn in recent_history)

    prompt = f"""You are a query resolution assistant.
Read the conversation history below, and then read the User's Follow-up Query.
If the follow-up query contains pronouns or ambiguous references (e.g., "they", "their", "it", "these", "the circular"), rewrite the query so it is fully self-contained and explicit, replacing the pronouns with the actual entities mentioned in the history.
If the follow-up query is already fully explicit and doesn't rely on history to be understood, return it exactly as is.

CONVERSATION HISTORY:
{history_str}

USER FOLLOW-UP QUERY: {query}

REWRITTEN EXPLICIT QUERY (Return ONLY the rewritten query text, nothing else):"""

    try:
        resolved_query, _ = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
        resolved_query = (resolved_query or "").strip(" \"'\n")
        return resolved_query if resolved_query else query
    except Exception as e:
        print(f"  [context_memory] Coreference resolution failed, using original query: {e}", flush=True)
        return query


def compress_history(history: list[dict]) -> str:
    """
    Compresses conversation history into a dense block for prompt injection.
    Truncates long assistant turns rather than summarizing — cheap, no LLM
    call, adequate for the small (default 4-turn) window this is scoped to.
    """
    if not history:
        return ""

    recent_history = history[-get_max_history_turns():]
    compressed_blocks = []

    for turn in recent_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "assistant" and len(content) > 1000:
            content = content[:997] + "..."
        compressed_blocks.append(f"[{role.upper()}] {content}")

    return "\n\n".join(compressed_blocks)
