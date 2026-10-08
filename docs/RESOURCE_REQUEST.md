# Trustworthy RAG: Resource Request

Trustworthy RAG is a course project on defending Retrieval-Augmented Generation
systems against indirect prompt-injection attacks. It is an inference and
evaluation project only; no model training or fine-tuning is required.

## Requested allocation

- 2 × NVIDIA H200 GPUs, 141 GB each.
- 32 CPU cores preferred.
- 128–256 GB system RAM preferred.
- 300–500 GB project storage preferred.

## Planned model placement

- **H200 GPU 1:** Qwen2.5-32B-Instruct generator, served with vLLM in BF16. Estimated use: 105–125 GB VRAM.
- **H200 GPU 2:** Qwen2.5-72B-Instruct-AWQ judge, served with vLLM. Estimated use: 75–105 GB VRAM.
- **GPU 2 or CPU:** bge-m3 embedding model. Estimated use: 4–8 GB VRAM if GPU-hosted.
- **GPU 2 or CPU:** PIGuard prompt-injection classifier. Estimated use: 2–6 GB VRAM if GPU-hosted; CPU-only is also feasible.

The generator answers RAG questions; the 72B model judges attack success and
answer correctness; bge-m3 retrieves passages; and PIGuard scores
prompt-injection risk before retrieved text enters the generator prompt.

The project will begin with small, serial development runs for validation and
will use caching throughout. Request concurrency for the larger evaluation can
be increased later only after measuring GPU memory use and service stability.
Two GPUs leave enough memory margin to keep the 32B generator and quantized
72B judge available simultaneously without repeatedly reloading models.

## Deployment priority

1. Qwen2.5-32B-Instruct generator
2. Qwen2.5-72B-Instruct-AWQ judge
3. bge-m3 embedding model
4. PIGuard locally on CPU or a small GPU partition

An optional Llama-3.1-8B-Instruct cross-model robustness check is outside the
core deployment request and should be added only if spare capacity is available.

This document describes a future dedicated allocation. The currently active
experiment plan continues to reuse approved services when available; endpoint
details and credentials must never be committed to this repository.
