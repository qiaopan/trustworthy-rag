"""Build and verify the fixed, stratified 30-case BIPIA EmailQA Dev manifest.

The manifest contains references into BIPIA instead of copied benchmark text.  It
is therefore small, reviewable, reproducible, and does not duplicate the
benchmark's data in this repository.  It deliberately covers every text-attack
family twice and balances the three insertion positions (10 cases each).

This script is offline: it never loads a model or contacts an endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = ROOT / "third_party/BIPIA/benchmark"
DEFAULT_OUTPUT = ROOT / "data/manifests/emailqa_dev_30.jsonl"
SEED = 20261009
POSITIONS = ("start", "middle", "end")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(benchmark_dir: Path) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    contexts = [json.loads(line) for line in (benchmark_dir / "email/train.jsonl").read_text().splitlines() if line]
    attacks = json.loads((benchmark_dir / "text_attack_train.json").read_text())
    if not contexts or not attacks:
        raise ValueError("BIPIA EmailQA contexts and text attacks must both be non-empty")
    if any(not values for values in attacks.values()):
        raise ValueError("Every BIPIA attack family must include at least one prompt")
    return contexts, attacks


def build_manifest(benchmark_dir: Path, seed: int = SEED) -> list[dict[str, Any]]:
    """Return 2 cases per attack family with 10 cases per insertion position."""
    contexts, attacks = load_inputs(benchmark_dir)
    families = sorted(attacks)
    case_count = len(families) * 2
    if case_count != 30:
        raise ValueError(f"Expected 15 BIPIA attack families for a 30-case Dev set; found {len(families)}")
    if len(contexts) < case_count:
        raise ValueError(f"Need at least {case_count} EmailQA contexts; found {len(contexts)}")

    # A seeded sample makes each Dev case use a different clean EmailQA context.
    context_indices = random.Random(seed).sample(range(len(contexts)), case_count)
    records: list[dict[str, Any]] = []
    for family_index, family in enumerate(families):
        prompts = attacks[family]
        for replicate in range(2):
            case_index = family_index * 2 + replicate
            records.append(
                {
                    "schema_version": 1,
                    "split": "dev",
                    "task": "email",
                    "case_id": f"emailqa-dev-{case_index + 1:02d}",
                    "seed": seed,
                    "context_index": context_indices[case_index],
                    "attack_family": family,
                    # Offset the second prompt choice so the paired cases do not
                    # trivially reuse the same string when a family has >1 prompt.
                    "attack_index": (family_index + replicate) % len(prompts),
                    "insertion_position": POSITIONS[case_index % len(POSITIONS)],
                }
            )
    return records


def validate_manifest(records: list[dict[str, Any]], benchmark_dir: Path) -> None:
    contexts, attacks = load_inputs(benchmark_dir)
    if len(records) != 30:
        raise ValueError(f"Expected exactly 30 Dev records, found {len(records)}")
    families = Counter(record["attack_family"] for record in records)
    expected_families = set(attacks)
    if set(families) != expected_families or any(count != 2 for count in families.values()):
        raise ValueError("Manifest must contain exactly two cases from every BIPIA attack family")
    positions = Counter(record["insertion_position"] for record in records)
    if positions != Counter({"start": 10, "middle": 10, "end": 10}):
        raise ValueError(f"Insertion positions must be balanced 10/10/10; found {dict(positions)}")
    case_ids = [record["case_id"] for record in records]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case_id values must be unique")
    indices = [record["context_index"] for record in records]
    if len(indices) != len(set(indices)) or not all(0 <= index < len(contexts) for index in indices):
        raise ValueError("Each record must reference one distinct, valid EmailQA context")
    for record in records:
        family = record["attack_family"]
        if not 0 <= record["attack_index"] < len(attacks[family]):
            raise ValueError(f"Invalid attack_index in {record['case_id']}")
        if record["task"] != "email" or record["split"] != "dev":
            raise ValueError(f"Unexpected task/split in {record['case_id']}")


def manifest_header(benchmark_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "trustworthy-rag-emailqa-dev-manifest",
        "seed": SEED,
        "benchmark": "microsoft/BIPIA",
        "email_train_sha256": sha256(benchmark_dir / "email/train.jsonl"),
        "text_attack_train_sha256": sha256(benchmark_dir / "text_attack_train.json"),
        "description": "30 Dev cases: every attack family twice; positions balanced start/middle/end.",
    }


def write_manifest(output: Path, benchmark_dir: Path) -> None:
    records = build_manifest(benchmark_dir)
    validate_manifest(records, benchmark_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(manifest_header(benchmark_dir), sort_keys=True)]
    lines.extend(json.dumps(record, sort_keys=True) for record in records)
    output.write_text("\n".join(lines) + "\n")


def read_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    if not rows or rows[0].get("kind") != "trustworthy-rag-emailqa-dev-manifest":
        raise ValueError("Missing or invalid Dev manifest header")
    return rows[0], rows[1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Validate an existing manifest without rewriting it")
    args = parser.parse_args()
    if args.check:
        header, records = read_manifest(args.output)
        validate_manifest(records, args.benchmark_dir)
        expected = manifest_header(args.benchmark_dir)
        if header != expected:
            raise ValueError("Manifest header does not match the installed BIPIA benchmark revision")
        print(f"OK: {args.output} has {len(records)} balanced, stratified Dev cases")
        return
    write_manifest(args.output, args.benchmark_dir)
    print(f"Wrote {args.output} (30 fixed, balanced Dev cases)")


if __name__ == "__main__":
    main()
