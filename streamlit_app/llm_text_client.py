"""
llm_text_client.py
===================
Unified LLM Client powered by LiteLLM.
- Primary provider: Groq (for fast testing & low latency using GROQ_API_KEY).
- Automatic / Configurable Switch: Switches back to Claude/Anthropic if
  PRIMARY_LLM_PROVIDER is set to 'claude'/'anthropic', if GROQ_API_KEY is unset,
  or if Groq API encounters a runtime failure/rate-limit.
"""
from __future__ import annotations
import os
import json
import re
import time
from typing import Optional, Tuple, Dict, Any, Generator

HAS_LITELLM = False
try:
    import litellm
    # Silence unnecessary litellm logs & ignore unsupported params across providers
    litellm.suppress_debug_info = True
    litellm.drop_params = True
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

import config


CLAUDE_MAX_RETRIES = 2
CLAUDE_RETRY_DELAY = 3
_anthropic_client = None


def _get_anthropic_client():
    """Lazy loader for native Anthropic client (used as safety backup)."""
    global _anthropic_client
    if _anthropic_client is None and getattr(config, "CLAUDE_API_KEY", ""):
        try:
            import anthropic
            import httpx
            http_client = httpx.Client(http2=True, keepalive_expiry=30.0, timeout=60.0)
            _anthropic_client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY, http_client=http_client)
        except Exception:
            try:
                import anthropic
                _anthropic_client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
            except Exception:
                _anthropic_client = None
    return _anthropic_client


def _sync_api_keys_to_env():
    """Ensure litellm finds keys in os.environ."""
    if getattr(config, "GROQ_API_KEY", ""):
        os.environ["GROQ_API_KEY"] = config.GROQ_API_KEY
    if getattr(config, "CLAUDE_API_KEY", ""):
        os.environ["ANTHROPIC_API_KEY"] = config.CLAUDE_API_KEY


def _resolve_model_and_fallbacks(model_id: str = None) -> Tuple[str, list[str]]:
    """
    Resolves the primary model and fallback model chain based on configuration.
    If PRIMARY_LLM_PROVIDER is 'groq' (and GROQ_API_KEY is available), uses Groq primary with Claude fallback.
    If PRIMARY_LLM_PROVIDER is 'claude'/'anthropic' or GROQ_API_KEY is missing, uses Claude directly.
    """
    _sync_api_keys_to_env()
    provider = getattr(config, "PRIMARY_LLM_PROVIDER", "groq").lower()
    has_groq = bool(getattr(config, "GROQ_API_KEY", ""))
    has_claude = bool(getattr(config, "CLAUDE_API_KEY", ""))

    groq_model = config.GROQ_MODEL_LIGHT if not model_id or "claude" in model_id.lower() else model_id
    groq_model = groq_model.replace("groq/", "")
    groq_model = f"groq/{groq_model}"

    claude_model = config.CLAUDE_MODEL_LIGHT if not model_id or "groq" in model_id.lower() else model_id
    claude_model = claude_model.replace("anthropic/", "")
    if "claude" in claude_model:
        claude_model = f"anthropic/{claude_model}"


    if provider in ("groq", "gq") and has_groq:
        target_model = groq_model
        fallback_models = []
        if "70b" in groq_model:
            fallback_models.append("groq/llama-3.1-8b-instant")
        if has_claude:
            fallback_models.append(claude_model)
        fallbacks = fallback_models
    else:
        target_model = claude_model
        fallbacks = ["groq/llama-3.1-8b-instant"] if has_groq else []


    return target_model, fallbacks


def call_llm_json(prompt: str, model_id: str = None) -> Optional[dict | list]:
    raw = call_llm(
        prompt + "\n\nRespond with ONLY valid JSON, no commentary, no markdown fences.",
        model_id=model_id
    )
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
) -> Tuple[str, Dict[str, int]]:
    user_content = user_prompt if user_prompt is not None else (prompt or "")
    empty_usage = {"input_tokens": 0, "output_tokens": 0}

    if not user_content:
        return "", empty_usage

    max_tokens = min(max(int(max_tokens or 1024), 1), 8192)
    target_model, fallbacks = _resolve_model_and_fallbacks(model_id)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    if HAS_LITELLM:
        for attempt in range(3):
            try:
                resp = litellm.completion(
                    model=target_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    fallbacks=fallbacks,
                )
                text = (resp.choices[0].message.content or "").strip()
                prompt_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
                comp_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
                usage = {"input_tokens": prompt_tokens, "output_tokens": comp_tokens}
                return text, usage
            except Exception as exc:
                err_msg = str(exc)
                if "ratelimit" in err_msg.lower() or "rate limit" in err_msg.lower():
                    # Parse 'try again in 24.08s' or 'try again in 1m5s'
                    wait_sec = 10.0
                    m_sec = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", err_msg, re.I)
                    if m_sec:
                        mins = float(m_sec.group(1) or 0)
                        secs = float(m_sec.group(2) or 0)
                        wait_sec = max(mins * 60 + secs + 1.0, 5.0)
                    print(f"  [llm_text] Rate limit hit — sleeping {wait_sec:.1f}s before retry (attempt {attempt+1}/3)...", flush=True)
                    time.sleep(wait_sec)
                    continue
                if getattr(config, "GROQ_API_KEY", ""):
                    err_msg = err_msg.replace(config.GROQ_API_KEY, "[REDACTED]")
                if getattr(config, "CLAUDE_API_KEY", ""):
                    err_msg = err_msg.replace(config.CLAUDE_API_KEY, "[REDACTED]")
                print(f"  [llm_text] LiteLLM call ({target_model}) failed: {type(exc).__name__}: {err_msg[:200]}", flush=True)
                break



    # Backup attempt: native Direct Claude client
    print("  [llm_text] LiteLLM unavailable or retries exhausted — attempting direct native fallback...", flush=True)
    return _direct_claude_fallback(user_content, system_prompt, max_tokens)



def _direct_claude_fallback(user_content: str, system_prompt: str = None, max_tokens: int = 4096) -> Tuple[str, Dict[str, int]]:
    client = _get_anthropic_client()
    empty_usage = {"input_tokens": 0, "output_tokens": 0}
    if not client:
        return "", empty_usage
    try:
        kwargs = {
            "model": config.CLAUDE_MODEL_LIGHT,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": user_content}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return text, usage
    except Exception as exc:
        print(f"  [llm_text] Native direct Claude fallback also failed: {exc}", flush=True)
        return "", empty_usage


def call_llm_streaming(
    prompt: str = None,
    model_id: str = None,
    max_tokens: int = 4096,
    system_prompt: str = None,
    user_prompt: str = None,
) -> Generator[str, None, None]:
    """Generator that yields text tokens as they arrive from primary LLM via LiteLLM."""
    user_content = user_prompt if user_prompt is not None else (prompt or "")
    if not user_content:
        yield ""
        return

    target_model, fallbacks = _resolve_model_and_fallbacks(model_id)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    try:
        response = litellm.completion(
            model=target_model,
            messages=messages,
            max_tokens=min(max_tokens, 8192),
            temperature=0.0,
            stream=True,
            fallbacks=fallbacks,
        )
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as exc:
        print(f"  [llm_text] LiteLLM Streaming failed ({exc})", flush=True)
        yield ""


def call_llm(prompt: str, model_id: str = None, max_tokens: int = 4096) -> str:
    """Backward-compatible wrapper."""
    text, _ = call_llm_with_usage(prompt, model_id=model_id, max_tokens=max_tokens)
    return text