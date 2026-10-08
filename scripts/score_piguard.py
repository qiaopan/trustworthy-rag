"""Score every pool passage with local PIGuard and append to a JSONL cache.

Run with the PIGuard venv (torch/transformers live there, bipia deps do not):
  PYTHONPATH=. .venv/bin/python scripts/run_dev.py --dump-pool-texts outputs/dev/pool_texts.jsonl ...
  PYTHONPATH=. .venv-piguard/bin/python scripts/score_piguard.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--texts", type=Path, default=ROOT / "outputs/dev/pool_texts.jsonl")
    parser.add_argument("--cache", type=Path, default=ROOT / "outputs/dev/cache/piguard.jsonl")
    args = parser.parse_args()
    done = set()
    if args.cache.exists():
        done = {json.loads(line)["text_sha"] for line in args.cache.read_text().splitlines() if line.strip()}
    todo = [json.loads(line)["text"] for line in args.texts.read_text().splitlines() if line.strip()]
    todo = [t for t in dict.fromkeys(todo) if hashlib.sha256(t.encode()).hexdigest() not in done]
    if not todo:
        print("All passages already scored")
        return
    os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
    from src.pigguard import PIGuardRiskScorer
    scorer = PIGuardRiskScorer()
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    with args.cache.open("a") as out:
        for text in todo:
            out.write(json.dumps({"text_sha": hashlib.sha256(text.encode()).hexdigest(), "risk": scorer.score(text),
                                  "model": "leolee99/PIGuard"}) + "\n")
    print(f"Scored {len(todo)} new passages -> {args.cache}")


if __name__ == "__main__":
    main()
