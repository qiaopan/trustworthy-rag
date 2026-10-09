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


## Current state (2026-10-09): main Test + B3 done

- Branch `main-test-2026-10-09` is pushed. Tag `main-test-frozen` = code used for the main Test run; B3 pre-registration committed before B3 ran. `outputs/test_main/provenance.json` pins commit + manifest sha256s.
- Pipeline: whole-email retrieval (bge-m3, top-3; target = BIPIA attacked email + 4 entity-excluded distractors) -> sentence-chunk defences with window PIGuard risk -> Qwen2.5-VL-32B (BIPIA system template) -> official BIPIA evaluators (72B judge replaces GPT-4). See DECISIONS "Pre-registration" sections.
- Runs completed (all serial, cached, no errors): Dev (train split, 30+30), Test pilot (100), main Test (300 attacked + 20 clean) for B0/B2/Ours, and B3 (risk-only) on the same 320 cases.
- Commands: `scripts/run_dev.py` (runner), `scripts/compute_metrics.py`, `scripts/paired_compare.py` (exact McNemar), `scripts/selection_tradeoff.py` (selection-only sweep, no model calls), `scripts/audit_report.py` (human-audit sheet), `scripts/build_emailqa_test_manifests.py --check`.

### Where outputs live (gitignored)
- `outputs/dev/` (Dev results, caches), `outputs/test_pilot/` (pilot), `outputs/test_main/`: `main_attack.jsonl`, `main_clean.jsonl`, `b3_main_300.jsonl`, `b3_clean_20.jsonl`, `metrics_main.json`, `metrics_with_b3.json`, `paired_main.json`, `paired_b3.json`, `selection_tradeoff.json`, `audit.md`, `provenance.json`, `cache/`.

### Current finalisation plan

See `STATUS_AND_TODO.md` for the current checklist. The required remaining
experiment is raw (per-chunk) PIGuard B2 on the frozen 300 attacked + 20 clean
Main Test. The existing window-risk run is named B2-win. A disjoint 45-case
follow-up Dev has completed under both BIPIA prompt templates; it is
supplementary, not pooled with the primary Test result.

### Pointers (2026-10-09)
- `docs/DECISION_LOG.md`: one table of every decision so far (problem, options, choice and reason, evidence, numbers, status). Read this first.
- `docs/LITERATURE_CHUNKING.md`: verified citations on chunk granularity and injection-detection granularity.
- Exploratory Dev chunk-size sweep: `scripts/sweep_granularity.py` → `outputs/dev/sweep_granularity_endpoint.jsonl`. The frozen Test protocol is unchanged.

### 2026-10-09 (later): raw-PIGuard B2 and no-system template
- Final tables: DECISIONS "Results: B2 (per-chunk PIGuard) and no-system template"; DECISION_LOG rows 23–26.
- Outputs (`outputs/test_main/`):
  - System template: `main_attack.jsonl`, `main_clean.jsonl` (B0, B2-win, Ours); `b3_*.jsonl`; `b2raw_main_300.jsonl` (rebuilt from the cache), `b2raw_clean_20.jsonl`.
  - No-system template: `wosys_main_300.jsonl`, `wosys_clean_20.jsonl`.
  - Metrics: `metrics_final_{system,wosys}.json`; paired tests: `paired_final_{system,wosys}.{json,txt}`.
  - Audit sheets: `audit.md`, `audit_wosys.md`.
- Human-audit overrides: `data/human_audit_labels.json`; pass it to `scripts/compute_metrics.py --human-labels` for the secondary adjusted ASR.
- Method keys in result files: `b2raw` = B2; `b2` = B2-win; `ours_a0…` and `b3` = B3.
- B2-doc (document-level PIGuard): `outputs/test_main/b2doc_{main_300,clean_20}.jsonl`, `metrics_b2doc.json`, `paired_b2doc.json`; DECISIONS "Results: B2-doc"; DECISION_LOG row 27.
- Clean n=50 and B1: DECISIONS "Results: clean set n=50 and B1"; DECISION_LOG rows 28–29.
- Paper: `paper/main.tex`. Figures come from `scripts/make_paper_figs.py` → `paper/figs/`. No LaTeX is installed on this machine; compile on Overleaf or another TeX installation.
