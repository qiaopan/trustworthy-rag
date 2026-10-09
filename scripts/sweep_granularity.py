"""EXPLORATORY (Dev/train split only; does not change the frozen Test protocol):
selection-level sweep of chunk granularity.  No generator/judge calls.

Granularities: sent1 (one Punkt sentence), sent12 (1-2 sentences, <=150 chars; the
frozen protocol), tok256 / tok512 (sentences merged up to ~256 / ~512 tokens,
approximated as 4 chars/token).  Proposition chunking (Chen et al. 2023) needs an
LLM and is skipped.  Each granularity is reported with window and raw-chunk risk.

  1) .venv:          scripts/sweep_granularity.py --dump outputs/dev/gran_texts.jsonl
  2) .venv-piguard:  scripts/score_piguard.py --texts outputs/dev/gran_texts.jsonl
  3) .venv:          scripts/sweep_granularity.py --embedder endpoint
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.bipia_emailqa as be  # noqa: E402
from src.llm_client import CachedEmbedder, JsonlCache  # noqa: E402
from src.rag_pipeline import CachedRiskScorer, OursConfig, retrieve_docs, select_chunks, selection_summary  # noqa: E402
from src.retrieval import HashingEmbedder  # noqa: E402

BIG = 10 ** 9
GRANULARITIES = {
    "sent1": dict(max_chars=BIG, max_sentences=1),
    "sent12": dict(max_chars=150, max_sentences=2),
    "tok256": dict(max_chars=256 * 4, max_sentences=BIG),
    "tok512": dict(max_chars=512 * 4, max_sentences=BIG),
}
_FROZEN_CHUNK = be.chunk


def use(name: str) -> None:
    kw = GRANULARITIES[name]
    be.chunk = lambda text, max_chars=None: [text[a:b].strip() for a, b in be.chunk_spans(text, kw["max_chars"], kw["max_sentences"])]


def cases_for(name: str, manifest: Path):
    use(name)
    try:
        return be.load_cases(manifest, include_clean=True)
    finally:
        be.chunk = _FROZEN_CHUNK


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/emailqa_dev_30.jsonl")
    p.add_argument("--out", type=Path, default=ROOT / "outputs/dev")
    p.add_argument("--dump", type=Path)
    p.add_argument("--embedder", choices=("fake", "endpoint"), default="fake")
    a = p.parse_args()
    all_cases = {g: cases_for(g, a.manifest) for g in GRANULARITIES}
    if a.dump:
        texts = dict.fromkeys(t for cs in all_cases.values() for t in be.scoring_texts(cs))
        a.dump.write_text("".join(json.dumps({"text": t}) + "\n" for t in texts))
        print(f"Wrote {len(texts)} texts to {a.dump}")
        return
    scorer = CachedRiskScorer(a.out / "cache/piguard.jsonl")
    embedder = HashingEmbedder() if a.embedder == "fake" else CachedEmbedder.from_config(JsonlCache(a.out / "cache/embeddings.jsonl"))
    rows = []
    for g, cases in all_cases.items():
        att = [c for c in cases if c.label == "attack"]
        cln = [c for c in cases if c.label == "clean"]
        docs = {c.case_id: retrieve_docs(c, embedder, 3) for c in cases}
        chunks_per_target = sum(len(next(d for d in c.docs if d.kind == "target").chunks) for c in cln) / len(cln)
        for mode in ("window", "chunk"):
            for method in ("b0", "b2", "ours"):
                sel = {c.case_id: selection_summary(c, docs[c.case_id], select_chunks(
                    c, docs[c.case_id], scorer, method, OursConfig(), 0.5, embedder, mode)) for c in cases}
                ans = [c for c in att if sel[c.case_id]["answer_possible"]]
                row = {"granularity": g, "risk": mode, "method": method,
                       "chunks_per_target_email": round(chunks_per_target, 2),
                       "attack_in_context": f"{sum(sel[c.case_id]['malicious_included'] for c in att)}/{len(att)}",
                       "attack_removed": f"{sum(sel[c.case_id]['attack_removed'] for c in att)}/{len(att)}",
                       "answer_retained": f"{sum(sel[c.case_id]['answer_retained'] for c in ans)}/{len(ans)}",
                       "clean_dropped_attack": sum(sel[c.case_id]["clean_chunks_dropped"] for c in att),
                       "clean_dropped_clean": sum(sel[c.case_id]["clean_chunks_dropped"] for c in cln),
                       "clean_chars_dropped_attack": sum(len(r.passage.text) for c in att for r in select_chunks(
                           c, docs[c.case_id], scorer, method, OursConfig(), 0.5, embedder, mode)
                           if not r.kept and r.passage.kind != "poisoned")}
                rows.append(row)
                print("  ".join(f"{k}={v}" for k, v in row.items()), flush=True)
    out = a.out / f"sweep_granularity_{a.embedder}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"-> {out}; new_embedding_calls={getattr(embedder, 'calls', 0)}  (EXPLORATORY, Dev only)")


if __name__ == "__main__":
    main()
