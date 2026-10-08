# Trustworthy RAG

Course-project experiment scaffold for risk-aware retrieval against indirect prompt injection.

## Layout

- `third_party/BIPIA/`: attack benchmark (cloned reference repository)
- `third_party/PIGuard/`: prompt-injection detector baseline (cloned reference repository)
- `src/`: minimal retrieval, defense, reranking, generation, and evaluation components
- `configs/h200.yaml`: H200 experiment defaults; models are downloaded only on the server
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

## H200 quick start

On the H200, clone this repository including `third_party/`, create the environment, then run:

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

The default H200 models are `meta-llama/Llama-3.1-8B-Instruct`, `BAAI/bge-base-en-v1.5`, and `leolee99/PIGuard`. Authenticate with Hugging Face before downloading gated Llama weights. `Qwen/Qwen2.5-14B-Instruct` is configured as an optional cross-model generator. The runner is intentionally a placeholder until the BIPIA task adapter is finalized; use `run_smoke.py` to validate the core pipeline now.

## Reproducibility notes

`third_party/` is ignored by the project commit because it contains independently versioned repositories. Run `scripts/bootstrap_third_party.sh` after cloning; remote URLs and expected revisions are recorded in `third_party/REVISIONS.md`.
