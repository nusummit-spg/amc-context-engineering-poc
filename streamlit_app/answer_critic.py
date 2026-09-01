# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
AMC Context Engineering — Agentic Core: Answer Critic (LLM-as-Judge)
Fact-checks generated answers against ground-truth context for high-stakes queries.
Verifies numeric claims, entity accuracy, and appends transparency disclaimers if needed.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import llm_text_client
import config

CRITIC_PROMPT = """You are a strict financial compliance critic reviewing an AI-generated answer.
Check the answer against the provided source context.

SOURCE CONTEXT (Ground Truth):
{context}

GENERATED ANSWER:
{answer}

ORIGINAL QUESTION:
{query}

Evaluate:
1. Are all numeric claims in the answer supported by the context?
2. Are entity names and regulatory clauses accurate?
3. Verdict: APPROVE, FLAG, or REJECT.

Return ONLY valid JSON matching this schema:
{{
  "verdict": "APPROVE|FLAG|REJECT",
  "issues": ["issue 1", "issue 2"],
  "corrected_answer": "..."
}}
"""


@dataclass
class CritiqueResult:
    verdict: str  # APPROVE, FLAG, REJECT
    answer: str
    flagged: bool = False
    issues: List[str] = field(default_factory=list)


class AnswerCritic:
    TRIGGER_TYPES = {"direct_lookup", "aggregation", "comparison"}

    def critique(self, query: str, answer: str, context: str, query_type: str) -> CritiqueResult:
        if query_type not in self.TRIGGER_TYPES or len(answer) < 40:
            return CritiqueResult(verdict="APPROVE", answer=answer)

        try:
            prompt = CRITIC_PROMPT.format(context=context[:2500], answer=answer, query=query)
            res = llm_text_client.call_llm_json(prompt, model_id=config.CLAUDE_MODEL_LIGHT)

            if isinstance(res, dict) and "verdict" in res:
                verdict = res.get("verdict", "APPROVE").upper()
                issues = res.get("issues", [])
                corrected = res.get("corrected_answer")

                if verdict == "REJECT" and corrected:
                    return CritiqueResult(verdict="REJECT", answer=corrected, flagged=True, issues=issues)
                elif verdict == "FLAG" and issues:
                    disclaimer = f"\n\n*⚠️ Verification note: {'; '.join(issues)}*"
                    return CritiqueResult(verdict="FLAG", answer=answer + disclaimer, flagged=True, issues=issues)

        except Exception as exc:
            print(f"  [AnswerCritic Warning] Critique pass fallback: {exc}", flush=True)

        return CritiqueResult(verdict="APPROVE", answer=answer)
