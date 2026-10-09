"""Build/verify the 30 extra clean Test cases: every BIPIA EmailQA test context not in
emailqa_test_clean_20.jsonl (so the two files together cover all 50 test contexts).
Deterministic (sorted context indices); header pins the BIPIA test file checksums."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN20 = ROOT / "data/manifests/emailqa_test_clean_20.jsonl"
OUT = ROOT / "data/manifests/emailqa_test_clean_extra_30.jsonl"


def build() -> str:
    rows = [json.loads(l) for l in CLEAN20.read_text().splitlines() if l.strip()]
    header = {**rows[0], "subset": "clean_extra"}
    used = {r["context_index"] for r in rows[1:]}
    n = sum(1 for l in (ROOT / "third_party/BIPIA/benchmark/email/test.jsonl").read_text().splitlines() if l.strip())
    recs = [{"schema_version": 1, "split": "test", "task": "email", "subset": "clean_extra", "label": "clean",
             "case_id": f"emailqa-test-clean-x{i + 1:02d}", "seed": header["seed"], "context_index": idx}
            for i, idx in enumerate(sorted(set(range(n)) - used))]
    assert len(recs) == 30 and not used & {r["context_index"] for r in recs}
    return "\n".join(json.dumps(r, sort_keys=True) for r in [header, *recs]) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    text = build()
    if a.check:
        if OUT.read_text() != text:
            raise SystemExit(f"MISMATCH: {OUT}")
        print(f"OK: {OUT.name}")
    else:
        OUT.write_text(text)
        print(f"Wrote {OUT.name}")


if __name__ == "__main__":
    main()
