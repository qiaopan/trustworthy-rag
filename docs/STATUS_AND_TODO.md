# Trustworthy RAG: project status and final to-do

Last updated: 2026-10-09.  This is the single short status page for the team.
Read `DECISION_LOG.md` for full methodological rationale and `DECISIONS.md` for
the frozen protocol and reported main-Test results.

## What is already complete

### Reproducible implementation

- BIPIA EmailQA adapter, deterministic manifests, whole-email bge-m3 retrieval,
  sentence-chunk defences, local PIGuard scoring, Qwen generator/judge clients,
  caching/resume, official BIPIA test evaluators, metrics, paired tests and audit
  report tooling are implemented.
- Local validation passes: 30 tests.  No secrets, URLs or endpoint credentials
  are tracked in Git.
- Current branch: `main-test-2026-10-09`; latest source commit at this update is
  `e39af35`.

### Data splits

| Split | Size | Role | Sampling rule | Status |
|---|---:|---|---|---|
| Train Dev | 30 attacked + 30 clean | Initial development only | 15 train attack families x 2; positions 10/10/10 | Complete |
| Pilot | 100 attacked | Infrastructure/stability gate only; never pooled with Test | 45 test family-position cells, 2--3 cases/cell | Complete; intentionally not a headline result |
| Main Test | 300 attacked + 20 clean | Primary frozen result | 45 test family-position cells, 6--7 cases/cell | Complete for B0/B2-win/B3/Ours |
| Follow-up Dev | 45 attacked | Supplementary method/template comparison after main Test | Exactly 1 case per test family-position cell; disjoint from Pilot/Main | Complete |

All attacked splits are disjoint at `(context, family, attack index, insertion
position)`.  The 300-case Main Test is **stratified random sampling**, not a
simple random 300-case draw.  The 20 clean cases contain 10 known-answer and
10 unknown-answer emails.

### Completed real-model runs

- Original train Dev, 30 attacked + 30 clean: completed.
- Pilot, 100 attacked: completed with no infrastructure errors.  Do not combine
  it with Main Test or use it to claim an effect.
- Frozen Main Test, system template, 300 attacked + 20 clean: B0, B2-win,
  Ours, and B3 completed.  Results and provenance are under ignored
  `outputs/test_main/`.
- Follow-up Dev, system template, 45 attacked: B0, raw B2, B2-win, B3, Ours
  completed.
- Follow-up Dev, BIPIA no-system/user template, the same 45 attacked cases and
  methods: completed.

The 45-case follow-up comparison has the same qualitative conclusion under
both templates: raw B2 preserves more answer-bearing content but filters less
aggressively; B2-win removes more attack text but loses more answers; Ours
keeps nearly B2-win-level attack removal while preserving substantially more
answer-bearing content.  It is a supplementary, small-sample check rather
than the primary claim.

## Remaining work

### Required before the final results table

1. **Run raw B2 on the frozen Main Test**: 300 attacked + 20 clean, system
   template, same fixed retrieval and judge.  Raw B2 means original PIGuard:
   score each chunk itself and hard-filter at 0.5.  This is the proper existing
   defense baseline.  The older window-risk result must be named **B2-win**,
   an ablation/our extension.
2. Recompute the final metrics table, Wilson intervals and paired McNemar
   comparisons for `B0 / B2 / B2-win / B3 / Ours`.
3. Review the audit sheet for automatic-judge successes and UNKNOWN outputs.
   Keep the official automatic labels as the primary result; add a separate,
   explicitly labelled human-audit sensitivity row for any confirmed error.
4. Update `DECISIONS.md`, `DECISION_LOG.md`, and `HANDOFF.md` with final raw-B2
   numbers, provenance and the corrected method names.

### Optional, not needed for the course report

- Expand the no-system template to 300 cases only if the 45-case follow-up
  changes the conclusion materially.
- Add a second generator or judge as a separate robustness study.
- Increase clean cases beyond 20 if fine-grained utility differences become a
  central claim.

## Time estimate and writing plan

These are active-work estimates, not a promise about shared-service queueing.

| Milestone | Estimated active time | Outcome |
|---|---:|---|
| Raw-B2 Main Test, serial and cached | 35--60 minutes | Complete primary comparison matrix |
| Recompute tables, paired tests, audit | 45--90 minutes | Final defensible numbers and limitations |
| Update repository documentation | 20--30 minutes | Reproducible handoff |
| Draft Methods + Experiment Setup | Can start now | Does not depend on raw-B2 results |
| Draft Results + Discussion | After the two rows above | Uses final, stable table |

**Writing can start immediately.**  The Methods, benchmark, implementation and
experimental-protocol sections are already fixed.  Once raw B2 and the audit
are complete (roughly one focused work session), the Results/Discussion section
can be written without changing the experimental story.

## Paper-safe claims

- The course handout grades implementation and how conclusions are drawn, not
  whether the proposed method always wins.
- The primary result is the frozen 300 attacked + 20 clean system-template
  Main Test, with raw B2 added before final reporting.
- Pilot and 45-case follow-up Dev results are supplementary and are not pooled
  into the primary Test denominator.
- Clean `n=20` supports a small utility check, not a precise claim that tiny
  clean-accuracy differences are statistically significant.
