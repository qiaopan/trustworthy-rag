# Trustworthy RAG

Course-project experiment scaffold for risk-aware retrieval against indirect prompt injection.

## Layout

- `third_party/BIPIA/`: attack benchmark (cloned reference repository)
- `third_party/PIGuard/`: prompt-injection detector baseline (cloned reference repository)
- `src/`: minimal retrieval, defense, reranking, generation, and evaluation components
- `configs/h200.yaml`: model-role defaults for H200 reuse
- `configs/h200_reuse.example.yaml`: endpoint placeholders for existing H200 services
- `docs/DECISIONS.md`: experiment decisions and current operational constraints
- `docs/HANDOFF.md`: concise state for a later agent or collaborator
- `scripts/run_smoke.py`: offline end-to-end sanity check

## Experiment matrix

| ID | Method | Selection rule |
|---|---|---|
| B0 | No Defense | relevance top-k |
| B1 | Keyword filter | discard passages matching injection keywords |
| B2 | PIGuard hard filter | discard passages whose PIGuard risk exceeds threshold |
| B3 | Risk-only soft rerank | rank by negative injection risk only |
| Ours | relevance-risk-conflict rerank | `alpha * relevance - beta * risk - gamma * context_conflict` |

The primary benchmark is BIPIA. Begin with one BIPIA task (recommended: EmailQA), then add other tasks or SafeRAG only after the primary matrix is reproducible.

## Local smoke test (no model download)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python scripts/run_smoke.py
```

## Local PIGuard verification (24 GB Mac)

PIGuard is the only model that needs to be downloaded locally. It is a small 0.2B text classifier; no local generator is required.

```bash
python3 -m venv .venv-piguard
.venv-piguard/bin/pip install torch transformers
HF_HOME="$PWD/.cache/huggingface" .venv-piguard/bin/python scripts/smoke_piguard.py
HF_HOME="$PWD/.cache/huggingface" PYTHONPATH=. .venv-piguard/bin/python scripts/run_local_piguard_rerank.py
```

## H200 model-reuse plan

This project must **not deploy new LLMs on the H200**. It reuses approved, existing WebGen-hosted services when capacity is available:

| Role | Existing service to reuse |
|---|---|
| Generator | `Qwen2.5-VL-32B-Instruct` |
| Judge / ASR evaluator | `Qwen2.5-VL-72B-Instruct-AWQ` |
| Embedding | `bge-m3` |
| Injection guard | local `leolee99/PIGuard` on the 24 GB Mac |

Before a formal run, the service owner must provide approved internal endpoint URLs and a low-load time window. The endpoint values are intentionally not stored in Git; copy `configs/h200_reuse.example.yaml` to a local ignored configuration file.

On the H200, clone the project and set up only code dependencies:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL> trustworthy-rag
cd trustworthy-rag
bash scripts/bootstrap_third_party.sh
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e third_party/BIPIA
PYTHONPATH=. python scripts/run_bipia.py --config configs/h200.yaml --method ours --task email
```

The runner is intentionally a placeholder until the BIPIA task adapter is finalized; use `run_smoke.py` to validate the core pipeline now. A later cross-model transfer run may use a paper-standard general-purpose model, but it is a separate reported experiment, not a new deployment during the active WebGen run.

### Lightweight H200 memory log

`scripts/h200_gpu_monitor.sh` records only timestamp, GPU index, used/free memory, and utilization. It neither calls a model service nor changes Slurm. Run it only with the project owner's approval, then filter it to the GPUs allocated to the WebGen job.

## Reproducibility notes

`third_party/` is ignored by the project commit because it contains independently versioned repositories. Run `scripts/bootstrap_third_party.sh` after cloning; remote URLs and expected revisions are recorded in `third_party/REVISIONS.md`.
