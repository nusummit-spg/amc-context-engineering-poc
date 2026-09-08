# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
finetune_nli_model.py
=====================
Fine-tuning pipeline for training a domain-specific Natural Language Inference
model on Indian Mutual Fund & SEBI regulatory compliance data.
Implements Task 0.2.2 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("finetune_nli")


def create_nli_training_data() -> List[Dict[str, Any]]:
    """Generate AMC domain training dataset with entailment, neutral, and contradiction pairs."""
    return [
        # ── Entailment (Label 0) ─────────────────────────────────────────
        {
            "premise": "SEBI circular specifies minimum AUM of Rs. 10 crore for equity fund launch",
            "hypothesis": "The minimum AUM requirement for launching an equity fund is Rs. 10 crore",
            "label": 0,
        },
        {
            "premise": "AMCs must maintain a minimum net worth of Rs. 50 crore under Regulation 21",
            "hypothesis": "Regulation 21 mandates AMCs to hold at least Rs. 50 crore in net worth",
            "label": 0,
        },
        {
            "premise": "SEBI requires quarterly portfolio disclosures for all mutual fund schemes on AMFI portal",
            "hypothesis": "Mutual fund scheme portfolios must be published every quarter",
            "label": 0,
        },
        {
            "premise": "Liquid funds can invest only in debt and money market securities with maturity up to 91 days",
            "hypothesis": "The maximum maturity for investments by liquid funds is 91 days",
            "label": 0,
        },

        # ── Contradiction (Label 2) ──────────────────────────────────────
        {
            "premise": "SEBI circular specifies minimum AUM of Rs. 10 crore for equity fund launch",
            "hypothesis": "AMCs can launch equity funds with any AUM amount without limit",
            "label": 2,
        },
        {
            "premise": "SEBI strictly prohibits guaranteed returns or assured gains on mutual fund schemes",
            "hypothesis": "Mutual funds can guarantee annual returns of 15% to investors",
            "label": 2,
        },
        {
            "premise": "Fund manager minimum experience is 5 years under SEBI MF Regulations",
            "hypothesis": "Individuals with zero prior investment experience can be appointed fund managers",
            "label": 2,
        },
        {
            "premise": "Exit load of 1% is charged if redeemed within 365 days",
            "hypothesis": "Redemptions on day 30 carry no exit load whatsoever",
            "label": 2,
        },

        # ── Neutral (Label 1) ───────────────────────────────────────────
        {
            "premise": "NSE is the primary stock exchange in India with daily trading turnover exceeding Rs 50,000 crore",
            "hypothesis": "Fund managers must follow Section 45 of SEBI Act",
            "label": 1,
        },
        {
            "premise": "AMFI publishes daily NAV updates for registered mutual funds",
            "hypothesis": "The Reserve Bank of India reduced the repo rate by 25 basis points",
            "label": 1,
        },
    ]


def finetune_nli_model(
    output_dir: str = "backend/app/evaluation/nli_model",
    base_model: str = "bert-base-uncased",
    epochs: int = 3,
):
    """Fine-tune NLI model if torch and transformers are present."""
    try:
        from datasets import Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
        )
    except ImportError:
        logger.warning("transformers or datasets not installed in this environment. Skipping training.")
        return

    logger.info("Initializing fine-tuning pipeline with base model %s", base_model)
    examples = create_nli_training_data()
    dataset = Dataset.from_list(examples)
    split_dataset = dataset.train_test_split(test_size=0.2)

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=3)

    def tokenize_fn(batch):
        return tokenizer(batch["premise"], batch["hypothesis"], truncation=True, max_length=512, padding=True)

    tokenized_train = split_dataset["train"].map(tokenize_fn, batched=True)
    tokenized_eval = split_dataset["test"].map(tokenize_fn, batched=True)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(out_path / "checkpoints"),
        learning_rate=2e-5,
        per_device_train_batch_size=4,
        num_train_epochs=epochs,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=1,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        data_collator=DataCollatorWithPadding(tokenizer),
    )

    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info("✅ Fine-tuned NLI model successfully saved to %s", output_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = create_nli_training_data()
    print(f"Generated {len(data)} AMC compliance NLI training samples.")
