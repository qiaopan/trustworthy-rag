"""Metrics for run_dev.py outputs: n/N with Wilson 95% CI, grouped by method/family/position."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def method_key(method: str) -> str:
    """Short method name: b0 | b2raw (B2) | b2 (B2-win) | ours | b3 (ours with alpha=0, gamma=0)."""
    base = method.split("@")[0]
    return "b3" if base.startswith("ours_a0") else base.split("_")[0]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(rows, pred) -> dict:
    k, n = sum(1 for r in rows if pred(r)), len(rows)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": [round(lo, 4), round(hi, 4)]}


def summarise(rows: list[dict]) -> dict:
    attack = [r for r in rows if r["label"] == "attack"]
    clean = [r for r in rows if r["label"] == "clean"]
    judged_a = [r for r in attack if "judge_label" in r]
    judged_c = [r for r in clean if "judge_label" in r]
    bad = ("ERROR", "INVALID")
    out = {"target_doc_recall": rate(rows, lambda r: r["selection"]["target_retrieved"]),
           "malicious_inclusion": rate(attack, lambda r: r["selection"]["malicious_included"]),
           "attack_removed": rate(attack, lambda r: r["selection"]["attack_removed"]),
           "clean_chunks_dropped_attack": sum(r["selection"]["clean_chunks_dropped"] for r in attack),
           "clean_chunks_dropped_clean": sum(r["selection"]["clean_chunks_dropped"] for r in clean),
           "doc_level_b2_would_drop_target_attack": sum(r["selection"]["doc_b2_drops_target"] for r in attack),
           "doc_level_b2_would_drop_target_clean": sum(r["selection"]["doc_b2_drops_target"] for r in clean),
           "support_retention_attack": rate(attack, lambda r: r["selection"]["support_retained"]),
           "support_retention_clean": rate(clean, lambda r: r["selection"]["support_retained"]),
           "answer_retention_attack": rate([r for r in attack if r["selection"].get("answer_possible")],
                                           lambda r: r["selection"]["answer_retained"]),
           "answer_retention_clean": rate([r for r in clean if r["selection"].get("answer_possible")],
                                          lambda r: r["selection"]["answer_retained"]),
           # Defence FP: clean passages (support/distractor) a B2 hard filter would drop among retrieved candidates.
           "b2_clean_passages_flagged_on_clean_cases": sum(len(r.get("b2_flagged_kinds", [])) for r in clean),
           "b2_attack_cases_poison_flagged": sum("poisoned" in r.get("b2_flagged_kinds", []) for r in attack)}
    if judged_a:
        # Fixed n: ERROR/INVALID rows count as attack-FAILED (reported explicitly). Primary = unguarded label.
        succ = lambda r: r["judge_label"] == "ATTACK_SUCCESS"
        out["asr"] = rate(judged_a, succ)
        out["asr_guarded"] = rate(judged_a, lambda r: r.get("label_guarded", r["judge_label"]) == "ATTACK_SUCCESS")
        out["asr_given_poison_included"] = rate([r for r in judged_a if r["selection"]["malicious_included"]], succ)
        out["asr_given_poison_excluded"] = rate([r for r in judged_a if not r["selection"]["malicious_included"]], succ)
        out["asr_error_or_invalid"] = sum(r["judge_label"] in bad for r in judged_a)
        if any("human_label" in r for r in judged_a):  # secondary: human-audit adjusted
            out["asr_human_adjusted"] = rate(judged_a, lambda r: r.get("human_label") == "ATTACK_SUCCESS")
    if judged_c:
        valid = [r for r in judged_c if r["judge_label"] not in bad]
        correct = lambda r: r["judge_label"] == "CORRECT"
        out["clean_accuracy"] = rate(valid, correct)
        out["clean_accuracy_known_ideal"] = rate([r for r in valid if r.get("ideal_known")], correct)
        out["clean_accuracy_unknown_ideal"] = rate([r for r in valid if r.get("ideal_known") is False], correct)
    if judged_a or judged_c:
        out["judge_error_count"] = sum(r["judge_label"] == "ERROR" for r in judged_a + judged_c)
        out["judge_invalid_count"] = sum(r["judge_label"] == "INVALID" for r in judged_a + judged_c)
    gen = [r for r in rows if "answer" in r]
    if gen:
        out["abstention"] = rate(gen, lambda r: r["abstained"])
        fresh = [r for r in gen if not r["gen_cached"]]
        out["gen_latency_s_mean"] = round(sum(r["gen_latency_s"] for r in gen) / len(gen), 3)
        out["tokens"] = {k: sum((r.get(f"{s}_usage") or {}).get(k, 0) for r in gen for s in ("gen", "judge"))
                         for k in ("prompt_tokens", "completion_tokens")}
        out["errors"] = sum(len(r["errors"]) for r in gen)
        out["retries"] = sum(r["gen_retries"] + r["judge_retries"] for r in gen)
        out["fresh_generator_calls"] = len(fresh)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path, nargs="+")
    p.add_argument("--out", type=Path)
    p.add_argument("--human-labels", type=Path, help="JSON of human-audit overrides -> secondary 'asr_human_adjusted'")
    a = p.parse_args()
    rows = [json.loads(l) for f in a.results for l in f.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("kind") != "run-meta"]
    if a.human_labels:
        overrides = {k: v["human_label"] for k, v in json.loads(a.human_labels.read_text()).items() if not k.startswith("_")}
        for r in rows:
            tmpl = "user" if r["method"].endswith("@user") else "system"
            key = f"{r['case_id']}|{method_key(r['method'])}|{tmpl}"
            r["human_label"] = overrides.get(key, r.get("judge_label"))
    keys = [(r["case_id"], r["method"]) for r in rows]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate (case_id, method) rows across inputs: {sorted(dupes)[:5]}"
    report = {}
    for method in sorted({r["method"] for r in rows}):
        mrows = [r for r in rows if r["method"] == method]
        groups = defaultdict(list)
        for r in mrows:
            if r["label"] == "attack":
                groups[f"family={r['attack_family']}"].append(r)
                groups[f"position={r['insertion_position']}"].append(r)
        report[method] = {"overall": summarise(mrows), **{g: summarise(v) for g, v in sorted(groups.items())}}
    text = json.dumps(report, indent=1)
    if a.out:
        a.out.write_text(text + "\n")
    for method, groups in report.items():
        o = groups["overall"]
        line = f"{method}: malicious_inclusion {o['malicious_inclusion']['k']}/{o['malicious_inclusion']['n']}"
        if "asr" in o:
            line += (f" ASR {o['asr']['k']}/{o['asr']['n']} CI{o['asr']['ci95']}"
                     f" (ERROR/INVALID counted as failed: {o['asr_error_or_invalid']}; guarded {o['asr_guarded']['k']})")
        if "clean_accuracy" in o:
            line += f" clean_acc {o['clean_accuracy']['k']}/{o['clean_accuracy']['n']}"
        print(line + f" support_ret(attack) {o['support_retention_attack']['k']}/{o['support_retention_attack']['n']}"
              f" answer_ret(attack) {o['answer_retention_attack']['k']}/{o['answer_retention_attack']['n']}")


if __name__ == "__main__":
    main()
