# Experiment manifests

Manifests are small, version-controlled references into BIPIA; they do not
copy BIPIA contexts or attack strings. Each manifest begins with a JSON header
record carrying the source-file checksums, followed by one record per case.

`emailqa_dev_30.jsonl` is the fixed development set. It has 30 attacked EmailQA
cases: two from each of BIPIA's 15 text-attack families, 10 insertions at each
of `start`, `middle`, and `end`, and 30 distinct clean email contexts. It is for
selecting the proposed-method parameters only. It draws solely from BIPIA's
training split; never report it as the main test result.

Build or verify it offline after bootstrapping BIPIA:

```bash
PYTHONPATH=. python scripts/build_emailqa_dev_manifest.py
PYTHONPATH=. python scripts/build_emailqa_dev_manifest.py --check
```

The command is deterministic. `--check` also fails when the local BIPIA source
files differ from the revision used to create the manifest.

`emailqa_test_followup_dev_45.jsonl` is a supplementary 45-case development
set drawn from the BIPIA test split: one case per attack-family/insertion-position
cell. It is disjoint from the frozen pilot and main Test manifests. It was added
after the original main Test completed, so it may only support clearly labelled
follow-up analyses; it is not evidence for tuning or reinterpreting the frozen
main result.
