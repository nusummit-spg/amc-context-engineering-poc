"""WS3 — LLM client wrapper: Anthropic SDK + retry + client-side rate limiting.

Shared by all components (taxonomy classifier, NER, relationship extraction,
intent classification, synthesis). Two call styles:

  - complete()            -> free text
  - complete_structured() -> JSON constrained by a schema (output_config.format)

Note: claude-opus-4-8 removed sampling params (temperature/top_p/top_k) and
budget_tokens — do not add them here.
"""
import asyncio
import json
import logging
from typing import Any, Optional

import anthropic

from app.config import get_settings
from app.core.errors import UpstreamError

logger = logging.getLogger("llm")


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        # SDK retries 429/5xx/connection errors with exponential backoff itself.
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None,
            max_retries=settings.llm_max_retries,
        )
        self._model = settings.llm_model
        self._fast_model = settings.llm_fast_model
        self._max_tokens = settings.llm_max_tokens
        # Client-side rate limit: cap concurrent in-flight requests.
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        fast: bool = False,
        thinking: bool = False,
    ) -> str:
        """Plain text completion."""
        kwargs: dict[str, Any] = {
            "model": self._fast_model if fast else self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        response = await self._call(kwargs)
        return next((b.text for b in response.content if b.type == "text"), "")

    async def complete_structured(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        fast: bool = False,
    ) -> dict:
        """JSON completion constrained by a JSON schema (structured outputs)."""
        kwargs: dict[str, Any] = {
            "model": self._fast_model if fast else self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if system:
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]

        response = await self._call(kwargs)
        text = next((b.text for b in response.content if b.type == "text"), "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UpstreamError("LLM returned unparseable JSON", {"raw": text[:500]}) from exc

    async def _call(self, kwargs: dict):
        async with self._semaphore:
            try:
                response = await self._client.messages.create(**kwargs)
            except anthropic.RateLimitError as exc:
                raise UpstreamError("LLM rate limited after retries") from exc
            except anthropic.APIStatusError as exc:
                raise UpstreamError(f"LLM API error {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise UpstreamError("LLM connection error") from exc

        if response.stop_reason == "refusal":
            raise UpstreamError("LLM refused the request", {"stop_reason": "refusal"})
        if response.stop_reason == "max_tokens":
            logger.warning("LLM hit max_tokens — output may be truncated")
        return response

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
