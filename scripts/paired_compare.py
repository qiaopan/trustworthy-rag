"""Paired method comparisons on identical cases: exact McNemar test (two-sided).

For a binary outcome per case, b = cases where method A=1 and B=0, c = A=0 and B=1;
p = two-sided exact binomial test of min(b, c) with n = b + c, p = 0.5.
"""
from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path

OUTCOMES = {
    "asr": ("attack", lambda r: r["judge_label"] == "ATTACK_SUCCESS"),
    "attack_in_context": ("attack", lambda r: r["selection"]["malicious_included"]),
    "answer_retained": ("attack_answerable", lambda r: r["selection"]["answer_retained"]),
    "abstention_attack": ("attack", lambda r: r["abstained"]),
    "clean_correct_known": ("clean_known", lambda r: r["judge_label"] == "CORRECT"),
    "clean_correct_unknown": ("clean_unknown", lambda r: r["judge_label"] == "CORRECT"),
}


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def subset(rows, name):
    if name == "attack":
        return [r for r in rows if r["label"] == "attack"]
    if name == "attack_answerable":
        return [r for r in rows if r["label"] == "attack" and r["selection"].get("answer_possible")]
    return [r for r in rows if r["label"] == "clean" and r.get("ideal_known") == (name == "clean_known")]


def compare(rows, a: str, b: str) -> dict:
    by = {(r["case_id"], r["method"]): r for r in rows}
    out = {}
    for name, (sub, fn) in OUTCOMES.items():
        ids = sorted({r["case_id"] for r in subset(rows, sub) if r["method"] == a} &
                     {r["case_id"] for r in subset(rows, sub) if r["method"] == b})
        pa = [fn(by[(i, a)]) for i in ids]
        pb = [fn(by[(i, b)]) for i in ids]
        b_ = sum(x and not y for x, y in zip(pa, pb))
        c_ = sum(y and not x for x, y in zip(pa, pb))
        out[name] = {"n": len(ids), a: sum(pa), b: sum(pb), f"{a}_only": b_, f"{b}_only": c_,
                     "p_mcnemar_exact": round(mcnemar_exact(b_, c_), 4)}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path, nargs="+")
    p.add_argument("--pairs", default="ours:b2,ours:b0,b2:b0")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    rows = [json.loads(l) for f in a.results for l in f.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if "case_id" in r]
    methods = {r["method"] for r in rows}
    alias = lambda m: next((x for x in methods if x == m or x.startswith(m + "_")), m)
    report = {f"{x} vs {y}": compare(rows, alias(x), alias(y)) for x, y in (s.split(":") for s in a.pairs.split(","))}
    if a.out:
        a.out.write_text(json.dumps(report, indent=1) + "\n")
    for pair, res in report.items():
        print(pair)
        for name, v in res.items():
            print("  ", name, v)


if __name__ == "__main__":
    main()
