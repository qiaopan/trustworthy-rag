# Handoff: Trustworthy RAG

## Repository and current state

- Repository: `qiaopan/trustworthy-rag` (visibility is managed on GitHub)
- Local root: `~/Downloads/764/rag/trustworthy-rag`
- Initial commits: `018e600`, `6db88a1`
- Third-party source clones are deliberately not committed. Recreate them with `bash scripts/bootstrap_third_party.sh`.
- Verified offline: the deterministic Dev manifest check and the 17-test suite
  pass in `.venv-piguard`. No model endpoint was called during that verification.

## What is implemented

- Minimal dense-retrieval abstraction and deterministic offline fallback.
- B0 No Defense, B1 keyword filter, B2 hard risk filter, B3 risk-only rerank, and proposed relevance-risk-context-conflict rerank.
- PIGuard adapter, generator prompt helper, metric helpers, H200 configuration placeholders.
- Local H200 integration check scripts: `run_manual_h200_check.py` performs five serial B0/B2 cases; `rejudge_manual_h200_check.py` reuses cached answers with the abstention-safe criterion.
- A reproducible EmailQA runner now exists: `src/bipia_emailqa.py` builds a
  labelled RAG pool using BIPIA's own insertion and prompt code;
  `scripts/run_dev.py` runs B0/B2/Ours serially with content-addressed caching;
  `scripts/compute_metrics.py` reports malicious inclusion, ASR, and clean
  accuracy; `scripts/score_piguard.py` precomputes local detector scores.
- `data/manifests/emailqa_dev_30.jsonl` is the fixed 30-case Dev set. It uses
  only BIPIA's training split (15 attack families x 2; insertion positions
  balanced 10/10/10), preserving the BIPIA test split for held-out evaluation.

## What remains

1. Precompute PIGuard scores for the manifest passage pool locally, then run
   the offline selection sweep. This is the gate before any generator calls.
2. Use the existing ignored local configuration for the already-approved Qwen
   generator, Qwen judge, and embedding endpoints. Never scan ports, infer
   credentials, or write endpoint details into Git.
3. After the local gate, run serial B0/B2 Dev and then only promising Ours
   configurations. Evaluate answers with the designated judge. Do not describe
   the old five-case integration check as a defense result.
4. Freeze one Ours configuration before touching the held-out BIPIA test split;
   only add B3 after the core comparison is credible.
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
