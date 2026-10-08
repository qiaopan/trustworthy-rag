"""Per-case retrieval + method-specific passage selection (no generator involved)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .bipia_emailqa import Case, sha
from .pigguard import KeywordRiskScorer
from .reranker import select_passages
from .retrieval import DenseRetriever, Embedder

RETRIEVE_K = 10
CONTEXT_K = 3


@dataclass(frozen=True)
class OursConfig:
    alpha: float = 1.0
    beta: float = 0.8
    gamma: float = 0.4
    threshold: float | None = None  # optional hard risk cap for Ours

    def tag(self) -> str:
        return f"ours_a{self.alpha:g}_b{self.beta:g}_g{self.gamma:g}_t{self.threshold if self.threshold is not None else 'none'}"


class CachedRiskScorer:
    """PIGuard scores precomputed by scripts/score_piguard.py (run in .venv-piguard)."""

    def __init__(self, path: Path):
        self.scores = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.scores[row["text_sha"]] = row["risk"]

    def missing(self, texts: list[str]) -> list[str]:
        return [t for t in texts if sha(t) not in self.scores]

    def score(self, text: str) -> float:
        try:
            return self.scores[sha(text)]
        except KeyError:
            raise KeyError("PIGuard score missing; run scripts/score_piguard.py first") from None


class FakeRiskScorer(KeywordRiskScorer):
    """Offline stand-in for tests/dry runs only; never report its numbers."""


def retrieve(case: Case, embedder: Embedder, k: int = RETRIEVE_K):
    retriever = DenseRetriever(embedder)
    retriever.index([p.text for p in case.pool], [{"pid": p.pid, "kind": p.kind, "answer_bearing": p.answer_bearing} for p in case.pool])
    return retriever.search(case.question, k=min(k, len(case.pool)))


def select(case: Case, candidates, scorer, method: str, ours: OursConfig = OursConfig(),
           b2_threshold: float = 0.5, k: int = CONTEXT_K):
    return select_passages(case.question, candidates, scorer, "ours" if method.startswith("ours") else method, k,
                           alpha=ours.alpha, beta=ours.beta, gamma=ours.gamma, threshold=b2_threshold,
                           ours_threshold=ours.threshold)


def risk_filtered_kinds(candidates, scorer, threshold: float = 0.5) -> list[str]:
    """Kinds of retrieved candidates a hard risk filter (B2) would drop."""
    return [c.metadata["kind"] for c in candidates if scorer.score(c.text) >= threshold]


def selection_summary(rows, case: Case | None = None) -> dict:
    kinds = [r.passage.metadata["kind"] for r in rows]
    return {"pids": [r.passage.metadata["pid"] for r in rows], "kinds": kinds,
            "risks": [round(r.risk, 6) for r in rows], "relevance": [round(r.passage.relevance, 6) for r in rows],
            "malicious_included": "poisoned" in kinds, "support_retained": "support" in kinds,
            "answer_retained": any(r.passage.metadata["answer_bearing"] for r in rows),
            "answer_possible": bool(case and any(p.answer_bearing for p in case.pool))}
