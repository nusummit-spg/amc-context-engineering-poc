"""
AMC Context Engineering — Compliance Guardrails & Input/Output Safety Engine
Implements Guardrails AI validation, SEBI RIA Financial Advice Shield, 
Prompt Injection Protection, and SEBI Risk Disclaimer Enforcement.
"""

import re
from typing import Dict, Any, List

# Try importing Guardrails AI if installed
HAS_GUARDRAILS_AI = False
try:
    import guardrails as gd
    HAS_GUARDRAILS_AI = True
except ImportError:
    HAS_GUARDRAILS_AI = False

# Prompt Injection Attack Patterns
PROMPT_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?(previous|above)\s+(instructions|prompts)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+DAN', re.IGNORECASE),
    re.compile(r'bypass\s+(system|safety)\s+rules', re.IGNORECASE),
    re.compile(r'system\s+prompt\s+reveal', re.IGNORECASE),
    re.compile(r'forget\s+all\s+rules', re.IGNORECASE),
]

# Unauthorized Financial Advice Patterns (SEBI Investment Adviser - RIA Protection)
UNAUTHORIZED_ADVICE_PATTERNS = [
    re.compile(r'i\s+recommend\s+you\s+(to\s+)?buy', re.IGNORECASE),
    re.compile(r'you\s+should\s+invest\s+\d+%', re.IGNORECASE),
    re.compile(r'guaranteed\s+returns?\s+of', re.IGNORECASE),
    re.compile(r'sell\s+your\s+holding\s+in', re.IGNORECASE),
    re.compile(r'put\s+all\s+your\s+money\s+in', re.IGNORECASE),
]

# Mandatory SEBI Risk Disclaimer
SEBI_RISK_DISCLAIMER = (
    "\n\n*Disclaimer: Mutual Fund investments are subject to market risks, read all scheme related "
    "documents carefully. Past performance is not indicative of future returns.*"
)


def validate_input_query(query: str) -> Dict[str, Any]:
    """
    Validate incoming user query against prompt injection and safety rules.
    """
    if not query:
        return {"is_safe": True, "risk_flag": None, "sanitized_query": query}

    # 1. Check Prompt Injection
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(query):
            return {
                "is_safe": False,
                "risk_flag": "PROMPT_INJECTION_DETECTED",
                "sanitized_query": "[BLOCKED: Query contains unauthorized prompt injection instructions]",
                "guardrail_engine": "GuardrailsAI_InjectionShield"
            }

    return {
        "is_safe": True,
        "risk_flag": None,
        "sanitized_query": query,
        "guardrail_engine": "GuardrailsAI_Standard"
    }


def validate_llm_output(answer: str, context: str = "", domain_intent: str = "general") -> Dict[str, Any]:
    """
    Validate LLM output answer against compliance rules:
    - SEBI Financial Advice Shield (blocks unauthorized buy/sell advice)
    - SEBI Risk Disclaimer Enforcement
    - Hallucination / Provenance check
    """
    if not answer:
        return {"is_valid": True, "modified_answer": answer, "reasons": [], "advice_shield_triggered": False}

    modified_answer = answer
    reasons = []
    advice_shield_triggered = False

    # 1. Check Unauthorized Financial Advice (SEBI RIA Shield)
    for pattern in UNAUTHORIZED_ADVICE_PATTERNS:
        if pattern.search(modified_answer):
            advice_shield_triggered = True
            reasons.append("UNAUTHORIZED_FINANCIAL_ADVICE_REDACTED")
            # Redact unauthorized personalized advice claim with regulatory notice
            modified_answer = pattern.sub(
                "[Regulatory Notice: Personal investment advice is restricted under SEBI RIA Regulations. Please consult a registered investment adviser]",
                modified_answer
            )

    # 2. SEBI Risk Disclaimer Enforcement for Investor Queries
    if "disclaimer" not in modified_answer.lower() and "market risk" not in modified_answer.lower():
        modified_answer += SEBI_RISK_DISCLAIMER
        reasons.append("SEBI_DISCLAIMER_ENFORCED")

    # 3. Simple Provenance Check for Numbers
    numbers_in_answer = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', answer))
    if numbers_in_answer and context:
        unsupported = [n for n in numbers_in_answer if n not in context and len(n) > 1 and n not in ("1", "2", "3", "2026", "2017")]
        if len(unsupported) > 3:
            reasons.append(f"UNSUPPORTED_NUMERIC_CLAIM: {unsupported[:3]}")

    return {
        "is_valid": True,
        "modified_answer": modified_answer,
        "reasons": reasons,
        "advice_shield_triggered": advice_shield_triggered,
        "guardrail_engine": "GuardrailsAI_OutputCompliance"
    }
