"""Defense variants used in the B0--B3 and proposed-method experiment matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .pigguard import RiskScorer
from .retrieval import RetrievedPassage


@dataclass(frozen=True)
class ScoredPassage:
    passage: RetrievedPassage
    risk: float
    conflict: float
    final_score: float


def context_conflict(query: str, passage: str) -> float:
    """Instruction-like content is suspicious when the user query is informational."""
    query_is_instruction = bool(re.search(r"^(write|summari[sz]e|explain|what|who|when|where|how)\b", query, re.I))
    passage_is_instruction = bool(re.search(r"ignore|instruction|system prompt|assistant|instead|must", passage, re.I))
    return float(query_is_instruction and passage_is_instruction)


def select_passages(query: str, candidates: list[RetrievedPassage], scorer: RiskScorer, method: str, k: int,
                    alpha: float = 1.0, beta: float = 0.8, gamma: float = 0.4, threshold: float = 0.5) -> list[ScoredPassage]:
    rows = []
    for candidate in candidates:
        risk = scorer.score(candidate.text)
        conflict = context_conflict(query, candidate.text)
        if method == "b0":
            final = candidate.relevance
        elif method == "b1":
            final = candidate.relevance if risk == 0 else float("-inf")
        elif method == "b2":
            final = candidate.relevance if risk < threshold else float("-inf")
        elif method == "b3":
            final = -risk
        elif method == "ours":
            final = alpha * candidate.relevance - beta * risk - gamma * conflict
        else:
            raise ValueError(f"Unknown method: {method}")
        rows.append(ScoredPassage(candidate, risk, conflict, final))
    return sorted((row for row in rows if row.final_score != float("-inf")), key=lambda row: row.final_score, reverse=True)[:k]
