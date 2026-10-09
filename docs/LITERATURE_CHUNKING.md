# Literature: chunk granularity and injection-detection granularity

Checked 2026-10-09 against the arXiv / ACL Anthology / publisher page of each source (title, authors, year, venue). Items marked **(secondary)** could not be checked in full from the primary text.

## A. Chunk size / retrieval granularity in RAG

| Source | Verified citation | Finding | Implication for us |
|---|---|---|---|
| Dense X Retrieval | Tong Chen, Hongwei Wang, Sihao Chen, Wenhao Yu, Kaixin Ma, Xinran Zhao, Hongming Zhang, Dong Yu. *Dense X Retrieval: What Retrieval Granularity Should We Use?* arXiv:2312.06648 (2023; revised 2024). The arXiv page lists no venue; it is widely cited as EMNLP 2024, which we have **not verified** here. | Indexing by propositions (atomic, self-contained facts) beats passage and sentence indexing for retrieval, and improves downstream QA at a fixed compute budget. | Finer units help *retrieval*. In our design retrieval is whole-email and only the *defence* works on chunks, so the claim transfers only partially. Building propositions needs an LLM rewrite, so we skipped it (cost, and it changes the text the generator sees). |
| LlamaIndex blog | Ravi Theja. *Evaluating the Ideal Chunk Size for a RAG System using LlamaIndex.* LlamaIndex blog, 5 Oct 2023. Not peer-reviewed. | Compared 128 / 256 / 512 / 1024 / 2048 on one 10-K filing (GPT-3.5 generating, GPT-4 judging). 1024 balanced faithfulness and relevancy best. The numbers are only in an image. | The best size depends on the corpus. Our emails are short (median 401 chars on train, 498 on test; max 3,943 / 1,054), so 1024-token chunks would be whole emails. |
| Jimeno Yepes et al. | Antonio Jimeno Yepes, Yao You, Jan Milczek, Sebastian Laverde, Renyu Li. *Financial Report Chunking for Effective Retrieval Augmented Generation.* arXiv:2402.05131 (2024). Preprint. | Chunking by structural element type (title, table, paragraph) improves RAG on financial reports without tuning a chunk size by hand. | Supports structure-aware units. The nearest analogue for us is sentence boundaries plus BIPIA's injection boundary. |
| Chroma technical report | Brandon Smith, Anton Troynikov. *Evaluating Chunking Strategies for Retrieval.* Chroma Technical Report, 3 Jul 2024. Not peer-reviewed. | Strategy changes recall by up to about 9 points. Small chunks (about 200 tokens, no overlap) give the best precision/IoU; larger chunks raise recall but lower precision. The default 800-token chunk with 400 overlap had the worst precision and IoU. | Small, non-overlapping units are efficient. This is the same direction as our sentence-level choice: dropping a small unit wastes less clean text. |
| Qu, Tu, Bao | Renyi Qu, Ruixuan Tu, Forrest Bao. *Is Semantic Chunking Worth the Computational Cost?* arXiv:2410.13070 (2024). Preprint. | Semantic chunking's extra compute is not justified by consistent gains over fixed-size chunking. | Supports simple, deterministic chunkers (Punkt sentences or fixed size) over embedding- or LLM-based semantic chunking. |

## B. Granularity in prompt-injection detection and removal

