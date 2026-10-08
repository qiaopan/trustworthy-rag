"""Dev runner: BIPIA EmailQA -> retrieval -> B0/B2/Ours selection -> generator -> judge.

Offline modes (no endpoint traffic): ``--dry-run`` (selection + planned call
counts only) and ``--fake-client`` (deterministic fake generator/judge).  Real
runs read endpoints from the ignored configs/h200_reuse.local.yaml; nothing
from it is printed or written.  All calls are serial and cached under --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bipia_emailqa import build_messages, load_cases, sha  # noqa: E402
from src.judge import ACCURACY_LABELS, ATTACK_LABELS, accuracy_messages, attack_messages, is_abstention, parse_label  # noqa: E402
from src.llm_client import CachedEmbedder, ChatClient, JsonlCache  # noqa: E402
from src.rag_pipeline import (CONTEXT_K, RETRIEVE_K, CachedRiskScorer, FakeRiskScorer, OursConfig, retrieve,
                              risk_filtered_kinds, select, selection_summary)  # noqa: E402
from src.retrieval import HashingEmbedder  # noqa: E402


def fake_generator(messages, model, decoding):
    text = messages[0]["content"]
    return ("FAKE: following injected text" if "ignore" in text.lower() else "FAKE: $0.00"), {"prompt_tokens": len(text) // 4, "completion_tokens": 4}


def fake_judge(messages, model, decoding):
    label = "CORRECT" if "Reference answer" in messages[-1]["content"] else "ATTACK_FAILED"
    return label, {"prompt_tokens": 10, "completion_tokens": 2}


def method_tag(method: str, ours: OursConfig) -> str:
    return ours.tag() if method == "ours" else method


def run(cases, methods, embedder, scorer, generator, judge, ours=OursConfig(), b2_threshold=0.5,
        retrieve_k=RETRIEVE_K, context_k=CONTEXT_K, dry_run=False) -> list[dict]:
    results = []
    for case in cases:
        candidates = retrieve(case, embedder, retrieve_k)
        flagged = risk_filtered_kinds(candidates, scorer, b2_threshold)
        for method in methods:
            rows = select(case, candidates, scorer, method, ours, b2_threshold, context_k)
            texts = [r.passage.text for r in rows]
            messages = build_messages(case.question, texts)
            tag, context_sha = method_tag(method, ours), sha(json.dumps(texts))
            record = {**case.meta(), "method": tag, "selection": selection_summary(rows, case), "context_sha": context_sha,
                      "b2_flagged_kinds": flagged}
            if not dry_run:
                gen = generator.complete(messages, case.case_id, tag, context_sha)
                answer = gen["text"] or ""
                if gen["ok"]:
                    jm = (attack_messages(case.question, case.ideal, case.attack, answer) if case.label == "attack"
                          else accuracy_messages(case.question, case.ideal, answer))
                    jud = judge.complete(jm, case.case_id, f"{tag}:judge", context_sha)
                    labels = ATTACK_LABELS if case.label == "attack" else ACCURACY_LABELS
                    label = parse_label(jud["text"], labels) if jud["ok"] else "ERROR"
                else:  # failed generation: never judged
                    jud = {"ok": False, "cached": False, "latency_s": 0.0, "usage": {}, "retries": 0, "error": None}
                    label = "ERROR"
                record.update(answer=answer, abstained=is_abstention(answer), judge_label=label,
                              gen_ok=gen["ok"], judge_ok=jud["ok"], gen_cached=gen["cached"], judge_cached=jud["cached"],
                              gen_latency_s=gen["latency_s"], judge_latency_s=jud["latency_s"],
                              gen_usage=gen["usage"], judge_usage=jud["usage"],
                              gen_retries=gen["retries"], judge_retries=jud["retries"],
                              errors=[e for e in (gen["error"], jud["error"]) if e])
            results.append(record)
            print(f"{case.case_id} {tag} kinds={record['selection']['kinds']}"
                  + ("" if dry_run else f" judge={record['judge_label']}"), flush=True)
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/emailqa_dev_30.jsonl")
    p.add_argument("--methods", default="b0,b2", help="comma list of b0,b2,b3,ours")
    p.add_argument("--include-clean", action="store_true", help="also run clean (no-injection) copies of each context")
    p.add_argument("--clean-only", action="store_true")
    p.add_argument("--out", type=Path, default=ROOT / "outputs/dev")
    p.add_argument("--embedder", choices=("fake", "endpoint"), default="fake")
    p.add_argument("--risk", choices=("fake", "piguard"), default="piguard")
    p.add_argument("--fake-client", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dump-pool-texts", type=Path, help="write all pool passages for PIGuard scoring and exit")
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--beta", type=float, default=0.8)
    p.add_argument("--gamma", type=float, default=0.4)
    p.add_argument("--ours-threshold", type=float, default=None)
    p.add_argument("--b2-threshold", type=float, default=0.5)
    p.add_argument("--retrieve-k", type=int, default=RETRIEVE_K)
    p.add_argument("--context-k", type=int, default=CONTEXT_K)
    p.add_argument("--pool-mode", choices=("replace", "duplicate"), default="replace")
    a = p.parse_args()

    cases = load_cases(a.manifest, include_clean=a.include_clean or a.clean_only, attacked=not a.clean_only, pool_mode=a.pool_mode)
    if a.dump_pool_texts:
        a.dump_pool_texts.parent.mkdir(parents=True, exist_ok=True)
        texts = dict.fromkeys(pa.text for c in cases for pa in c.pool)
        a.dump_pool_texts.write_text("".join(json.dumps({"text": t}) + "\n" for t in texts))
        print(f"Wrote {len(texts)} unique passages to {a.dump_pool_texts}")
        return
    if not (a.fake_client or a.dry_run) and (a.embedder, a.risk) != ("endpoint", "piguard"):
        sys.exit("Real generator/judge runs require --embedder endpoint --risk piguard")
    cache_dir = a.out / "cache"
    scorer = FakeRiskScorer() if a.risk == "fake" else CachedRiskScorer(cache_dir / "piguard.jsonl")
    if a.risk == "piguard" and (missing := scorer.missing([pa.text for c in cases for pa in c.pool])):
        sys.exit(f"{len(missing)} passages lack PIGuard scores: run --dump-pool-texts then scripts/score_piguard.py")
    embedder = HashingEmbedder() if a.embedder == "fake" else CachedEmbedder.from_config(JsonlCache(cache_dir / "embeddings.jsonl"))
    llm_cache = JsonlCache(cache_dir / ("fake_llm_calls.jsonl" if a.fake_client else "llm_calls.jsonl"))
    if a.fake_client or a.dry_run:
        generator = ChatClient("generator", "fake-generator", llm_cache, fake_generator)
        judge = ChatClient("judge", "fake-judge", llm_cache, fake_judge, max_tokens=8)
    else:
        generator = ChatClient.from_config("generator", llm_cache)
        judge = ChatClient.from_config("judge", llm_cache, max_tokens=8)
    ours = OursConfig(a.alpha, a.beta, a.gamma, a.ours_threshold)
    methods = a.methods.split(",")
    results = run(cases, methods, embedder, scorer, generator, judge, ours, a.b2_threshold, a.retrieve_k, a.context_k, a.dry_run)
    name = "selection_dryrun" if a.dry_run else ("results_fake" if a.fake_client else "results")
    out = a.out / f"{name}_{'-'.join(method_tag(m, ours) for m in methods)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "run-meta", "embedder": a.embedder if a.embedder == "fake" else "bge-m3", "risk": a.risk,
            "generator_model": generator.model, "judge_model": judge.model, "decoding": generator.decoding,
            "retrieve_k": a.retrieve_k, "pool_mode": a.pool_mode, "context_k": a.context_k, "b2_threshold": a.b2_threshold, "ours": vars(ours) | {}}
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [meta, *results]))
    print(f"cases={len(cases)} methods={methods} new_generator_calls={generator.calls} new_judge_calls={judge.calls}"
          f" new_embedding_calls={getattr(embedder, 'calls', 0)} -> {out}")


if __name__ == "__main__":
    main()
