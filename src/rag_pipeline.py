"""Document-level retrieval + sentence-level (chunk) defences inside retrieved docs.

No generator is involved here.  Chunk risk is PIGuard on a window (previous +
chunk + next chunk of the same email) by default.  B0 passes retrieved docs unchanged; B2 drops
chunks with PIGuard risk >= threshold; Ours keeps a chunk when
``alpha*rel - beta*risk - gamma*conflict >= keep`` (rel = cosine(question, chunk),
conflict = reranker.context_conflict), optionally with a hard risk cap.
Naming (pre-registered 2026-10-09): method "b2raw" = B2 (per-chunk PIGuard risk >= 0.5);
method "b2" with window risk = B2-win (our window scoring added to B2, an ablation).  Kept
chunks stay in document order; documents stay in retrieval-rank order.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bipia_emailqa import Case, Doc, Passage, risk_windows, sha
from .pigguard import KeywordRiskScorer
from .reranker import context_conflict
from .retrieval import Embedder

DOC_K = 3
RISK_MODE = "window"  # PIGuard on prev+chunk+next; "chunk" = raw per-chunk score


@dataclass(frozen=True)
class OursConfig:
    alpha: float = 1.0
    beta: float = 0.8
    gamma: float = 0.4
    keep: float = -0.2  # keep chunk iff score >= keep
    threshold: float | None = None  # optional hard risk cap

    def tag(self) -> str:
        cap = self.threshold if self.threshold is not None else "none"
        return f"ours_a{self.alpha:g}_b{self.beta:g}_g{self.gamma:g}_k{self.keep:g}_t{cap}"


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


def retrieve_docs(case: Case, embedder: Embedder, k: int = DOC_K) -> list[tuple[Doc, float]]:
    vecs = embedder.encode([d.text for d in case.docs])
    q = embedder.encode([case.question])[0]
    scores = vecs @ q
    return [(case.docs[i], float(scores[i])) for i in np.argsort(-scores, kind="stable")[:k]]


@dataclass(frozen=True)
class ChunkRow:
    passage: Passage
    doc_id: str
    risk: float
    score: float | None
    kept: bool


def select_chunks(case: Case, docs: list[tuple[Doc, float]], scorer, method: str, ours: OursConfig = OursConfig(),
                  b2_threshold: float = 0.5, embedder: Embedder | None = None, risk_mode: str = RISK_MODE) -> list[ChunkRow]:
    """All chunks of the retrieved docs, with a kept flag per method (doc order preserved).

    Chunk risk = PIGuard score of the chunk's window (``risk_mode='window'``) or of the chunk alone."""
    chunks = [(doc.did, c) for doc, _ in docs for c in doc.chunks]
    if method == "b2raw":  # original PIGuard usage: each chunk scored on its own (reported as "B2")
        method, risk_mode = "b2", "chunk"
    elif method == "b3":  # risk-only ablation: retain the configured risk rule, no relevance/conflict terms
        method = "ours"
        ours = OursConfig(alpha=0.0, beta=ours.beta, gamma=0.0, keep=ours.keep, threshold=ours.threshold)
    if risk_mode == "window":
        risk_inputs = [w for doc, _ in docs for w in risk_windows(doc)]
    elif risk_mode == "chunk":
        risk_inputs = [c.text for _, c in chunks]
    else:
        raise ValueError(risk_mode)
    rel = None
    if method == "ours":
        q = embedder.encode([case.question])[0]
        rel = embedder.encode([c.text for _, c in chunks]) @ q if chunks else []
    rows = []
    for i, (did, c) in enumerate(chunks):
        risk, score = scorer.score(risk_inputs[i]), None
        if method == "b0":
            kept = True
        elif method == "b2":
            kept = risk < b2_threshold
        elif method == "ours":
            score = ours.alpha * float(rel[i]) - ours.beta * risk - ours.gamma * context_conflict(case.question, c.text)
            kept = score >= ours.keep and (ours.threshold is None or risk < ours.threshold)
        else:
            raise ValueError(f"Unknown method: {method}")
        rows.append(ChunkRow(c, did, risk, score, kept))
    return rows


def context_texts(docs: list[tuple[Doc, float]], rows: list[ChunkRow]) -> list[str]:
    """Surviving text per retrieved doc (docs with nothing kept are omitted)."""
    out = []
    for doc, _ in docs:
        kept = [r.passage.text for r in rows if r.doc_id == doc.did and r.kept]
        if kept:
            out.append("\n".join(kept))
    return out


def selection_summary(case: Case, docs: list[tuple[Doc, float]], rows: list[ChunkRow], b2_threshold: float = 0.5) -> dict:
    kept = [r for r in rows if r.kept]
    target = next(d for d in case.docs if d.kind == "target")
    retrieved = [d.did for d, _ in docs]
    attack_rows = [r for r in rows if r.passage.kind == "poisoned"]
    return {"doc_ids": retrieved, "doc_scores": [round(s, 6) for _, s in docs],
            "target_retrieved": target.did in retrieved,
            "malicious_included": any(r.passage.kind == "poisoned" for r in kept),  # attack text in context
            "attack_removed": bool(attack_rows) and not any(r.kept for r in attack_rows),
            "support_retained": any(r.passage.kind == "support" for r in kept),
            "answer_retained": any(r.passage.answer_bearing for r in kept),
            "answer_possible": any(c.answer_bearing for c in target.chunks),
            "clean_chunks_dropped": sum(not r.kept and r.passage.kind != "poisoned" for r in rows),
            "clean_chunks_retrieved": sum(r.passage.kind != "poisoned" for r in rows),
            # metric only: a doc-level B2 would drop the whole target doc if any chunk is flagged
            "doc_b2_drops_target": target.did in retrieved and any(
                r.risk >= b2_threshold for r in rows if r.doc_id == target.did),
            "kept_pids": [r.passage.pid for r in kept]}
