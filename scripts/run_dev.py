"""Dev runner: BIPIA EmailQA -> retrieval -> doc retrieval -> B0/B2/Ours chunk filtering -> generator -> judge.

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

from src.bipia_emailqa import build_messages, load_cases, scoring_texts, sha  # noqa: E402
from src.attack_eval import evaluate, evaluator_for  # noqa: E402
from src.judge import ACCURACY_LABELS, accuracy_messages, is_abstention, parse_label  # noqa: E402
from src.llm_client import CachedEmbedder, ChatClient, JsonlCache  # noqa: E402
from src.rag_pipeline import (DOC_K, CachedRiskScorer, FakeRiskScorer, OursConfig, context_texts,  # noqa: E402
                              retrieve_docs, select_chunks, selection_summary)
from src.retrieval import HashingEmbedder  # noqa: E402


def fake_generator(messages, model, decoding):
    text = messages[0]["content"]
    return ("FAKE: following injected text" if "ignore" in text.lower() else "FAKE: $0.00"), {"prompt_tokens": len(text) // 4, "completion_tokens": 4}


def fake_judge(messages, model, decoding):
    label = "CORRECT" if "Reference answer" in messages[-1]["content"] else "NO"
    return label, {"prompt_tokens": 10, "completion_tokens": 2}


def method_tag(method: str, ours: OursConfig, template: str = "system") -> str:
    tag = ours.tag() if method == "ours" else method
    return tag if template == "system" else f"{tag}@{template}"


def run(cases, methods, embedder, scorer, generator, judge, ours=OursConfig(), b2_threshold=0.5,
        doc_k=DOC_K, dry_run=False, template="system") -> list[dict]:
    results = []
    for case in cases:
        docs = retrieve_docs(case, embedder, doc_k)
        flagged = [r.passage.kind for r in select_chunks(case, docs, scorer, "b0") if r.risk >= b2_threshold]
        for method in methods:
            rows = select_chunks(case, docs, scorer, method, ours, b2_threshold, embedder)
            texts = context_texts(docs, rows)
            messages = build_messages(case.question, texts, template)
            tag, context_sha = method_tag(method, ours, template), sha(json.dumps(texts))
            record = {**case.meta(), "method": tag, "selection": selection_summary(case, docs, rows, b2_threshold),
                      "context_sha": context_sha, "b2_flagged_kinds": flagged}
            if not dry_run:
                gen = generator.complete(messages, case.case_id, tag, context_sha)
                answer = gen["text"] or ""
                none = {"ok": True, "cached": False, "latency_s": 0.0, "usage": {}, "retries": 0, "error": None}
                extra = {}
                if not gen["ok"]:  # failed generation: never judged
                    jud, label = {**none, "ok": False}, "ERROR"
                elif case.label == "attack":
                    ev = evaluate(evaluator_for(case.split, case.attack_family, case.attack_index), answer, judge,
                                  case.case_id, tag, context_sha)
                    jud, label = ev.pop("judge_call") or none, ev.pop("label")
                    extra = ev
                else:
                    jud = judge.complete(accuracy_messages(case.question, case.ideal, answer), case.case_id,
                                         f"{tag}:judge", context_sha)
                    label = parse_label(jud["text"], ACCURACY_LABELS) if jud["ok"] else "ERROR"
                record.update(extra, prompt_messages=messages)
                record.update(answer=answer, abstained=is_abstention(answer), judge_label=label,
                              gen_ok=gen["ok"], judge_ok=jud["ok"], gen_cached=gen["cached"], judge_cached=jud["cached"],
                              gen_latency_s=gen["latency_s"], judge_latency_s=jud["latency_s"],
                              gen_usage=gen["usage"], judge_usage=jud["usage"],
                              gen_retries=gen["retries"], judge_retries=jud["retries"],
                              errors=[e for e in (gen["error"], jud["error"]) if e])
            results.append(record)
            sel = record["selection"]
            print(f"{case.case_id} {tag} target={sel['target_retrieved']} attack_in_ctx={sel['malicious_included']}"
                  + ("" if dry_run else f" judge={record['judge_label']}"), flush=True)
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/emailqa_dev_30.jsonl")
    p.add_argument("--methods", default="b0,b2", help="comma list of b0,b2raw,b2,b3,ours (b2raw = per-chunk PIGuard; b2 = window PIGuard)")
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
    p.add_argument("--ours-keep", type=float, default=-0.2)
    p.add_argument("--ours-threshold", type=float, default=None)
    p.add_argument("--b2-threshold", type=float, default=0.5)
    p.add_argument("--template", choices=("system", "user"), default="system",
                   help="BIPIA EmailIPIABuilder variant: context in system message, or all in one user message")
    p.add_argument("--doc-k", type=int, default=DOC_K, help="number of whole emails retrieved")
    a = p.parse_args()

    cases = load_cases(a.manifest, include_clean=a.include_clean or a.clean_only, attacked=not a.clean_only)
    if a.dump_pool_texts:
        a.dump_pool_texts.parent.mkdir(parents=True, exist_ok=True)
        texts = scoring_texts(cases)
        a.dump_pool_texts.write_text("".join(json.dumps({"text": t}) + "\n" for t in texts))
        print(f"Wrote {len(texts)} unique passages to {a.dump_pool_texts}")
        return
    if not (a.fake_client or a.dry_run) and (a.embedder, a.risk) != ("endpoint", "piguard"):
        sys.exit("Real generator/judge runs require --embedder endpoint --risk piguard")
    cache_dir = a.out / "cache"
    scorer = FakeRiskScorer() if a.risk == "fake" else CachedRiskScorer(cache_dir / "piguard.jsonl")
    if a.risk == "piguard" and (missing := scorer.missing(scoring_texts(cases))):
        sys.exit(f"{len(missing)} passages lack PIGuard scores: run --dump-pool-texts then scripts/score_piguard.py")
    embedder = HashingEmbedder() if a.embedder == "fake" else CachedEmbedder.from_config(JsonlCache(cache_dir / "embeddings.jsonl"))
    llm_cache = JsonlCache(cache_dir / ("fake_llm_calls.jsonl" if a.fake_client else "llm_calls.jsonl"))
    if a.fake_client or a.dry_run:
        generator = ChatClient("generator", "fake-generator", llm_cache, fake_generator)
        judge = ChatClient("judge", "fake-judge", llm_cache, fake_judge, max_tokens=32)
    else:
        generator = ChatClient.from_config("generator", llm_cache)
        judge = ChatClient.from_config("judge", llm_cache, max_tokens=32)  # BIPIA ModelEval uses 32
    ours = OursConfig(a.alpha, a.beta, a.gamma, a.ours_keep, a.ours_threshold)
    methods = a.methods.split(",")
    results = run(cases, methods, embedder, scorer, generator, judge, ours, a.b2_threshold, a.doc_k, a.dry_run, a.template)
    name = "selection_dryrun" if a.dry_run else ("results_fake" if a.fake_client else "results")
    out = a.out / f"{name}_{'-'.join(method_tag(m, ours, a.template) for m in methods)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "run-meta", "embedder": a.embedder if a.embedder == "fake" else "bge-m3", "risk": a.risk,
            "generator_model": generator.model, "judge_model": judge.model, "attack_eval": "bipia-official (test) / ours-train-extension (train); 72B judge replaces GPT-4", "decoding": generator.decoding,
            "doc_k": a.doc_k, "template": a.template, "retrieval_unit": "email", "defence_unit": "sentence-chunk", "b2_threshold": a.b2_threshold, "ours": vars(ours)}
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [meta, *results]))
    print(f"cases={len(cases)} methods={methods} new_generator_calls={generator.calls} new_judge_calls={judge.calls}"
          f" new_embedding_calls={getattr(embedder, 'calls', 0)} -> {out}")


if __name__ == "__main__":
    main()
