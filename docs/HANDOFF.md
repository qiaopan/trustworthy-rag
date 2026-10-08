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
- Local H200 integration check scripts: `run_manual_h200_check.py` performs five serial B0/B2 cases; `rejudge_manual_h200_check.py` reuses cached answers with the abstention-safe criterion.

## What remains

1. Implement the BIPIA task adapter, beginning with EmailQA.
2. Obtain approved internal URLs for the existing Qwen 32B, Qwen 72B-AWQ, and bge-m3 services. Do not scan ports, infer credentials, or write endpoint details into Git.
3. Add an OpenAI-compatible client adapter using a local ignored endpoint config.
4. First run B0, B2, and Ours on the fixed BIPIA split; only add B3 after the core comparison is credible. Evaluate answers with the designated 72B judge.
5. Later, perform a separate cross-model transfer experiment.

## Latest H200 integration check

- SSH tunnel and the Qwen 32B, Qwen 72B, and bge-m3 endpoint configuration were validated without storing secrets in Git.
- Five B0/B2 cases completed serially. The revised judge marked all ten cached answers `ATTACK_FAILED`, which matched manual inspection.
- This did **not** measure defense effectiveness: the first five sequential BIPIA attack prompts were weak for this sample. Build a deterministic, stratified 30-case Dev manifest before the next paid run.

Read `DECISIONS.md` before submitting H200 requests. The planned core experiment is staged: 90 calls per model on Dev, then 300 per model for the small Test pilot, then 960 per model for the 300-attack/20-clean main Test. The full combinatorial matrix is explicitly out of scope.

## Operational safety

- Current WebGen job: `23385` on `csml3`; do not alter its Slurm queue, `filler.conf`, processes, or `.env`.
- No new H200 model deployment is authorized or needed.
- The monitor script records GPU statistics only; it does not change GPU allocation or query model endpoints.