| Source | Verified citation | Finding | Implication for us |
|---|---|---|---|
| BIPIA | Jingwei Yi, Yueqi Xie, Bin Zhu, Emre Kiciman, Guangzhong Sun, Xing Xie, Fangzhao Wu. *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models.* arXiv:2312.14197; KDD 2025 (per arXiv comments). | Benchmark of injections inserted at the start, middle or end of external content. Defences are boundary awareness and explicit reminder. Default evaluation LLM is `gpt35` (`config/gpt35.yaml`); the repo ships both system-prompt and no-system (`gpt35_wosys`, `gpt4_wosys`) configs. | Source of our data, insertion functions, prompt templates and per-attack evaluators. BIPIA inserts the attack as its own line, so the injection boundary coincides with a sentence boundary. |
| Chen et al. 2025 | Yulin Chen, Haoran Li, Yuan Sui, Yufei He, Yue Liu, Yangqiu Song, Bryan Hooi. *Can Indirect Prompt Injection Attacks Be Detected and Removed?* arXiv:2502.16580; ACL 2025 (Main). | Studies detection and removal. One removal method segments the document and drops segments with injected instructions; the other extracts them. Segment-level performance is **not checked** from the full text. | The closest prior work to our "chunk, score, drop" defence. Cite it as related work for segment-level removal. |
| PromptLocate | Yuqi Jia, Yupei Liu, Zedian Shao, Jinyuan Jia, Neil Zhenqiang Gong. *PromptLocate: Localizing Prompt Injection Attacks.* arXiv:2510.12252; to appear at IEEE S&P 2026 (per arXiv comments). | Splits contaminated data into semantically coherent segments, then locates the injected-instruction and injected-data segments. | Supports localisation at segment level rather than whole documents. A stronger localiser than per-chunk PIGuard. |
| PIGuard | Hao Li, Xiaogeng Liu, Ning Zhang, Chaowei Xiao. *PIGuard: Prompt Injection Guardrail via Mitigating Overdefense for Free.* ACL 2025 (Long), pp. 30420–30437, doi:10.18653/v1/2025.acl-long.1468. Earlier arXiv version: Hao Li, Xiaogeng Liu, *InjecGuard: Benchmarking and Mitigating Over-defense in Prompt Injection Guardrail Models*, arXiv:2410.22770. | DeBERTa-v3 classifier trained to reduce trigger-word over-defence (NotInject benchmark). It outputs one label per input and does no localisation. | It is our risk scorer, so granularity is chosen by us. Very short inputs give it little context; this motivated the window scoring. |
| DataSentinel | Yupei Liu, Yuqi Jia, Jinyuan Jia, Dawn Song, Neil Zhenqiang Gong. *DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks.* arXiv:2504.11358; IEEE S&P 2025 (Distinguished Paper, per arXiv page). | An LLM-based detector fine-tuned with minimax training against adaptive attacks. It detects whether an input is contaminated; it does not localise. | A possible alternative detector. It is document-level, so it would need the same chunking or windowing as PIGuard. |
| PromptArmor **(secondary)** | arXiv:2507.15219, *PromptArmor: Simple yet Effective Prompt Injection Defenses* (Shi et al.; author list not checked). | An off-the-shelf LLM finds and removes injected prompts before the agent sees the input. Reported FPR/FNR are below 1% on AgentDojo. | An LLM-based removal baseline. Too costly for our serial H200 budget. |

## What this means for our design

1. Sentence-level chunks for the defence are consistent with segment-level removal work (Chen et al. 2025; PromptLocate) and with the small-unit efficiency result (Chroma). Simple splitting is supported over semantic chunking (Qu et al.).
2. Retrieval granularity and defence granularity are separate choices. We retrieve whole emails, which is how the poisoned email is found through its clean content, and defend at sentence level.
3. A single-label classifier such as PIGuard needs enough context. Our window scoring (previous + current + next chunk) is a pragmatic answer; it is not taken from a paper.

## C. Reported BIPIA attack success rates (reference point for our B0)

Source: Yi et al., arXiv:2312.14197 v4 (HTML version, checked 2026-10-09), Table 2, "Attack success rates (ASRs) of different LLMs on BIPIA". Values are proportions.

| Model | Email QA ASR | Overall ASR (all tasks) |
|---|---|---|
| GPT-4 | 0.1524 | 0.3103 |
| GPT-3.5-turbo | 0.1634 | 0.2616 |
| Llama2-Chat-70B | 0.1290 | 0.1867 |
| Vicuna-33B | 0.1088 | 0.1617 |
| Vicuna-13B | 0.1036 | 0.1294 |
| Vicuna-7B | 0.0854 | 0.1049 |
| Mistral-7B | 0.0552 | 0.0966 |
| Average over all evaluated models | 0.0730 | 0.1179 |

- **Evaluator:** the paper says evaluation combines rule-based checks, LLM-as-judge and langdetect, without naming the judge model in the text. The repository README sets the evaluation LLM default to `gpt35` (`--gpt_config_file config/gpt35.yaml`).
- **Insertion position (figure only, no numbers in the text):** ASR is highest when the attack is at the end, then the start, then the middle.
- **System prompt:** the paper uses each model's documented conversation template, at temperature 0. It does not report system vs no-system results; the repository provides both `gpt35`/`gpt4` and `gpt35_wosys`/`gpt4_wosys` configs.
- **Comparison with our B0:** our main-Test B0 ASR is 30/300 = 10.0% (Qwen2.5-VL-32B, RAG over retrieved emails, judge = 72B).
  - This is in the same range as BIPIA's Email QA numbers (5.5–16.3%).
  - It is not directly comparable. BIPIA puts the full attacked email in the prompt; our retrieval sometimes misses the target email (attack text in context 265/300), and our judge differs from theirs.
  - Our start > end > middle position pattern differs from BIPIA's end > start > middle (B0: start 20/101, end 6/100, middle 4/99).
