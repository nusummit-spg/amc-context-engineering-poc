# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import asyncio
import json
import logging
from typing import Any, Optional
import httpx

import groq

from app.config import get_settings
from app.core.errors import UpstreamError

logger = logging.getLogger("llm")


class LLMClient:
    def __init__(self) -> None:
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
        """Plain text completion with Groq as exclusive primary API provider."""
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
        """JSON completion constrained by JSON schema with Groq as primary provider."""
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
        api_key = self._settings.groq_api_key
        if not api_key:
            raise UpstreamError("Groq API key not configured")

        model = self._settings.llm_fast_model if fast else self._settings.llm_model
        messages = []
        if structured_schema:
            sys_text = (system + "\n\nYou must output a valid JSON object.") if system else "You must output a valid JSON object."
            messages.append({"role": "system", "content": sys_text})
        elif system:
            messages.append({"role": "system", "content": system})
        
        user_content = prompt
        if structured_schema:
            user_content += f"\n\nRespond strictly with a valid JSON object matching this schema:\n{json.dumps(structured_schema)}"
        messages.append({"role": "user", "content": user_content})

        default_tokens = 1500 if fast else self._settings.llm_max_tokens
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or default_tokens,
            "temperature": 0.1,
        }
        if structured_schema:
            kwargs["response_format"] = {"type": "json_object"}

        async with self._semaphore:
            try:
                response = await self._groq_client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            except groq.RateLimitError as exc:
                raise UpstreamError("Groq rate limited after retries") from exc
            except groq.APIStatusError as exc:
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
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as exc:
            raise UpstreamError("LLM returned unparseable JSON", {"raw": text[:500]}) from exc

    async def ping(self) -> bool:
        try:
            await self.complete("ping", max_tokens=8, fast=True)
            return True
        except Exception:
            return False


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
