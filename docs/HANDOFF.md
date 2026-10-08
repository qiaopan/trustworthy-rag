# Handoff: Trustworthy RAG

## Repository and current state

- Repository: `qiaopan/trustworthy-rag` (private)
- Local root: `~/Downloads/764/rag/trustworthy-rag`
- Initial commits: `018e600`, `6db88a1`
- Third-party source clones are deliberately not committed. Recreate them with `bash scripts/bootstrap_third_party.sh`.
- The offline smoke test passes: `PYTHONPATH=. .venv/bin/python scripts/run_smoke.py`.

## What is implemented

- Minimal dense-retrieval abstraction and deterministic offline fallback.
- B0 No Defense, B1 keyword filter, B2 hard risk filter, B3 risk-only rerank, and proposed relevance-risk-context-conflict rerank.
- PIGuard adapter, generator prompt helper, metric helpers, H200 configuration placeholders.

## What remains

1. Implement the BIPIA task adapter, beginning with EmailQA.
2. Obtain approved internal URLs for the existing Qwen 32B, Qwen 72B-AWQ, and bge-m3 services. Do not scan ports, infer credentials, or write endpoint details into Git.
3. Add an OpenAI-compatible client adapter using a local ignored endpoint config.
4. Run B0--B3 and Ours on a fixed BIPIA split, then evaluate answers with the designated 72B judge.
5. Later, perform a separate cross-model transfer experiment.

## Operational safety

- Current WebGen job: `23385` on `csml3`; do not alter its Slurm queue, `filler.conf`, processes, or `.env`.
- No new H200 model deployment is authorized or needed.
- The monitor script records GPU statistics only; it does not change GPU allocation or query model endpoints.
