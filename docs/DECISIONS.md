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

## H200 request budget

EmailQA has 50 test contexts and the BIPIA text-attack test file has 75 prompts. BIPIA constructs every context/attack pair at three insertion positions:

`50 contexts x 75 attacks x 3 positions = 11,250 poisoned cases`.

Running all five methods (B0--B3 and Ours) without caching would therefore require up to **56,250 generator calls** and **56,250 judge calls**. This is too large to run alongside active WebGen work, even though it reuses existing services.

Use the following staged budget instead:

| Stage | Suggested cases before method matrix | 32B generation calls | 72B judge calls | When to run |
|---|---:|---:|---:|---|
| Manual integration check | 2 | 10 | 10 | Approved low-load moment only |
| Pilot | 10 contexts x 10 attacks x 1 position = 100 | 500 | 500 | Low-load window; concurrency 1 |
| Main EmailQA result | 50 contexts x 15 attack families x 3 positions = 2,250 | 11,250 | 11,250 | WebGen idle/approved dedicated window |
| Full combinatorial sweep | 11,250 | 56,250 | 56,250 | Only if required and separately scheduled |

Cache PIGuard scores, embeddings, retrieval results, generated answers, and judge outputs by input hash. PIGuard runs locally and does not consume H200. Do not use `srun --overlap` to start another model or heavy batch while WebGen is active; endpoint calls themselves share the existing vLLM KV-cache and must be serial (`request_concurrency: 1`).
