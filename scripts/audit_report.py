"""Human-audit sheet for attack results (analysis only, no model calls).

Writes judge UNKNOWN counts per method/family, every ATTACK_SUCCESS row, and a
seeded sample of judge-UNKNOWN rows (answer excerpt + injected instruction).
Official labels are never changed; audit notes are separate annotations.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bipia_emailqa import load_cases  # noqa: E402

HUMAN = json.loads((ROOT / "data/human_audit_labels.json").read_text())


def method_key(method: str) -> str:
    """Short method name: b0 | b2raw (B2) | b2 (B2-win) | ours | b3 (ours with alpha=0, gamma=0)."""
    base = method.split("@")[0]
    return "b3" if base.startswith("ours_a0") else base.split("_")[0]


def human(case_id: str, method: str) -> tuple[str, str]:
    tmpl = "user" if method.endswith("@user") else "system"
    entry = HUMAN.get(f"{case_id}|{method_key(method)}|{tmpl}")
    return (entry["human_label"], entry["reason"]) if entry else ("ATTACK_SUCCESS (agrees)", "")


def cell(text: str, n: int = 300) -> str:
    return text[:n].replace("|", "\\|").replace("\n", " ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results", type=Path)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/emailqa_test_main_300.jsonl")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--unknown-sample", type=int, default=15)
    a = p.parse_args()
    attacks = {c.case_id: c.attack for c in load_cases(a.manifest)}
    rows = [r for r in map(json.loads, a.results.read_text().splitlines()) if "case_id" in r and r["label"] == "attack"]
    short = lambda m: m.split("_")[0]
    unk = [r for r in rows if (r.get("judge_raw") or "").strip().upper().startswith("UNKNOWN")]
    lines = ["# Human audit: main Test attack results", "",
             "Official labels are unchanged; notes are human-audit annotations only.", "",
             "## Judge UNKNOWN replies (counted as ATTACK_FAILED by BIPIA's rule)", "",
             "| method | UNKNOWN | model-judged rows |", "|---|---|---|"]
    for m in sorted({r["method"] for r in rows}):
        lines.append(f"| {short(m)} | {sum(r['method'] == m for r in unk)} | "
                     f"{sum(r['method'] == m and r['evaluator_kind'] == 'model' for r in rows)} |")
    fam = Counter((r["attack_family"], short(r["method"])) for r in unk)
    lines += ["", "| family | b0 | b2 | ours |", "|---|---|---|---|"]
    for f in sorted({k[0] for k in fam}):
        lines.append(f"| {f} | {fam[(f, 'b0')]} | {fam[(f, 'b2')]} | {fam[(f, 'ours')]} |")
    succ = [r for r in rows if r["judge_label"] == "ATTACK_SUCCESS"]
    lines += ["", f"## All ATTACK_SUCCESS rows ({len(succ)})", "",
              "| case | method | family-idx | pos | evaluator | injected instruction | answer excerpt | human_label | audit note |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in succ:
        label, note = human(r["case_id"], r["method"])
        lines.append(f"| {r['case_id']} | {short(r['method'])} | {r['attack_family']}-{r['attack_index']} | "
                     f"{r['insertion_position']} | {r['evaluator_kind']} | {cell(attacks[r['case_id']], 120)} | "
                     f"{cell(r['answer'])} | {label} | {note} |")
    sample = random.Random(20261010).sample(unk, min(a.unknown_sample, len(unk)))
    lines += ["", f"## Random judge-UNKNOWN rows ({len(sample)} of {len(unk)}, seed 20261010)", "",
              "| case | method | family-idx | judge question | injected instruction | answer excerpt |",
              "|---|---|---|---|---|---|"]
    for r in sample:
        lines.append(f"| {r['case_id']} | {short(r['method'])} | {r['attack_family']}-{r['attack_index']} | "
                     f"{cell(r['evaluator_arg'], 120)} | {cell(attacks[r['case_id']], 120)} | {cell(r['answer'])} |")
    a.out.write_text("\n".join(lines) + "\n")
    print(f"UNKNOWN total={len(unk)}; successes={len(succ)} -> {a.out}")


if __name__ == "__main__":
    main()
