"""Retrieval-only gate / Ours sweep: no generator or judge calls.

For each context_k and config reports poisoned-passage inclusion, support and
answer-bearing retention (attack and clean cases), plus how many attack cases a
B2 hard filter flags and how many clean passages it would drop.  Uses cached
PIGuard scores; ``--embedder endpoint`` uses bge-m3 through the cached client
(only unseen texts are sent).  Fake-embedder numbers are not reportable.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bipia_emailqa import load_cases  # noqa: E402
from src.llm_client import CachedEmbedder, JsonlCache  # noqa: E402
from src.rag_pipeline import (RETRIEVE_K, CachedRiskScorer, FakeRiskScorer, OursConfig, retrieve,  # noqa: E402
                              risk_filtered_kinds, select, selection_summary)
from src.retrieval import HashingEmbedder  # noqa: E402


def floats(s: str) -> list[float]:
    return [float(x) for x in s.split(",")]


def frac(flags) -> str:
    flags = list(flags)
    return f"{sum(flags)}/{len(flags)}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/emailqa_dev_30.jsonl")
    p.add_argument("--out", type=Path, default=ROOT / "outputs/dev")
    p.add_argument("--embedder", choices=("fake", "endpoint"), default="fake")
    p.add_argument("--risk", choices=("fake", "piguard"), default="piguard")
    p.add_argument("--pool-mode", choices=("replace", "duplicate"), default="replace")
    p.add_argument("--context-ks", default="3", help="comma list, e.g. 3,4,5")
    p.add_argument("--retrieve-k", type=int, default=RETRIEVE_K)
    p.add_argument("--b2-threshold", type=float, default=0.5)
    p.add_argument("--alphas", type=floats, default=[1.0])
    p.add_argument("--betas", type=floats, default=[0.2, 0.4, 0.8, 1.6, 3.2])
    p.add_argument("--gammas", type=floats, default=[0.0, 0.2, 0.4, 0.8])
    p.add_argument("--thresholds", default="none,0.9,0.5")
    a = p.parse_args()
    cases = load_cases(a.manifest, include_clean=True, pool_mode=a.pool_mode)
    scorer = FakeRiskScorer() if a.risk == "fake" else CachedRiskScorer(a.out / "cache/piguard.jsonl")
    if a.risk == "piguard" and (missing := scorer.missing([x.text for c in cases for x in c.pool])):
        sys.exit(f"{len(missing)} passages lack PIGuard scores; run --dump-pool-texts + scripts/score_piguard.py")
    embedder = HashingEmbedder() if a.embedder == "fake" else CachedEmbedder.from_config(JsonlCache(a.out / "cache/embeddings.jsonl"))
    candidates = {c.case_id: retrieve(c, embedder, a.retrieve_k) for c in cases}
    att = [c for c in cases if c.label == "attack"]
    cln = [c for c in cases if c.label == "clean"]
    flagged = {c.case_id: risk_filtered_kinds(candidates[c.case_id], scorer, a.b2_threshold) for c in cases}
    print(f"retrieval: poisoned in top-{a.retrieve_k} {frac('poisoned' in [x.metadata['kind'] for x in candidates[c.case_id]] for c in att)}; "
          f"B2 flags poison in {frac('poisoned' in flagged[c.case_id] for c in att)} attack cases; "
          f"clean passages B2 drops: attack cases {sum(k != 'poisoned' for c in att for k in flagged[c.case_id])}, "
          f"clean cases {sum(len(flagged[c.case_id]) for c in cln)}")
    thresholds = [None if t == "none" else float(t) for t in a.thresholds.split(",")]
    configs = [("b0", OursConfig()), ("b2", OursConfig())] + [
        ("ours", OursConfig(*v)) for v in itertools.product(a.alphas, a.betas, a.gammas, thresholds)]
    rows = []
    for k in [int(x) for x in a.context_ks.split(",")]:
        for method, cfg in configs:
            sel = {c.case_id: selection_summary(select(c, candidates[c.case_id], scorer, method, cfg, a.b2_threshold, k), c)
                   for c in cases}
            ans = lambda group: [sel[c.case_id]["answer_retained"] for c in group if sel[c.case_id]["answer_possible"]]
            row = {"k": k, "config": cfg.tag() if method == "ours" else method,
                   "poison_inclusion": frac(sel[c.case_id]["malicious_included"] for c in att),
                   "support_ret_attack": frac(sel[c.case_id]["support_retained"] for c in att),
                   "answer_ret_attack": frac(ans(att)),
                   "support_ret_clean": frac(sel[c.case_id]["support_retained"] for c in cln),
                   "answer_ret_clean": frac(ans(cln))}
            rows.append(row)
            print("  ".join(f"{key}={v}" for key, v in row.items()))
    out = a.out / f"sweep_{a.embedder}_{a.risk}_{a.pool_mode}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} rows -> {out}; new_embedding_calls={getattr(embedder, 'calls', 0)}")


if __name__ == "__main__":
    main()
