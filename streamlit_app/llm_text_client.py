"""
llm_text_client.py
===================
Claude-only. No fallback provider — if Claude fails after retries, the
caller gets an empty string/None and must handle that explicitly.
"""
from __future__ import annotations
import json
import re
import time
from typing import Optional

import anthropic
import config

_client: Optional[anthropic.Anthropic] = None

CLAUDE_MAX_RETRIES = 3
CLAUDE_RETRY_DELAY = 5


def _get_client() -> Optional[anthropic.Anthropic]:
    global _client
    if _client is None:
        if not config.CLAUDE_API_KEY:
            print("  [llm_text] No CLAUDE_API_KEY set in .env.", flush=True)
            return None
        _client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
        print("  [llm_text] Claude client ready.", flush=True)
    return _client


def call_llm_json(prompt: str, model_id: str = None) -> Optional[dict | list]:
    raw = call_llm(
        prompt + "\n\nRespond with ONLY valid JSON, no commentary, no markdown fences.",
        model_id=model_id)
    if not raw:
        return None
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None


def call_llm_with_usage(prompt: str, model_id: str = None, max_tokens: int = 4096) -> tuple[str, dict]:
    client = _get_client()
    model = model_id or config.CLAUDE_MODEL_RELATIONS
    empty_usage = {"input_tokens": 0, "output_tokens": 0}

    if not isinstance(max_tokens, int) or max_tokens <= 0:
        max_tokens = 1024
    max_tokens = min(max_tokens, 8192)

    if client is None:
        print("  [llm_text] No Claude client available — returning empty.", flush=True)
        return "", empty_usage

    for attempt in range(CLAUDE_MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            usage = {"input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens}
            return text, usage
        except anthropic.RateLimitError:
            wait = CLAUDE_RETRY_DELAY * (2 ** attempt)
            print(f"  [llm_text] Claude rate-limited, waiting {wait}s…", flush=True)
            time.sleep(wait)
        except Exception as e:
            print(f"  [llm_text] Claude call failed (attempt {attempt+1}): {e}", flush=True)
            if attempt < CLAUDE_MAX_RETRIES - 1:
                time.sleep(1.0)

    print("  [llm_text] Claude failed after all retries — returning empty.", flush=True)
    return "", empty_usage


def call_llm(prompt: str, model_id: str = None, max_tokens: int = 4096) -> str:
    """Backward-compatible — discards usage. Existing callers unaffected."""
    text, _ = call_llm_with_usage(prompt, model_id=model_id, max_tokens=max_tokens)
    return text