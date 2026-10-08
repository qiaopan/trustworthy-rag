"""Generator interface; mock mode keeps smoke tests offline."""
from __future__ import annotations


def build_prompt(query: str, contexts: list[str]) -> str:
    joined = "\n\n".join(f"[Context {i + 1}] {text}" for i, text in enumerate(contexts))
    return f"Answer the user query using only the contexts.\n\n{joined}\n\nUser query: {query}\nAnswer:"


class MockGenerator:
    def generate(self, query: str, contexts: list[str]) -> str:
        return f"MOCK ANSWER: {contexts[0] if contexts else 'ABSTAIN'}"
