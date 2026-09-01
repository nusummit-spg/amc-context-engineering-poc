# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
llm_text_client.py
===================
Groq-only. Uses Groq API client with llama-3.3-70b-versatile and llama-3.1-8b-instant.
"""
from __future__ import annotations
import json
import re
import time
from typing import Optional

import groq
from app.engine import config

_client: Optional[groq.Groq] = None

GROQ_MAX_RETRIES = 3
GROQ_RETRY_DELAY = 3


def _get_client() -> Optional[groq.Groq]:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            print("  [llm_text] No GROQ_API_KEY set in .env.", flush=True)
            return None
        _client = groq.Groq(api_key=config.GROQ_API_KEY)
        print("  [llm_text] Groq client ready.", flush=True)
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


def call_llm_with_usage(
    prompt: str = None,
    model_id: str = None,
    max_tokens: int = 4096,
    system_prompt: str = None,
    user_prompt: str = None,
) -> tuple[str, dict]:
    client = _get_client()
    model = model_id or config.GROQ_MODEL_RELATIONS
    empty_usage = {"input_tokens": 0, "output_tokens": 0}

    if not isinstance(max_tokens, int) or max_tokens <= 0:
        max_tokens = 1024
    max_tokens = min(max_tokens, 8192)

    if client is None:
        print("  [llm_text] No Groq client available — returning empty.", flush=True)
        return "", empty_usage

    user_content = user_prompt if user_prompt is not None else (prompt or "")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    for attempt in range(GROQ_MAX_RETRIES):
        t_attempt = time.perf_counter()
        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "presence_penalty": 0.1,
                "frequency_penalty": 0.15,
                "messages": messages,
            }
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            usage = {
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
            }
            if attempt > 0:
                elapsed = (time.perf_counter() - t_attempt) * 1000.0
                print(f"  [llm_text] Groq ({model}) succeeded on attempt {attempt+1}/{GROQ_MAX_RETRIES} "
                      f"({elapsed:.0f}ms for this attempt)", flush=True)
            return text, usage
        except groq.RateLimitError:
            wait = GROQ_RETRY_DELAY * (2 ** attempt)
            print(f"  [llm_text] Groq rate-limited, waiting {wait}s…", flush=True)
            time.sleep(wait)
        except Exception as e:
            print(f"  [llm_text] Groq call failed (attempt {attempt+1}): {e}", flush=True)
            if attempt < GROQ_MAX_RETRIES - 1:
                time.sleep(1.0)

    print("  [llm_text] Groq failed after all retries — returning empty.", flush=True)
    return "", empty_usage


def call_llm(prompt: str, model_id: str = None, max_tokens: int = 4096) -> str:
    """Backward-compatible — discards usage. Existing callers unaffected."""
    text, _ = call_llm_with_usage(prompt, model_id=model_id, max_tokens=max_tokens)
    return text
