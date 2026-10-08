"""H200 runner entry point. Task-specific BIPIA-to-corpus adapter remains to be implemented."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/h200.yaml")
    parser.add_argument("--method", choices=["b0", "b1", "b2", "b3", "ours"], required=True)
    parser.add_argument("--task", choices=["email", "qa", "abstract", "table", "code"], required=True)
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    print(f"Loaded {args.config}: generator={config['models']['generator']}; method={args.method}; task={args.task}")
    raise SystemExit("BIPIA adapter placeholder: first validate with scripts/run_smoke.py, then implement task mapping.")


if __name__ == "__main__":
    main()
