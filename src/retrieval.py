"""Dense retrieval with a lightweight deterministic fallback for tests."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    """Offline test embedder; do not use for reported experimental results."""
    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"\w+", text.lower()):
                index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimension
                vectors[row, index] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, device: str | None = None):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name, device=device)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


@dataclass(frozen=True)
class RetrievedPassage:
    text: str
    relevance: float
    metadata: dict


class DenseRetriever:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self._texts: list[str] = []
        self._metadata: list[dict] = []
        self._embeddings: np.ndarray | None = None

    def index(self, passages: list[str], metadata: list[dict] | None = None) -> None:
        self._texts = passages
        self._metadata = metadata or [{} for _ in passages]
        self._embeddings = self.embedder.encode(passages)

    def search(self, query: str, k: int) -> list[RetrievedPassage]:
        if self._embeddings is None:
            raise RuntimeError("Index passages before searching")
        query_vector = self.embedder.encode([query])[0]
        scores = self._embeddings @ query_vector
        indices = np.argsort(-scores)[:k]
        return [RetrievedPassage(self._texts[i], float(scores[i]), self._metadata[i]) for i in indices]
