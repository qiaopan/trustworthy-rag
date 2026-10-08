"""Serial, cached OpenAI-compatible clients for the reused H200 services.

Endpoints and API keys are read programmatically from the ignored
``configs/h200_reuse.local.yaml``; they are never printed, logged, or written to
any output.  Every request goes through one process-wide lock (concurrency 1).
Results are cached in an append-only JSONL file keyed by a hash of the case,
method, selected-context hash, prompt hash, model name, and decoding config, so
an interrupted run resumes without repeating successful calls.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .bipia_emailqa import sha

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = ROOT / "configs/h200_reuse.local.yaml"
SERVICE_KEYS = {"generator": "generator_qwen32b", "judge": "judge_qwen72b_awq", "embedding": "embedder_bge_m3"}
REQUEST_LOCK = threading.Lock()  # global: at most one in-flight request to any endpoint


def stable_hash(obj: Any) -> str:
    return sha(json.dumps(obj, sort_keys=True, ensure_ascii=False))


class JsonlCache:
    """Append-only cache; only successful entries are served as hits."""

    def __init__(self, path: Path):
        self.path = path
        self.hits: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("ok"):
                        self.hits[row["key"]] = row

    def get(self, key: str) -> dict | None:
        return self.hits.get(key)

    def append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if row.get("ok"):
            self.hits[row["key"]] = row


def load_service(role: str, config_path: Path = LOCAL_CONFIG) -> tuple[dict, dict]:
    import yaml
    config = yaml.safe_load(config_path.read_text())
    return config["services"][SERVICE_KEYS[role]], config.get("runtime", {})


def _with_retries(call: Callable[[], Any], max_retries: int, backoff: float) -> tuple[Any, int, str | None]:
    error = None
    for attempt in range(max_retries + 1):
        try:
            with REQUEST_LOCK:
                return call(), attempt, None
        except Exception as exc:  # noqa: BLE001 - record and retry any transport/server error
            error = f"{type(exc).__name__}: {re.sub(r'https?://\S+', '<url>', str(exc))[:200]}"
            if attempt < max_retries:
                time.sleep(backoff * 2 ** attempt)
    return None, max_retries, error


class ChatClient:
    """Chat completion with temperature 0, bounded retry, and caching.

    ``transport(messages, model, decoding) -> (text, usage_dict)`` is injectable
    so tests can use a fake without any network access.
    """

    def __init__(self, role: str, model: str, cache: JsonlCache, transport: Callable | None = None,
                 max_tokens: int = 256, max_retries: int = 2, backoff: float = 2.0, timeout: float = 120.0):
        self.role, self.model, self.cache, self.transport = role, model, cache, transport
        self.decoding = {"temperature": 0, "max_tokens": max_tokens}
        self.max_retries, self.backoff, self.timeout = max_retries, backoff, timeout
        self.calls = 0

    @classmethod
    def from_config(cls, role: str, cache: JsonlCache, config_path: Path = LOCAL_CONFIG, **kw) -> "ChatClient":
        from openai import OpenAI
        service, runtime = load_service(role, config_path)
        if int(runtime.get("request_concurrency", 1)) != 1:
            raise ValueError("request_concurrency must be 1")
        client = OpenAI(base_url=service["base_url"], api_key=service.get("api_key", "EMPTY"),
                        timeout=kw.get("timeout", 120.0), max_retries=0)

        def transport(messages, model, decoding):
            response = client.chat.completions.create(model=model, messages=messages, **decoding)
            usage = response.usage.model_dump() if response.usage else {}
            return response.choices[0].message.content or "", usage

        kw.setdefault("max_retries", int(runtime.get("max_retries", 2)))
        return cls(role, service["model"], cache, transport, **kw)

    def complete(self, messages: list[dict], case_id: str, method: str, context_sha: str) -> dict:
        prompt_sha = stable_hash(messages)
        key = stable_hash({"case_id": case_id, "method": method, "context_sha": context_sha,
                           "prompt_sha": prompt_sha, "model": self.model, "decoding": self.decoding})
        if (hit := self.cache.get(key)) is not None:
            return {**hit, "cached": True}
        start = time.monotonic()
        result, retries, error = _with_retries(lambda: self.transport(messages, self.model, self.decoding),
                                               self.max_retries, self.backoff)
        self.calls += 1
        text, usage = result if result is not None else (None, {})
        row = {"key": key, "ok": error is None, "role": self.role, "model": self.model, "case_id": case_id,
               "method": method, "context_sha": context_sha, "prompt_sha": prompt_sha, "decoding": self.decoding,
               "text": text, "usage": usage, "latency_s": round(time.monotonic() - start, 3),
               "retries": retries, "error": error, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.cache.append(row)
        return {**row, "cached": False}


class CachedEmbedder:
    """``Embedder`` protocol wrapper: per-text cache around a batch encode function."""

    def __init__(self, model: str, cache: JsonlCache, encode_fn: Callable[[list[str]], list[list[float]]],
                 max_retries: int = 2, backoff: float = 2.0):
        self.model, self.cache, self.encode_fn = model, cache, encode_fn
        self.max_retries, self.backoff, self.calls = max_retries, backoff, 0

    @classmethod
    def from_config(cls, cache: JsonlCache, config_path: Path = LOCAL_CONFIG) -> "CachedEmbedder":
        from openai import OpenAI
        service, runtime = load_service("embedding", config_path)
        client = OpenAI(base_url=service["base_url"], api_key=service.get("api_key", "EMPTY"), timeout=120.0, max_retries=0)

        def encode(texts):
            return [item.embedding for item in client.embeddings.create(model=service["model"], input=texts).data]

        return cls(service["model"], cache, encode, int(runtime.get("max_retries", 2)))

    def encode(self, texts: list[str]) -> np.ndarray:
        keys = [stable_hash({"model": self.model, "text_sha": sha(t)}) for t in texts]
        missing = [t for t, k in zip(texts, keys) if self.cache.get(k) is None]
        for t in dict.fromkeys(missing):  # one request per unseen text keeps payloads small
            start = time.monotonic()
            result, retries, error = _with_retries(lambda: self.encode_fn([t]), self.max_retries, self.backoff)
            self.calls += 1
            self.cache.append({"key": stable_hash({"model": self.model, "text_sha": sha(t)}), "ok": error is None,
                               "role": "embedding", "model": self.model, "text_sha": sha(t),
                               "vector": result[0] if result else None, "latency_s": round(time.monotonic() - start, 3),
                               "retries": retries, "error": error})
            if error:
                raise RuntimeError(f"embedding failed after retries: {error}")
        vectors = np.array([self.cache.get(k)["vector"] for k in keys], dtype=np.float32)
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
