"""Selection-only trade-off analysis (no generator/judge calls; cached PIGuard + embeddings).

Per configuration: attack-text-in-context (attack cases), answer-bearing retention
(answerable attack cases), clean chunks dropped (attack and clean cases).  B2 is
swept over thresholds; Ours and its ablations are located relative to that curve.
Also reports the chunks Ours keeps that B2 drops ("rescued") and their precision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bipia_emailqa import load_cases  # noqa: E402
from src.llm_client import CachedEmbedder, JsonlCache  # noqa: E402
from src.rag_pipeline import CachedRiskScorer, OursConfig, retrieve_docs, select_chunks, selection_summary  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / "outputs/test_main")
    p.add_argument("--attack-manifest", type=Path, default=ROOT / "data/manifests/emailqa_test_main_300.jsonl")
    p.add_argument("--clean-manifest", type=Path, default=ROOT / "data/manifests/emailqa_test_clean_20.jsonl")
    a = p.parse_args()
    cases = load_cases(a.attack_manifest) + load_cases(a.clean_manifest)
    scorer = CachedRiskScorer(a.out / "cache/piguard.jsonl")
    embedder = CachedEmbedder.from_config(JsonlCache(a.out / "cache/embeddings.jsonl"))
    docs = {c.case_id: retrieve_docs(c, embedder, 3) for c in cases}

    def run(method, cfg=OursConfig(), thr=0.5):
        rows = {c.case_id: select_chunks(c, docs[c.case_id], scorer, method, cfg, thr, embedder) for c in cases}
        sel = {c.case_id: selection_summary(c, docs[c.case_id], rows[c.case_id], thr) for c in cases}
        att = [c for c in cases if c.label == "attack"]
        cln = [c for c in cases if c.label == "clean"]
        ans = [c for c in att if sel[c.case_id]["answer_possible"]]
        return rows, {"attack_in_context": sum(sel[c.case_id]["malicious_included"] for c in att),
                      "answer_retained": sum(sel[c.case_id]["answer_retained"] for c in ans), "answerable": len(ans),
                      "clean_dropped_attack": sum(sel[c.case_id]["clean_chunks_dropped"] for c in att),
                      "clean_dropped_clean": sum(sel[c.case_id]["clean_chunks_dropped"] for c in cln)}

    table = []
    for thr in [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999]:
        table.append({"config": f"b2_thr{thr}", **run("b2", thr=thr)[1]})
    b2_rows, _ = run("b2")
    ours_cfgs = {"ours_default(a1,b0.8,g0.4)": OursConfig(),
                 "ours_gamma0": OursConfig(gamma=0.0),
                 "ours_alpha0(risk-only,g0.4)": OursConfig(alpha=0.0),
                 "ours_alpha0_gamma0(=B3)": OursConfig(alpha=0.0, gamma=0.0)}
    for beta in [0.4, 0.6, 1.0, 1.2, 1.6]:
        ours_cfgs[f"ours_beta{beta}"] = OursConfig(beta=beta)
    rescued = None
    for name, cfg in ours_cfgs.items():
        rows, row = run("ours", cfg)
        table.append({"config": name, **row})
        if name.startswith("ours_default"):
            kept = [r for cid in rows for r, b in zip(rows[cid], b2_rows[cid]) if r.kept and not b.kept]
            rescued = {"rescued_chunks": len(kept), "attack": sum(r.passage.kind == "poisoned" for r in kept),
                       "clean": sum(r.passage.kind != "poisoned" for r in kept),
                       "answer_bearing": sum(r.passage.answer_bearing for r in kept)}
            rescued["precision_clean"] = round(rescued["clean"] / max(1, len(kept)), 3)
            dropped = [r for cid in rows for r, b in zip(rows[cid], b2_rows[cid]) if not r.kept and b.kept]
            rescued["ours_drops_b2_keeps"] = {"total": len(dropped), "attack": sum(r.passage.kind == "poisoned" for r in dropped)}
    for r in table:
        print("  ".join(f"{k}={v}" for k, v in r.items()))
    b2 = [r for r in table if r["config"].startswith("b2_")]
    ours = table[[r["config"] for r in table].index("ours_default(a1,b0.8,g0.4)")]
    leak = min(b2, key=lambda r: (abs(r["attack_in_context"] - ours["attack_in_context"]), -r["answer_retained"]))
    ret = min(b2, key=lambda r: (abs(r["answer_retained"] - ours["answer_retained"]), r["attack_in_context"]))
    summary = {"ours": ours, "b2_matched_leakage": leak, "b2_matched_retention": ret, "rescued_vs_b2_thr0.5": rescued,
               "new_embedding_calls": embedder.calls}
    print(json.dumps(summary, indent=1))
    (a.out / "selection_tradeoff.json").write_text(json.dumps({"table": table, **summary}, indent=1) + "\n")


if __name__ == "__main__":
    main()
