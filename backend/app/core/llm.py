# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
"""Module providing llm functionality."""


import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Optional
import httpx

import groq

from app.config import get_settings
from app.core.errors import UpstreamError

logger = logging.getLogger("llm")

_STREAM_STALL_TIMEOUT = 30.0    # seconds with no chunk before treating stream as stalled
_BACKOFF_DELAYS = [1.0, 2.0, 4.0, 8.0]  # exponential backoff for rate-limit recovery

class LLMClient:
    def __init__(self) -> None:
        """Initialize a new instance of LLMClient.
        """
        self._settings = get_settings()
        self._provider = self._settings.llm_provider.lower()
        self._semaphore = asyncio.Semaphore(self._settings.llm_max_concurrency)
        self._http_client = httpx.AsyncClient(timeout=30.0)

        # Groq Client (Primary API Provider)
        self._groq_client = groq.AsyncGroq(
            api_key=self._settings.groq_api_key or None,
            max_retries=self._settings.llm_max_retries,
        )

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        fast: bool = False,
        thinking: bool = False,
    ) -> str:
        """Plain text completion with Groq as exclusive primary API provider.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.
            thinking (bool): The thinking.

        Returns:
            str: Resulting str instance.
        """
        # 1. Primary Provider Call (Groq)
        try:
            return await self._call_provider(self._provider, prompt, system, max_tokens, fast, thinking, structured_schema=None)
        except Exception as primary_exc:
            logger.warning("Primary LLM provider (%s) call failed: %s", self._provider, primary_exc)

            # 2. Multi-Provider Fallback (DISABLED BY DEFAULT)
            if self._settings.enable_multi_provider_fallback:
                providers_to_try = [p for p in ["openai", "gemini"] if p != self._provider]
                for fallback_p in providers_to_try:
                    try:
                        logger.info("Attempting multi-provider fallback to %s", fallback_p)
                        return await self._call_provider(fallback_p, prompt, system, max_tokens, fast, thinking, structured_schema=None)
                    except Exception as fb_exc:
                        logger.debug("Fallback provider %s failed: %s", fallback_p, fb_exc)

            # 3. Local LLM Fallback (DISABLED BY DEFAULT)
            if self._settings.enable_local_llm_fallback:
                try:
                    logger.info("Attempting local small LLM fallback at %s", self._settings.local_llm_endpoint)
                    return await self._call_local_llm(prompt, system, max_tokens)
                except Exception as local_exc:
                    logger.warning("Local LLM fallback failed: %s", local_exc)

            raise primary_exc

    async def complete_structured(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        fast: bool = False,
    ) -> dict:
        """JSON completion constrained by JSON schema with Groq as primary provider.

        Args:
            prompt (str): The prompt.
            schema (dict): Graph or database schema definition.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.

        Returns:
            dict: Dictionary containing result data or status.
        """
        # 1. Primary Provider Call (Groq)
        try:
            raw_text = await self._call_provider(self._provider, prompt, system, max_tokens, fast, False, structured_schema=schema)
            return self._parse_json(raw_text)
        except Exception as primary_exc:
            logger.warning("Primary LLM provider (%s) structured call failed: %s", self._provider, primary_exc)

            # 2. Multi-Provider Fallback (DISABLED BY DEFAULT)
            if self._settings.enable_multi_provider_fallback:
                providers_to_try = [p for p in ["openai", "gemini"] if p != self._provider]
                for fallback_p in providers_to_try:
                    try:
                        logger.info("Attempting structured fallback to %s", fallback_p)
                        raw = await self._call_provider(fallback_p, prompt, system, max_tokens, fast, False, structured_schema=schema)
                        return self._parse_json(raw)
                    except Exception as fb_exc:
                        logger.debug("Structured fallback provider %s failed: %s", fallback_p, fb_exc)

            # 3. Local LLM Fallback (DISABLED BY DEFAULT)
            if self._settings.enable_local_llm_fallback:
                try:
                    logger.info("Attempting structured local LLM fallback at %s", self._settings.local_llm_endpoint)
                    raw = await self._call_local_llm(prompt, system, max_tokens)
                    return self._parse_json(raw)
                except Exception as local_exc:
                    logger.warning("Local structured LLM fallback failed: %s", local_exc)

            raise primary_exc

    async def complete_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        fast: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream plain text completion token-by-token via Groq.

        Yields text chunks as they arrive. Handles:
        - Rate limits: exponential backoff up to 4 retries before raising
        - Stall detection: raises UpstreamError if no chunk for _STREAM_STALL_TIMEOUT seconds
        - Fallback: if streaming not supported by provider, falls back to single-chunk yield

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.
        """
        last_exc: Optional[Exception] = None
        for attempt, delay in enumerate([0.0] + _BACKOFF_DELAYS):
            if delay:
                logger.info("Stream retry %d/%d after %.1fs backoff", attempt, len(_BACKOFF_DELAYS), delay)
                await asyncio.sleep(delay)
            try:
                async for chunk in self._call_groq_stream(prompt, system, max_tokens, fast):
                    yield chunk
                return  # success — stop retrying
            except groq.RateLimitError as exc:
                last_exc = exc
                logger.warning("Groq rate limit on stream attempt %d: %s", attempt + 1, exc)
                if attempt >= len(_BACKOFF_DELAYS):
                    break
                continue
            except UpstreamError:
                raise
            except Exception as exc:
                raise UpstreamError(f"Groq stream failed: {exc}") from exc
        raise UpstreamError("Groq stream rate limited after all retries") from last_exc

    async def _call_groq_stream(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
        fast: bool,
    ) -> AsyncGenerator[str, None]:
        """Low-level Groq streaming call — yields delta text chunks.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.
        """
        api_key = self._settings.groq_api_key
        if not api_key:
            raise UpstreamError("Groq API key not configured")

        model = self._settings.llm_fast_model if fast else self._settings.llm_model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        default_tokens = 1500 if fast else self._settings.llm_max_tokens
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or default_tokens,
            "temperature": 0.1,
            "stream": True,
        }

        async with self._semaphore:
            try:
                stream = await self._groq_client.chat.completions.create(**kwargs)
                last_chunk_time = asyncio.get_event_loop().time()
                async for chunk in stream:
                    # Stall detection: abort if no chunk for _STREAM_STALL_TIMEOUT seconds
                    now = asyncio.get_event_loop().time()
                    if now - last_chunk_time > _STREAM_STALL_TIMEOUT:
                        logger.warning("Groq stream stalled — no chunk for %.0fs, aborting", _STREAM_STALL_TIMEOUT)
                        raise UpstreamError("Stream stalled: no data received for 30 seconds")
                    last_chunk_time = now

                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
            except groq.RateLimitError:
                raise
            except groq.APIStatusError as exc:
                raise UpstreamError(f"Groq API error {exc.status_code}: {exc.message}") from exc
            except groq.APIConnectionError as exc:
                raise UpstreamError("Groq connection error") from exc

    async def _call_provider(
        self,
        provider: str,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
        fast: bool,
        thinking: bool,
        structured_schema: Optional[dict],
    ) -> str:
        """Call provider.

        Args:
            provider (str): The provider.
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.
            thinking (bool): The thinking.
            structured_schema (Optional[dict]): The structured schema.

        Returns:
            str: Resulting str instance.
        """
        if provider == "groq":
            return await self._call_groq(prompt, system, max_tokens, fast, structured_schema)
        elif provider == "openai":
            return await self._call_openai(prompt, system, max_tokens, structured_schema)
        elif provider == "gemini":
            return await self._call_gemini(prompt, system, max_tokens, structured_schema)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    async def _call_groq(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
        fast: bool,
        structured_schema: Optional[dict],
    ) -> str:
        """Call groq.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            fast (bool): The fast.
            structured_schema (Optional[dict]): The structured schema.

        Returns:
            str: Resulting str instance.
        """
        api_key = self._settings.groq_api_key
        if not api_key:
            raise UpstreamError("Groq API key not configured")

        model = self._settings.llm_fast_model if fast else self._settings.llm_model
        messages = []
        if structured_schema:
            sys_text = (
                (system + "\n\nYou must return ONLY a raw valid JSON object. Do NOT wrap in markdown code blocks or ```json. Do NOT include any explanations, preamble, or trailing text. The output MUST start with '{' and end with '}'.")
                if system
                else "You must return ONLY a raw valid JSON object. Do NOT wrap in markdown code blocks or ```json. Do NOT include any explanations, preamble, or trailing text. The output MUST start with '{' and end with '}'."
            )
            messages.append({"role": "system", "content": sys_text})
        elif system:
            messages.append({"role": "system", "content": system})
        
        user_content = prompt
        if structured_schema:
            user_content += f"\n\nRespond strictly with a valid JSON object matching this schema:\n{json.dumps(structured_schema)}\nReturn ONLY the raw JSON object starting with '{{' and ending with '}}'."
        messages.append({"role": "user", "content": user_content})

        default_tokens = 2500 if fast else (self._settings.llm_max_tokens or 4096)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or default_tokens,
            "temperature": 0.1,
        }
        if structured_schema:
            kwargs["response_format"] = {"type": "json_object"}

        delays = [3.0, 6.0, 12.0, 20.0, 30.0, 45.0]
        for attempt in range(len(delays) + 1):
            async with self._semaphore:
                try:
                    response = await self._groq_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content or ""
                except groq.RateLimitError as exc:
                    err_msg = str(exc)
                    # If primary heavy model hit rate/daily limit, fall back immediately to fast model
                    if kwargs.get("model") != self._settings.llm_fast_model and self._settings.llm_fast_model:
                        logger.warning("Groq model %s rate limited (%s). Falling back immediately to %s",
                                       kwargs["model"], err_msg, self._settings.llm_fast_model)
                        kwargs["model"] = self._settings.llm_fast_model
                        continue
                    if attempt >= len(delays):
                        logger.error("Groq rate limit exceeded after %d retries: %s", len(delays), exc)
                        raise UpstreamError("Groq rate limited after retries") from exc
                    m_min_sec = re.search(r"try again in (?:(\d+)m)?([\d\.]+)s", err_msg)
                    m_ms = re.search(r"try again in ([\d\.]+)ms", err_msg)
                    if m_min_sec:
                        mins = float(m_min_sec.group(1) or 0)
                        secs = float(m_min_sec.group(2) or 0)
                        backoff = (mins * 60.0) + secs + 1.5
                    elif m_ms:
                        backoff = (float(m_ms.group(1)) / 1000.0) + 1.0
                    else:
                        backoff = delays[attempt]
                    logger.warning("Groq rate limited (attempt %d/%d): %s. Sleeping %.1fs before retrying...", attempt + 1, len(delays), err_msg, backoff)
                    await asyncio.sleep(backoff)
                    continue
                except groq.APIStatusError as exc:
                    if exc.status_code == 400 and "json_validate_failed" in getattr(exc, "message", str(exc)):
                        logger.info("Groq json_validate_failed; retrying without response_format constraint")
                        kwargs_retry = dict(kwargs)
                        kwargs_retry.pop("response_format", None)
                        try:
                            response = await self._groq_client.chat.completions.create(**kwargs_retry)
                            return response.choices[0].message.content or "{}"
                        except Exception as retry_exc:
                            raise UpstreamError(f"Groq API error {exc.status_code}: {exc.message}") from retry_exc
                    raise UpstreamError(f"Groq API error {exc.status_code}: {exc.message}") from exc
                except groq.APIConnectionError as exc:
                    raise UpstreamError("Groq connection error") from exc

    async def _call_openai(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
        structured_schema: Optional[dict],
    ) -> str:
        """Call openai.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            structured_schema (Optional[dict]): The structured schema.

        Returns:
            str: Resulting str instance.
        """
        api_key = self._settings.openai_api_key
        if not api_key:
            raise UpstreamError("OpenAI API key not configured")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._settings.openai_model,
            "messages": messages,
            "max_tokens": max_tokens or 4000,
        }
        if structured_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "synthesis_response", "schema": structured_schema, "strict": True},
            }

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        resp = await self._http_client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise UpstreamError(f"OpenAI API error {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_gemini(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
        structured_schema: Optional[dict],
    ) -> str:
        """Call gemini.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.
            structured_schema (Optional[dict]): The structured schema.

        Returns:
            str: Resulting str instance.
        """
        api_key = self._settings.gemini_api_key
        if not api_key:
            raise UpstreamError("Gemini API key not configured")

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system}"}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload: dict[str, Any] = {"contents": contents}
        if structured_schema:
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": structured_schema,
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._settings.gemini_model}:generateContent?key={api_key}"
        resp = await self._http_client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code != 200:
            raise UpstreamError(f"Gemini API error {resp.status_code}: {resp.text}")
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        return candidates[0]["content"]["parts"][0]["text"]

    async def _call_local_llm(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: Optional[int],
    ) -> str:
        """Call local llm.

        Args:
            prompt (str): The prompt.
            system (Optional[str]): The system.
            max_tokens (Optional[int]): Collection or list of max tokens.

        Returns:
            str: Resulting str instance.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._settings.local_llm_model,
            "messages": messages,
            "max_tokens": max_tokens or 2000,
        }
        url = f"{self._settings.local_llm_endpoint.rstrip('/')}/chat/completions"
        resp = await self._http_client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code != 200:
            raise UpstreamError(f"Local LLM error {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _parse_json(self, text: str) -> dict:
        """Parse json.

        Args:
            text (str): Input text content.

        Returns:
            dict: Dictionary containing result data or status.
        """
        clean = text.strip()
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
            if match:
                clean = match.group(1).strip()
        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            clean = clean[first_brace : last_brace + 1]
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            first_bracket = clean.find("[")
            last_bracket = clean.rfind("]")
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                try:
                    parsed_list = json.loads(clean[first_bracket : last_bracket + 1])
                    return {"entities": parsed_list, "relationships": parsed_list}
                except Exception:
                    pass
            logger.warning("LLM returned unparseable JSON (first 300 chars: %r)", text[:300])
            return {}

    async def ping(self) -> bool:
        """Check connectivity and availability of the service.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        try:
            await self.complete("ping", max_tokens=8, fast=True)
            return True
        except Exception:
            return False


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Retrieve llm client.

    Returns:
        LLMClient: Resulting LLMClient instance.
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
