# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
nli_evaluator.py
================
Natural Language Inference (NLI) model evaluator for hallucination detection and claim verification.
Implements Task 0.2 of the Chief Architect Implementation Plan.
Classifies (Premise, Hypothesis) pairs into:
  - ENTAILMENT: Hypothesis is fully supported by premise context
  - NEUTRAL: Hypothesis contains unverified or unrelated information
  - CONTRADICTION: Hypothesis directly contradicts facts in premise context
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.evaluation.nli")


class NLIEvaluator:
    """NLI entailment evaluator with hybrid neural model support and high-performance heuristic fallback."""

    def __init__(self, model_name_or_path: Optional[str] = None):
        self.model_name = model_name_or_path or "bert-base-uncased"
        self._neural_pipeline = None
        self.label_map = {
            0: "entailment",
            1: "neutral",
            2: "contradiction",
        }
        self._init_model()

    def _init_model(self):
        """Attempt to load transformers model if available; gracefully fallback to heuristic engine."""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
            import torch

            # If local fine-tuned model path exists, load it
            import os
            if os.path.exists(self.model_name):
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
                self._neural_pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer)
                logger.info("Loaded custom NLI model from %s", self.model_name)
        except Exception as exc:
            logger.debug("Neural NLI pipeline not active (%s); using deterministic heuristic engine", exc)
            self._neural_pipeline = None

    def evaluate(self, premise: str, hypothesis: str) -> Tuple[str, float]:
        """
        Evaluate if hypothesis is entailed by premise context.
        Returns:
            (label, confidence_score)
            label: "entailment" | "neutral" | "contradiction"
            confidence_score: float in [0.0, 1.0]
        """
        premise_clean = (premise or "").strip()
        hypo_clean = (hypothesis or "").strip()

        if not premise_clean or not hypo_clean:
            return "neutral", 0.5

        # 1. Neural classification path if active
        if self._neural_pipeline is not None:
            try:
                out = self._neural_pipeline(f"{premise_clean} [SEP] {hypo_clean}")[0]
                label = out["label"].lower()
                conf = float(out["score"])
                if label in ["entailment", "contradiction", "neutral"]:
                    return label, conf
            except Exception as exc:
                logger.warning("Neural NLI evaluation failed: %s; falling back to heuristic", exc)

        # 2. Semantic & Deterministic Verification Engine
        p_lower = premise_clean.lower()
        h_lower = hypo_clean.lower()

        # Check 1: Regulatory prohibition & guarantee violations
        guarantee_words = ["guarantee", "guaranteed", "assured", "promise", "cannot lose", "risk-free"]
        if any(gw in h_lower for gw in guarantee_words):
            if any(pw in p_lower for pw in ["prohibit", "forbidden", "disallow", "cannot guarantee", "no guaranteed"]):
                return "contradiction", 0.95
            if "%" in hypo_clean or "return" in h_lower:
                return "contradiction", 0.90

        # Check 2: Regulatory inversion / negation contradiction
        inversion_pairs = [
            ("prohibits", "can"),
            ("prohibits", "allows"),
            ("mandatory", "optional"),
            ("required", "not required"),
            ("minimum", "any"),
            ("maximum", "unlimited"),
        ]
        for p_term, h_term in inversion_pairs:
            if p_term in p_lower and re.search(r"\b" + re.escape(h_term) + r"\b", h_lower):
                return "contradiction", 0.88

        # Check 3: Numeric discrepancy detection
        # e.g., "Rs. 10 crore" vs "Rs. 25 crore" or "5 years" vs "2 years"
        p_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(%|crore|lakh|year|years|months|days)?", p_lower)
        h_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(%|crore|lakh|year|years|months|days)?", h_lower)

        if p_nums and h_nums:
            p_units = {unit: val for val, unit in p_nums if unit}
            h_units = {unit: val for val, unit in h_nums if unit}
            for unit, h_val in h_units.items():
                if unit in p_units and p_units[unit] != h_val:
                    # Contradicting numerical facts
                    return "contradiction", 0.85

        # Check 4: Substantial token overlap and factual alignment (Entailment)
        h_words = set(re.findall(r"\b\w{4,}\b", h_lower))
        p_words = set(re.findall(r"\b\w{4,}\b", p_lower))

        if h_words and p_words:
            overlap = len(h_words.intersection(p_words)) / len(h_words)
            if overlap >= 0.6:
                # Key statements match context
                return "entailment", min(0.70 + (overlap * 0.25), 0.96)
            elif overlap >= 0.35:
                return "neutral", 0.65

        # Default fallback
        return "neutral", 0.50

    def batch_evaluate(self, premises: List[str], hypotheses: List[str]) -> List[Dict[str, Any]]:
        """Evaluate a batch of premise-hypothesis pairs."""
        results = []
        for p, h in zip(premises, hypotheses):
            label, conf = self.evaluate(p, h)
            results.append({"label": label, "confidence": conf})
        return results


# Global singleton instance
_nli_evaluator: Optional[NLIEvaluator] = None


def get_nli_evaluator() -> NLIEvaluator:
    global _nli_evaluator
    if _nli_evaluator is None:
        _nli_evaluator = NLIEvaluator()
    return _nli_evaluator
