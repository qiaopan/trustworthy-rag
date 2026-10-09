# Report and presentation writing plan

This page turns the course brief into a reproducible writing checklist. It is
deliberately separate from the experiment log: experimental numbers are only
copied into the paper after the raw-PIGuard B2 Main-Test run and the audit are
complete.

## Deliverables and constraints

| Deliverable | Course requirement | Repository artifact |
|---|---|---|
| Final report | IEEE PDF; 10--12 pages excluding references; abstract 150--200 words; at least 10 references | `paper/main.tex` |
| Oral presentation | One 8--10 minute MP4; two speakers contribute 4--5 minutes each | `presentation/SCRIPT_AND_OUTLINE.md`, then a student-edited slide deck |

The report must contain Title, Author, Abstract, Introduction, Related Work,
Methodology, Implementation/Results, Conclusion/Future Work, References, and
a pair contribution breakdown. Methodology is the highest-weighted section.
The presentation must make the problem, why it matters, existing solutions,
our extension, results, and conclusion clear.

## Evidence rules for writing

1. The primary result is only the frozen, system-template Main Test: 300
   attacked cases plus 20 clean cases.
2. The 100-case pilot is an infrastructure/stability gate. It is never pooled
   with the Main Test or used to make a headline effectiveness claim.
3. The 45-case test-split follow-up is post-main and supplementary. It tests
   method/template robustness and must not be described as tuning Dev data.
4. Call the historical window-scored defence **B2-win**, not B2. **B2 (raw)**
   is the original chunk-level PIGuard hard filter and remains pending for the
   Main Test at the time this draft was created.
5. Report `n/N`, Wilson confidence intervals, and denominators: attacked
   security metrics `n=300`; answer-bearing retention `n=120`; clean utility
   `n=20`; abstention `n=320`.
6. The context-conflict signal made no selection difference in the frozen
   implementation. Do not claim it creates a benefit. B3 is a stricter,
   risk-only threshold comparison, not a "soft reranker."
7. The automatic judge is Qwen2.5-VL-72B-AWQ in place of BIPIA's GPT-3.5.
   UNKNOWN is counted as not successful in the primary result. Any human
   check is a separately-labelled sensitivity analysis, never a silent relabel.

## Writing order

1. Claude Code finishes raw B2, recomputes metrics, and locks the audit.
2. Copy the locked table and intervals into `paper/main.tex`; remove all
   `TBD` markers that concern results.
3. Add at least one result figure (security--utility comparison) generated
   from the locked metric JSON, not hand-entered values.
4. Each student rewrites and fact-checks their own sections, fills author
   names and contribution breakdown, then compiles the IEEE PDF.
5. Turn the storyboard and speaker notes into the recorded slide deck; rehearse
   once against an 8--10 minute timer before recording the MP4.

## Suggested ownership (edit to match reality)

| Workstream | Student 1 | Student 2 |
|---|---|---|
| Literature review and motivation | `TBD` | `TBD` |
| Implementation and reproducibility | `TBD` | `TBD` |
| Experiment verification and audit | `TBD` | `TBD` |
| Results interpretation and presentation | `TBD` | `TBD` |

Replace the placeholders with the factual division before submission.
