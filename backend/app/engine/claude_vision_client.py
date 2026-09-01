# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
claude_vision_client.py
=========================
Groq vision client helper. Uses llama-3.2-11b-vision-preview (config.GROQ_VISION_MODEL).
"""
from __future__ import annotations
import base64
import time
from typing import Optional

import groq
from app.engine import config
from app.engine.rate_limiter import vision_limiter

_client: Optional[groq.Groq] = None
VISION_MAX_RETRIES = 3
VISION_RETRY_BASE_DELAY = 3


def _get_client() -> Optional[groq.Groq]:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            print("  [groq-vision] No GROQ_API_KEY set.", flush=True)
            return None
        _client = groq.Groq(api_key=config.GROQ_API_KEY)
    return _client


def extract_from_image(image_bytes: bytes, prompt: str,
                        model: str = None, max_tokens: int = 4096) -> str:
    client = _get_client()
    if client is None:
        return ""
    model = model or config.GROQ_VISION_MODEL
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    for attempt in range(VISION_MAX_RETRIES):
        with vision_limiter:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.1,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }],
                )
                return resp.choices[0].message.content or ""
            except groq.RateLimitError:
                wait = VISION_RETRY_BASE_DELAY * (2 ** attempt)
                print(f"    [groq-vision] rate-limited, waiting {wait}s…", flush=True)
                time.sleep(wait)
            except Exception as e:
                print(f"    [groq-vision] attempt {attempt+1} failed: {e}", flush=True)
                if attempt == VISION_MAX_RETRIES - 1:
                    return ""
                time.sleep(1.0)
    return ""
