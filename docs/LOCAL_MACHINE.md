# Local machine profile

This is the machine used for the local PIGuard detector and offline ranking
checks. It is not a replacement for the H200 generator or judge services.

| Item | Specification |
|---|---|
| Computer | Apple Mac with Apple M5 chip |
| Unified memory | 24 GB |
| Internal storage | 1 TB |
| Local workload | PIGuard (about 0.2B parameters), cached embeddings/risk scores, and Python reranking |
| Not run locally | Qwen2.5-VL-32B generator and Qwen2.5-VL-72B judge |

The local setup should use the `.venv-piguard` environment and a project-local
Hugging Face cache. Do not place H200 service endpoints, API keys, or other
credentials in this document or in Git.
