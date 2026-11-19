"""Wave 4.0 (TDS-40 E6, ADR40-07): model-provider residency policy and outbound PII control.

Active when AMC_VERIFIED_SERVING_MODE=enforce and AMC_PROVIDER_POLICY=on.

Startup (assert_provider_policy) refuses to boot unless:
  * the configured provider is in AMC_LLM_PROVIDER_ALLOWLIST (comma-separated, required);
  * AMC_LLM_REGION (the operator-declared processing region of that provider) is in AMC_LLM_REGION_ALLOWLIST;
  * cross-provider and local fallbacks are OFF, so a provider failure becomes an abstention instead of a silent
    hop to another jurisdiction or model.

Every outbound call (outbound()) re-checks the provider and scrubs PII (PAN, Aadhaar, mobile, e-mail, bank
account, IFSC) from the prompt and system text with the existing ingestion scrubber; ISINs are preserved.

Honest limit: the region is DECLARED by the operator, not detected. It is checked against the allowlist and
recorded, which makes a wrong declaration an auditable configuration error rather than an invisible one.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)
FLAG = "AMC_PROVIDER_POLICY"
_REDACTED = re.compile(r"\[REDACTED_[A-Z_]+\]")


class ProviderPolicyError(RuntimeError):
    pass


def policy_enabled() -> bool:
    value = os.environ.get(FLAG, "off").strip().lower()
    if value not in ("on", "off"):
        raise ProviderPolicyError(f"{FLAG} must be 'on' or 'off'")
    return os.environ.get("AMC_VERIFIED_SERVING_MODE", "off") == "enforce" and value == "on"


def _csv(name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(name, "").split(",") if v.strip()}


def assert_provider_policy(settings) -> dict | None:
    """Raise ProviderPolicyError when the configuration violates the policy. Returns the recorded decision."""
    if not policy_enabled():
        return None
    provider = str(getattr(settings, "llm_provider", "") or "").lower()
    providers = _csv("AMC_LLM_PROVIDER_ALLOWLIST")
    regions = _csv("AMC_LLM_REGION_ALLOWLIST")
    region = os.environ.get("AMC_LLM_REGION", "").strip().lower()
    if not providers:
        raise ProviderPolicyError("AMC_LLM_PROVIDER_ALLOWLIST is required when the provider policy is on")
    if provider not in providers:
        raise ProviderPolicyError(f"LLM provider {provider!r} is not in AMC_LLM_PROVIDER_ALLOWLIST")
    if not regions or not region:
        raise ProviderPolicyError("AMC_LLM_REGION and AMC_LLM_REGION_ALLOWLIST are required when the provider policy is on")
    if region not in regions:
        raise ProviderPolicyError(f"declared provider region {region!r} is not in AMC_LLM_REGION_ALLOWLIST")
    if getattr(settings, "enable_multi_provider_fallback", False) or getattr(settings, "enable_local_llm_fallback", False):
        raise ProviderPolicyError("LLM provider fallbacks must be disabled when the provider policy is on")
    decision = {"provider": provider, "region": region, "model": getattr(settings, "llm_model", None)}
    logger.info("W40 provider policy: %s", decision)
    return decision


def outbound(provider: str, prompt: str, system: str | None) -> tuple[str, str | None]:
    """Check the provider and scrub PII from text leaving the process. No-op when the policy is off."""
    if not policy_enabled():
        return prompt, system
    if str(provider or "").lower() not in _csv("AMC_LLM_PROVIDER_ALLOWLIST"):
        raise ProviderPolicyError(f"LLM provider {provider!r} is not allowed")
    from app.engine.pii_scrub import scrub_text
    clean_prompt = scrub_text(prompt or "")
    clean_system = scrub_text(system) if system else system
    redacted = len(_REDACTED.findall(clean_prompt)) + len(_REDACTED.findall(clean_system or ""))
    redacted -= len(_REDACTED.findall(prompt or "")) + len(_REDACTED.findall(system or ""))
    if redacted:
        logger.warning("W40 outbound PII scrub redacted %d span(s) before the provider call", redacted)
    return clean_prompt, clean_system


__all__ = ["FLAG", "ProviderPolicyError", "policy_enabled", "assert_provider_policy", "outbound"]
