"""Clean-set utility / false-positive report over all 50 EmailQA test contexts (system template).

Combines the original 20 clean cases with the 30 extra ones, normalises method names
(b2raw=B2, b2=B2-win, ours_a0*/b3=B3), and reports Wilson CIs and exact McNemar Ours vs each.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compute_metrics import method_key, wilson  # noqa: E402
from paired_compare import mcnemar_exact  # noqa: E402

M = ROOT / "outputs/test_main"
FILES = ["main_clean", "b3_clean_20", "b2raw_clean_20", "b2doc_clean_20", "clean_extra_30", "b1_clean_20", "b1_clean_extra_30"]
NAMES = {"b0": "B0", "b1": "B1", "b2raw": "B2", "b2doc": "B2-doc", "b2": "B2-win", "b3": "B3", "ours": "Ours"}


def main() -> None:
    rows = [r for f in FILES for r in map(json.loads, (M / f"{f}.jsonl").read_text().splitlines())
            if r.get("label") == "clean"]
    by = {}
    for r in rows:
        key = (r["case_id"].removesuffix("-clean"), method_key(r["method"]))
        assert key not in by, key
        by[key] = r
    cases = sorted({c for c, _ in by})
    report = {"n_cases": len(cases)}
    fmt = lambda k, n: f"{k}/{n} [{wilson(k, n)[0]*100:.1f}, {wilson(k, n)[1]*100:.1f}]"
    for m in NAMES:
        rs = [by[(c, m)] for c in cases]
        ok = [r["judge_label"] == "CORRECT" for r in rs]
        known = [o for o, r in zip(ok, rs) if r["ideal_known"]]
        unk = [o for o, r in zip(ok, rs) if not r["ideal_known"]]
        chunks = sum(r["selection"]["clean_chunks_dropped"] for r in rs)
        total = sum(r["selection"]["clean_chunks_retrieved"] for r in rs)
        emails = sum(len(set(r["selection"]["doc_ids"]) - {p.split("-")[0] for p in r["selection"]["kept_pids"]}) for r in rs)
        fp_cases = sum(r["selection"]["clean_chunks_dropped"] > 0 for r in rs)
        report[NAMES[m]] = {"accuracy": fmt(sum(ok), len(ok)), "known": fmt(sum(known), len(known)),
                            "unknown": fmt(sum(unk), len(unk)), "clean_chunks_dropped": f"{chunks}/{total}",
                            "emails_fully_dropped": emails, "cases_with_any_drop": fmt(fp_cases, len(rs)),
                            "abstained": sum(r["abstained"] for r in rs),
                            "errors": sum(r["judge_label"] in ("ERROR", "INVALID") for r in rs)}
        if m != "ours":
            o = [by[(c, "ours")]["judge_label"] == "CORRECT" for c in cases]
            b, cc = sum(x and not y for x, y in zip(o, ok)), sum(y and not x for x, y in zip(o, ok))
            report[NAMES[m]]["mcnemar_ours_only/other_only"] = f"{b}/{cc} p={mcnemar_exact(b, cc):.3f}"
    (M / "clean50_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
