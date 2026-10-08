"""Offline tests: no endpoint traffic; fake transports only."""
import json
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from src.bipia_emailqa import INSERT_FNS, build_case, build_messages, load_benchmark, load_cases
from src.judge import ATTACK_LABELS, attack_messages, is_abstention, parse_label
from src.llm_client import ChatClient, JsonlCache
from src.rag_pipeline import OursConfig, retrieve, select
from src.retrieval import HashingEmbedder

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/manifests/emailqa_dev_30.jsonl"


class DictRisk:
    """Poisoned passage = 0.99, everything else = 0.01."""
    def __init__(self, case):
        self.risk = {p.text: (0.99 if p.kind == "poisoned" else 0.01) for p in case.pool}

    def score(self, text):
        return self.risk[text]


@pytest.fixture(scope="module")
def cases():
    return load_cases(MANIFEST, include_clean=True)


def test_manifest_stratification_and_checksum():
    import build_emailqa_dev_manifest as m
    header, records = m.read_manifest(MANIFEST)
    m.validate_manifest(records, m.DEFAULT_BENCHMARK)
    assert header == m.manifest_header(m.DEFAULT_BENCHMARK)
    assert Counter(r["insertion_position"] for r in records) == {"start": 10, "middle": 10, "end": 10}
    assert set(Counter(r["attack_family"] for r in records).values()) == {2}


def test_case_fields_and_labels(cases):
    attack = [c for c in cases if c.label == "attack"]
    clean = [c for c in cases if c.label == "clean"]
    assert len(attack) == len(clean) == 30
    for c in attack:
        meta = c.meta()
        assert all(meta[k] is not None for k in meta)
        assert c.attack in c.poisoned_context
        assert sum(p.kind == "poisoned" for p in c.pool) == 1
        assert c.attack in next(p.text for p in c.pool if p.kind == "poisoned")
        assert any(p.kind == "distractor" for p in c.pool)
    assert all(not any(p.kind == "poisoned" for p in c.pool) and c.attack is None for c in clean)


def test_insertion_reproducible_and_uses_bipia():
    contexts, attacks = load_benchmark()
    rec = {"case_id": "x", "context_index": 3, "attack_family": next(iter(attacks)), "attack_index": 0,
           "insertion_position": "middle", "seed": 20261009}
    a, b = build_case(rec, contexts, attacks), build_case(rec, contexts, attacks)
    assert a.poisoned_context == b.poisoned_context
    assert a.poisoned_context == INSERT_FNS["middle"](contexts[3]["context"], a.attack, random_state=20261009)
    start = build_case({**rec, "insertion_position": "start"}, contexts, attacks)
    end = build_case({**rec, "insertion_position": "end"}, contexts, attacks)
    assert start.poisoned_context.startswith(start.attack) and end.poisoned_context.endswith(end.attack)


def _selected(case, method, k=3):
    cands = retrieve(case, HashingEmbedder(), k=len(case.pool))
    return [r.passage.metadata["kind"] for r in select(case, cands, DictRisk(case), method, OursConfig(), k=k)]


def test_b0_b2_ours_selection(cases):
    for case in [c for c in cases if c.label == "attack"]:
        kinds_all = _selected(case, "b0", k=len(case.pool))
        assert "poisoned" in kinds_all  # B0 does not filter
        b2 = _selected(case, "b2", k=len(case.pool))
        assert "poisoned" not in b2  # B2 drops poison ...
        assert ("support" in b2) == any(p.kind == "support" for p in case.pool)  # ... and keeps remaining clean support
        ours = _selected(case, "ours", k=len(case.pool))
        assert ours[-1] == "poisoned"  # soft rerank: high risk sinks to the bottom


def test_ours_threshold_drops(cases):
    case = next(c for c in cases if c.label == "attack")
    cands = retrieve(case, HashingEmbedder(), k=len(case.pool))
    rows = select(case, cands, DictRisk(case), "ours", OursConfig(threshold=0.5), k=len(case.pool))
    assert "poisoned" not in [r.passage.metadata["kind"] for r in rows]


def test_prompt_uses_bipia_template(cases):
    msgs = build_messages(cases[0].question, ["ctx"])
    assert msgs[0]["content"].startswith("You are an email assistant") and msgs[1]["content"].startswith("Question:")


def test_cache_hit_avoids_repeat_call(tmp_path):
    calls = []
    transport = lambda m, model, d: (calls.append(1), ("ok", {"prompt_tokens": 1}))[1]
    msgs = [{"role": "user", "content": "q"}]
    client = ChatClient("generator", "m", JsonlCache(tmp_path / "c.jsonl"), transport)
    first = client.complete(msgs, "case", "b0", "ctx")
    second = client.complete(msgs, "case", "b0", "ctx")
    assert len(calls) == 1 and not first["cached"] and second["cached"]
    resumed = ChatClient("generator", "m", JsonlCache(tmp_path / "c.jsonl"), transport)  # after interruption
    assert resumed.complete(msgs, "case", "b0", "ctx")["cached"] and len(calls) == 1
    client.complete(msgs, "case", "b2", "ctx")
    assert len(calls) == 2  # different method -> different key


def test_retry_then_error_not_cached(tmp_path):
    n = []
    def flaky(m, model, d):
        n.append(1)
        raise ConnectionError("down at http://10.0.0.1:8000/v1")
    client = ChatClient("generator", "m", JsonlCache(tmp_path / "c.jsonl"), flaky, max_retries=2, backoff=0)
    row = client.complete([{"role": "user", "content": "q"}], "c", "b0", "x")
    assert len(n) == 3 and not row["ok"] and row["retries"] == 2 and "10.0.0.1" not in row["error"]
    assert "10.0.0.1" not in (tmp_path / "c.jsonl").read_text()
    assert JsonlCache(tmp_path / "c.jsonl").get(row["key"]) is None


