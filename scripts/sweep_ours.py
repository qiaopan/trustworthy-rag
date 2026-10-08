"""Retrieval-only gate / Ours sweep (doc-level retrieval, chunk-level defence).

No generator or judge calls.  Uses cached PIGuard chunk scores; ``--embedder
endpoint`` uses bge-m3 through the cached client (only unseen texts are sent).
Fake-embedder numbers are not reportable.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bipia_emailqa import load_cases, scoring_texts  # noqa: E402
from src.llm_client import CachedEmbedder, JsonlCache  # noqa: E402
from src.rag_pipeline import CachedRiskScorer, FakeRiskScorer, OursConfig, retrieve_docs, select_chunks, selection_summary  # noqa: E402
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
    p.add_argument("--doc-ks", default="3")
    p.add_argument("--risk-modes", default="window,chunk")
    p.add_argument("--no-sweep", action="store_true", help="only B0, B2 and the default Ours config")
    p.add_argument("--b2-threshold", type=float, default=0.5)
    p.add_argument("--alphas", type=floats, default=[1.0])
    p.add_argument("--betas", type=floats, default=[0.4, 0.8, 1.6])
    p.add_argument("--gammas", type=floats, default=[0.0, 0.4])
    p.add_argument("--keeps", type=floats, default=[-0.4, -0.2, 0.0, 0.2])
    p.add_argument("--thresholds", default="none,0.5")
    a = p.parse_args()
    cases = load_cases(a.manifest, include_clean=True)
    scorer = FakeRiskScorer() if a.risk == "fake" else CachedRiskScorer(a.out / "cache/piguard.jsonl")
    if a.risk == "piguard" and (missing := scorer.missing(scoring_texts(cases))):
        sys.exit(f"{len(missing)} chunks lack PIGuard scores; run run_dev.py --dump-pool-texts + scripts/score_piguard.py")
    embedder = HashingEmbedder() if a.embedder == "fake" else CachedEmbedder.from_config(JsonlCache(a.out / "cache/embeddings.jsonl"))
    att = [c for c in cases if c.label == "attack"]
    cln = [c for c in cases if c.label == "clean"]
    thresholds = [None if t == "none" else float(t) for t in a.thresholds.split(",")]
    configs = [("b0", OursConfig()), ("b2", OursConfig())] + [
        ("ours", OursConfig(*v)) for v in itertools.product(a.alphas, a.betas, a.gammas, a.keeps, thresholds)]
    if a.no_sweep:
        configs = [("b0", OursConfig()), ("b2", OursConfig()), ("ours", OursConfig())]
    rows = []
    for k in [int(x) for x in a.doc_ks.split(",")]:
        docs = {c.case_id: retrieve_docs(c, embedder, k) for c in cases}
        for (method, cfg), mode in itertools.product(configs, a.risk_modes.split(",")):
            sel = {c.case_id: selection_summary(c, docs[c.case_id], select_chunks(
                c, docs[c.case_id], scorer, method, cfg, a.b2_threshold, embedder, mode), a.b2_threshold) for c in cases}
            ans = lambda group: [sel[c.case_id]["answer_retained"] for c in group if sel[c.case_id]["answer_possible"]]
            row = {"doc_k": k, "risk": mode, "config": cfg.tag() if method == "ours" else method,
                   "target_recall": frac(sel[c.case_id]["target_retrieved"] for c in att),
                   "attack_in_ctx": frac(sel[c.case_id]["malicious_included"] for c in att),
                   "attack_removed": frac(sel[c.case_id]["attack_removed"] for c in att),
                   "answer_ret_attack": frac(ans(att)), "answer_ret_clean": frac(ans(cln)),
                   "clean_dropped_attack": f"{sum(sel[c.case_id]['clean_chunks_dropped'] for c in att)}/{sum(sel[c.case_id]['clean_chunks_retrieved'] for c in att)}",
                   "clean_dropped_clean": f"{sum(sel[c.case_id]['clean_chunks_dropped'] for c in cln)}/{sum(sel[c.case_id]['clean_chunks_retrieved'] for c in cln)}",
                   "doclevel_b2_drops_target_attack": sum(sel[c.case_id]["doc_b2_drops_target"] for c in att),
                   "doclevel_b2_drops_target_clean": sum(sel[c.case_id]["doc_b2_drops_target"] for c in cln)}
            rows.append(row)
            print("  ".join(f"{key}={v}" for key, v in row.items()), flush=True)
    out = a.out / f"sweep_doc_{a.embedder}_{a.risk}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} rows -> {out}; new_embedding_calls={getattr(embedder, 'calls', 0)}")


if __name__ == "__main__":
    main()
