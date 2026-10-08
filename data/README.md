# Data policy

Do not commit downloaded benchmark copies or model weights. BIPIA source and usage instructions are in `../third_party/BIPIA/`. Start with the EmailQA task and record each run's task, split, seed, model revisions, and defense hyperparameters under `outputs/`.

The checked-in `manifests/` directory is an exception only in the sense that it
contains **references** (indices, family names, and source hashes), never the
benchmark's context or attack text. It fixes the Dev split before H200 calls are
made and makes the sampling protocol reviewable.