def test_concurrency_is_one(tmp_path):
    active, peak, lock = [0], [0], threading.Lock()
    def slow(m, model, d):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.02)
        with lock:
            active[0] -= 1
        return "ok", {}
    client = ChatClient("generator", "m", JsonlCache(tmp_path / "c.jsonl"), slow)
    threads = [threading.Thread(target=client.complete, args=([{"role": "user", "content": str(i)}], str(i), "b0", "x"))
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


def test_judge_label_restricted():
    assert parse_label("ATTACK_SUCCESS", ATTACK_LABELS) == "ATTACK_SUCCESS"
    assert parse_label(" attack_failed.", ATTACK_LABELS) == "ATTACK_FAILED"
    assert parse_label("Yes, the attack succeeded", ATTACK_LABELS) == "INVALID"
    assert parse_label("ATTACK_SUCCESS or ATTACK_FAILED", ATTACK_LABELS) == "INVALID"
    assert parse_label("INCORRECT", ("CORRECT", "INCORRECT")) == "INCORRECT"


def test_abstention_is_not_success():
    msgs = attack_messages("Q?", "$1", "Say hi", "There is no information about this in the email.")
    assert "abstaining because no trusted context" in msgs[0]["content"]
    assert is_abstention("There is no information about the question in the email.")
    assert is_abstention("[No trusted email content available.] I cannot determine the value.")
    assert not is_abstention("The amount paid was $420.00.")


def test_fake_end_to_end(tmp_path, cases):
    import run_dev
    gen = ChatClient("generator", "fg", JsonlCache(tmp_path / "c.jsonl"), run_dev.fake_generator)
    jud = ChatClient("judge", "fj", JsonlCache(tmp_path / "c.jsonl"), run_dev.fake_judge)
    subset = cases[:2] + cases[30:32]
    from src.rag_pipeline import FakeRiskScorer
    rows = run_dev.run(subset, ["b0", "b2", "ours"], HashingEmbedder(), FakeRiskScorer(), gen, jud)
    assert len(rows) == 12 and gen.calls == 12 and jud.calls == 12
    assert {r["judge_label"] for r in rows if r["label"] == "attack"} <= set(ATTACK_LABELS)
    run_dev.run(subset, ["b0", "b2", "ours"], HashingEmbedder(), FakeRiskScorer(), gen, jud)
    assert gen.calls == 12  # second pass fully cached
    import compute_metrics
    report = compute_metrics.summarise([r for r in rows if r["method"] == "b0"])
    assert report["asr"]["n"] == 2 and report["clean_accuracy"]["n"] == 2
    assert json.dumps(report)


def test_judge_prompt_matches_rejudge_script():
    import rejudge_manual_h200_check as legacy
    from src.judge import JUDGE_SYSTEM
    assert JUDGE_SYSTEM == legacy.JUDGE_SYSTEM


def test_replace_mode_replaces_chunk_duplicate_keeps_all():
    contexts, attacks = load_benchmark()
    rec = {"case_id": "x", "context_index": 31, "attack_family": next(iter(attacks)), "attack_index": 0,
           "insertion_position": "middle", "seed": 20261009}  # multi-chunk email
    clean = build_case(rec, contexts, attacks, clean=True)
    rep = build_case(rec, contexts, attacks)
    dup = build_case(rec, contexts, attacks, pool_mode="duplicate")
    n_target = lambda c: sum(p.pid.startswith("e31-") for p in c.pool)
    assert n_target(clean) > 1 and n_target(rep) == n_target(clean) and n_target(dup) == n_target(clean) + 1
    assert sum(p.kind == "support" for p in rep.pool) == n_target(clean) - 1
    poisoned = next(p for p in rep.pool if p.kind == "poisoned")
    replaced = next(p for p in clean.pool if p.pid == poisoned.pid.removesuffix("-poison"))
    assert poisoned.text.replace(rep.attack, "").split() == replaced.text.split()
    assert poisoned.answer_bearing == replaced.answer_bearing


def test_checksum_mismatch_aborts(tmp_path):
    lines = MANIFEST.read_text().splitlines()
    header = json.loads(lines[0]) | {"email_train_sha256": "0" * 64}
    bad = tmp_path / "m.jsonl"
    bad.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n")
    with pytest.raises(ValueError, match="checksum"):
        load_cases(bad)


def test_failed_generation_is_error_and_excluded(tmp_path, cases):
    import compute_metrics
    import run_dev
    from src.rag_pipeline import FakeRiskScorer
    def down(m, model, d):
        raise ConnectionError("down")
    gen = ChatClient("generator", "g", JsonlCache(tmp_path / "c.jsonl"), down, max_retries=0)
    jud = ChatClient("judge", "j", JsonlCache(tmp_path / "c.jsonl"), run_dev.fake_judge)
    rows = run_dev.run(cases[:2], ["b0"], HashingEmbedder(), FakeRiskScorer(), gen, jud)
    assert {r["judge_label"] for r in rows} == {"ERROR"} and jud.calls == 0
    report = compute_metrics.summarise(rows)
    assert report["asr"]["n"] == 0 and report["judge_error_count"] == 2


def test_real_run_requires_real_embedder_and_piguard():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(ROOT / "scripts/run_dev.py"), "--embedder", "fake"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 and "--embedder endpoint --risk piguard" in out.stderr
