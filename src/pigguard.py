"""PIGuard adapter and deterministic test-time injection scoring."""
from __future__ import annotations

import re
from typing import Protocol


class RiskScorer(Protocol):
    def score(self, text: str) -> float: ...


class KeywordRiskScorer:
    """Transparent B1 baseline and offline fallback, not a PIGuard substitute."""
    PATTERN = re.compile(r"ignore (all |previous |prior )?instructions|system prompt|reveal .*secret|jailbreak|do not answer", re.I)

    def score(self, text: str) -> float:
        return 1.0 if self.PATTERN.search(text) else 0.0


class PIGuardRiskScorer:
    def __init__(self, model_name: str = "leolee99/PIGuard", device: int = -1):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, trust_remote_code=True)
        self.classifier = pipeline(
            "text-classification", model=model, tokenizer=tokenizer, device=device, truncation=True, top_k=None
        )

    def score(self, text: str) -> float:
        labels = self.classifier(text)[0]
        for item in labels:
            if "inject" in item["label"].lower() and "not" not in item["label"].lower():
                return float(item["score"])
        # PIGuard label naming can differ by checkpoint; fail visibly rather than silently claiming safety.
        raise ValueError(f"Cannot identify injection label in PIGuard output: {labels}")
