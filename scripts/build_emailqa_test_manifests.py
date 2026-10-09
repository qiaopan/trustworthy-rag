"""Build/verify the held-out BIPIA EmailQA Test manifests (offline, deterministic).

* ``emailqa_test_followup_dev_45.jsonl``: 45 attacked cases for supplementary
  follow-up development, one per (attack family, insertion position) cell.
* ``emailqa_test_pilot_100.jsonl``: 100 attacked cases (infra/stability pilot).
* ``emailqa_test_main_300.jsonl``: 300 attacked cases.
* ``emailqa_test_clean_20.jsonl``: 20 clean cases, 10 known-ideal + 10 unknown-ideal contexts.

Attacked cases are stratified over the 45 (test attack family x insertion position)
cells: cells are visited in a seeded order, round robin, so every cell gets
floor/ceil of n/45 cases.  Each case draws a seeded (context_index, attack_index);
The follow-up Dev, pilot and main sets are DISJOINT at the (context, family,
attack_index, position) level.  The original pilot/main random stream is left
unchanged so their committed manifests and frozen-test provenance remain valid.
Headers pin the SHA-256 of BIPIA's ``email/test.jsonl`` and ``text_attack_test.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "third_party/BIPIA/benchmark"
OUT = ROOT / "data/manifests"
SEED = 20261010
POSITIONS = ("start", "middle", "end")
FILES = {"dev45": "emailqa_test_followup_dev_45.jsonl", "pilot": "emailqa_test_pilot_100.jsonl", "main": "emailqa_test_main_300.jsonl", "clean": "emailqa_test_clean_20.jsonl"}
FOLLOWUP_DEV_SEED = 20261011


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header(kind: str) -> dict:
    seed = FOLLOWUP_DEV_SEED if kind == "dev45" else SEED
    return {"schema_version": 1, "kind": "trustworthy-rag-emailqa-test-manifest", "subset": kind, "seed": seed,
            "benchmark": "microsoft/BIPIA",
            "email_test_sha256": sha256(BENCH / "email/test.jsonl"),
            "text_attack_test_sha256": sha256(BENCH / "text_attack_test.json")}


def build() -> dict[str, list[dict]]:
    contexts = [json.loads(l) for l in (BENCH / "email/test.jsonl").read_text().splitlines() if l]
    attacks = json.loads((BENCH / "text_attack_test.json").read_text())
    rng = random.Random(SEED)
    cells = [(f, p) for f in sorted(attacks) for p in POSITIONS]
    used: set[tuple] = set()
    out = {}
    for subset, n in (("pilot", 100), ("main", 300)):
        order = cells[:]
        rng.shuffle(order)
        records = []
        for i in range(n):
            family, position = order[i % len(order)]
            while True:
                key = (rng.randrange(len(contexts)), family, rng.randrange(len(attacks[family])), position)
                if key not in used:
                    used.add(key)
                    break
            records.append({"schema_version": 1, "split": "test", "task": "email", "subset": subset,
                            "case_id": f"emailqa-test-{subset}-{i + 1:03d}", "seed": SEED, "context_index": key[0],
                            "attack_family": family, "attack_index": key[2], "insertion_position": position})
        out[subset] = records
    # This comes after the original pilot/main construction on purpose: adding a
    # follow-up set must never change their already frozen deterministic samples.
    dev_rng = random.Random(FOLLOWUP_DEV_SEED)
    order = cells[:]
    dev_rng.shuffle(order)
    records = []
    for i, (family, position) in enumerate(order):
        while True:
            key = (dev_rng.randrange(len(contexts)), family, dev_rng.randrange(len(attacks[family])), position)
            if key not in used:
                used.add(key)
                break
        records.append({"schema_version": 1, "split": "test", "task": "email", "subset": "followup-dev",
                        "case_id": f"emailqa-test-followup-dev-{i + 1:02d}", "seed": FOLLOWUP_DEV_SEED,
                        "context_index": key[0], "attack_family": family, "attack_index": key[2],
                        "insertion_position": position})
    out["dev45"] = records
    known = [i for i, c in enumerate(contexts) if c["ideal"] not in ("unknown", "unkown")]
    unknown = [i for i, c in enumerate(contexts) if c["ideal"] in ("unknown", "unkown")]
    chosen = sorted(rng.sample(known, 10)) + sorted(rng.sample(unknown, 10))
    out["clean"] = [{"schema_version": 1, "split": "test", "task": "email", "subset": "clean", "label": "clean",
                     "case_id": f"emailqa-test-clean-{i + 1:02d}", "seed": SEED, "context_index": idx}
                    for i, idx in enumerate(chosen)]
    return out


def validate(m: dict[str, list[dict]]) -> None:
    key = lambda r: (r["context_index"], r["attack_family"], r["attack_index"], r["insertion_position"])
    dev45, pilot, main = ({key(r) for r in m[name]} for name in ("dev45", "pilot", "main"))
    assert len(dev45) == 45 and len(pilot) == 100 and len(main) == 300, "unexpected attacked split size"
    assert not (dev45 & pilot or dev45 & main or pilot & main), "attacked splits must be pairwise disjoint"
    for subset in ("dev45", "pilot", "main"):
        counts = Counter((r["attack_family"], r["insertion_position"]) for r in m[subset])
        assert len(counts) == 45 and max(counts.values()) - min(counts.values()) <= 1, f"{subset} not stratified"
    assert len({r["context_index"] for r in m["clean"]}) == 20
    ids = [r["case_id"] for s in m.values() for r in s]
    assert len(ids) == len(set(ids))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    m = build()
    validate(m)
    for subset, name in FILES.items():
        text = "\n".join(json.dumps(r, sort_keys=True) for r in [header(subset), *m[subset]]) + "\n"
        path = OUT / name
        if a.check:
            if path.read_text() != text:
                raise SystemExit(f"MISMATCH: {path} differs from deterministic rebuild (BIPIA revision changed?)")
        else:
            path.write_text(text)
    print(("OK: verified " if a.check else "Wrote ") + ", ".join(FILES.values()))


if __name__ == "__main__":
    main()
