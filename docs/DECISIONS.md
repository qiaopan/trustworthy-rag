# Trustworthy RAG decisions

## Current model plan (2026-10-08)

The project reuses existing H200 services rather than deploying any additional LLM.

| Component | Decision | Rationale |
|---|---|---|
| Generator | Reuse `Qwen2.5-VL-32B-Instruct` | General-purpose model; do not use the WebGen-finetuned 32B model as the primary RAG generator. |
| Judge | Reuse `Qwen2.5-VL-72B-Instruct-AWQ` | Separates judging from 32B generation and reduces same-model self-evaluation bias. |
| Retrieval embedding | Reuse `bge-m3` | Existing dense embedding service; replaces `BAAI/bge-base-en-v1.5`. |
| Injection scoring | Run `leolee99/PIGuard` on the project owner's 24 GB Apple-Silicon Mac | PIGuard is a 0.2B text classifier and does not require H200. |
| Reranking | Local Python | The proposed relevance-risk-context-conflict score does not require another model. |

## Constraints

- Do not deploy Llama, Qwen 14B, or another standalone generator while WebGen is active.
- Do not use `WebGen-LM-32B` as the Trustworthy RAG primary generator; it is WebGen-finetuned.
- Existing endpoint URLs, credentials, and ports are never committed. Put them in a local ignored config file.
- Formal batch evaluation must run in an approved low-load window. Calls to an existing vLLM service consume KV-cache capacity even though no weights are reloaded.
- For a later transfer/generalization experiment, run the full fixed pipeline with a second general-purpose model and report that result separately.

## H200 observation

At the time of inspection, the WebGen Slurm job `23385` owned two H200 GPUs. The worker log and direct readings showed high, but non-OOM, usage: known free-memory observations were approximately 21 GiB, 32 GiB, 34 GiB, and 28 GiB across the two cards at two sampled times. The worker log contained no CUDA OOM, engine-failure, or restart signal. This is not a continuous 24-hour history; use `scripts/h200_gpu_monitor.sh` for prospective measurements.
