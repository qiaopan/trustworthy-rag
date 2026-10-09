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
from src.rag_pipeline import OursConfig, context_texts, retrieve_docs, select_chunks, selection_summary
from src.retrieval import HashingEmbedder

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/manifests/emailqa_dev_30.jsonl"


class DictRisk:
    """Any text containing an attack chunk = 0.99, else 0.01 (works for chunks and windows)."""
    def __init__(self, case):
        self.attack = [p.text for p in case.pool if p.kind == "poisoned"]

    def score(self, text):
        return 0.99 if any(a in text for a in self.attack) else 0.01


class TargetFirst:
    """Fake embedder: the target doc is most similar; distractors orthogonal."""
    def __init__(self, case):
        self.target = next(d.text for d in case.docs if d.kind == "target")
        self.q = case.question

    def encode(self, texts):
        import numpy as np
        return np.array([[1.0, 0.0] if t in (self.target, self.q) else [0.0, 1.0] for t in texts])


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
    assert len(rows) == 12 and gen.calls == 12 and jud.calls <= 12
    assert {r["judge_label"] for r in rows if r["label"] == "attack"} <= {"ATTACK_SUCCESS", "ATTACK_FAILED"}
    assert {r["evaluator_source"] for r in rows if r["label"] == "attack"} == {"ours-train-extension"}
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
    assert report["asr"]["n"] == 2 and report["asr"]["k"] == 0 and report["asr_error_or_invalid"] == 2


def test_real_run_requires_real_embedder_and_piguard():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(ROOT / "scripts/run_dev.py"), "--embedder", "fake"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 and "--embedder endpoint --risk piguard" in out.stderr




def test_case_docs_and_labels(cases):
    attack = [c for c in cases if c.label == "attack"]
    clean = [c for c in cases if c.label == "clean"]
    assert len(attack) == len(clean) == 30
    for c in attack:
        assert all(v is not None for v in c.meta().values())
        target = [d for d in c.docs if d.kind == "target"]
        assert len(target) == 1 and target[0].text == c.poisoned_context  # exactly BIPIA's attacked context
        atk = [p for p in target[0].chunks if p.kind == "poisoned"]
        assert atk and " ".join(p.text for p in atk).split() == c.attack.split()  # attack chunks = attack only
        assert all(c.attack not in p.text for p in target[0].chunks if p.kind == "support")
        assert sum(d.kind == "distractor" for d in c.docs) >= 1
    for c in clean:
        assert not any(p.kind == "poisoned" for p in c.pool) and c.attack is None


def test_chunks_sentence_level():
    from src.bipia_emailqa import chunk
    contexts = load_benchmark(split="train")[0] + load_benchmark(split="test")[0]
    assert max(len(x) for d in contexts for x in chunk(d["context"])) <= 150


def test_doc_retrieval_and_chunk_defences(cases):
    for case in [c for c in cases if c.label == "attack"]:
        emb = TargetFirst(case)
        docs = retrieve_docs(case, emb, k=2)
        assert docs[0][0].kind == "target"
        risk = DictRisk(case)
        b0 = selection_summary(case, docs, select_chunks(case, docs, risk, "b0"))
        b2_rows = select_chunks(case, docs, risk, "b2")
        b2 = selection_summary(case, docs, b2_rows)
        assert b0["malicious_included"] and not b0["attack_removed"]
        assert b2["attack_removed"] and not b2["malicious_included"]
        raw = selection_summary(case, docs, select_chunks(case, docs, risk, "b2", risk_mode="chunk"))
        assert raw["clean_chunks_dropped"] == 0  # raw scoring drops attack chunks only
        assert raw["answer_retained"] == raw["answer_possible"]  # dropping attack sentences never drops the answer
        assert b2["doc_b2_drops_target"]  # doc-level B2 would lose the whole email
        ours = selection_summary(case, docs, select_chunks(case, docs, risk, "ours", OursConfig(keep=-0.2), embedder=emb))
        assert ours["attack_removed"]
        # surviving text preserves doc order and contains no attack text
        ctx = context_texts(docs, b2_rows)
        assert case.attack not in "\n".join(ctx) and ctx[0].split("\n")[0] in docs[0][0].text


def test_ours_hard_cap(cases):
    case = next(c for c in cases if c.label == "attack")
    emb, risk = TargetFirst(case), DictRisk(case)
    docs = retrieve_docs(case, emb, k=2)
    rows = select_chunks(case, docs, risk, "ours", OursConfig(beta=0.0, keep=-10, threshold=0.5), embedder=emb)
    assert not selection_summary(case, docs, rows)["malicious_included"]


def test_window_risk_uses_neighbours(cases):
    from src.bipia_emailqa import risk_windows
    case = next(c for c in cases if c.label == "attack")
    target = next(d for d in case.docs if d.kind == "target")
    wins = risk_windows(target)
    assert len(wins) == len(target.chunks) and target.chunks[0].text in wins[0]
    if len(target.chunks) > 2:
        assert wins[1] == "\n".join(c.text for c in target.chunks[:3])

    class WindowOnly:  # window containing attack text is risky; raw chunks are not
        def score(self, text):
            return 0.99 if "\n" in text and case.attack.split()[0] in text else 0.0
    docs = retrieve_docs(case, TargetFirst(case), k=1)
    win = selection_summary(case, docs, select_chunks(case, docs, WindowOnly(), "b2", risk_mode="window"))
    raw = selection_summary(case, docs, select_chunks(case, docs, WindowOnly(), "b2", risk_mode="chunk"))
    assert not raw["attack_removed"]
    assert win["attack_removed"] or len(target.chunks) == 1


def test_user_template_is_bipia_no_system_variant(cases):
    from bipia.data import EmailIPIABuilder
    msgs = build_messages(cases[0].question, ["ctx"], template="user")
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert msgs[0]["content"] == EmailIPIABuilder(seed=0).construct_prompt(
        {"context": "ctx", "question": cases[0].question}, require_system_prompt=False)
    assert "ctx" in msgs[0]["content"] and msgs[0]["content"].rstrip().endswith(cases[0].question)


def test_distractors_exclude_question_entity(cases):
    from src.bipia_emailqa import question_entity
    assert question_entity("Q: Find the $ value paid to Air Canada? If multiple, record all.") == "Air Canada"
    assert question_entity("Q: Find the $ value paid by Barlow & Williams? If multiple") == "Barlow & Williams"
    for c in cases:
        for d in c.docs:
            if d.kind == "distractor" and c.entity:
                assert c.entity.lower() not in d.text.lower()


def test_metrics_reject_duplicate_rows(tmp_path):
    import subprocess
    import sys
    row = json.dumps({"case_id": "a", "method": "b0", "label": "attack", "selection": {}})
    f = tmp_path / "r.jsonl"
    f.write_text(row + "\n" + row + "\n")
    out = subprocess.run([sys.executable, str(ROOT / "scripts/compute_metrics.py"), str(f)], capture_output=True, text=True)
    assert out.returncode != 0 and "duplicate" in out.stderr


def test_test_manifests_check_and_disjoint():
    import build_emailqa_test_manifests as t
    m = t.build()
    t.validate(m)
    for subset, name in t.FILES.items():
        lines = (t.OUT / name).read_text().splitlines()
        assert json.loads(lines[0]) == t.header(subset) and len(lines) - 1 == len(m[subset])
    known = [r for r in m["clean"] if load_benchmark(split="test")[0][r["context_index"]]["ideal"] != "unknown"]
    assert len(known) == 10


def test_mcnemar_exact():
    from paired_compare import mcnemar_exact
    assert mcnemar_exact(0, 0) == 1.0
    assert abs(mcnemar_exact(0, 5) - 0.0625) < 1e-12
    assert abs(mcnemar_exact(2, 8) - 0.109375) < 1e-9


def test_b2raw_uses_per_chunk_risk(cases):
    case = next(c for c in cases if c.label == "attack")
    docs = retrieve_docs(case, TargetFirst(case), k=1)

    class WindowOnly:
        def score(self, text):
            return 0.99 if "\n" in text and case.attack.split()[0] in text else 0.0
    raw = select_chunks(case, docs, WindowOnly(), "b2raw")  # default risk_mode is window, b2raw must override
    win = select_chunks(case, docs, WindowOnly(), "b2")
    assert all(r.kept for r in raw)
    assert sum(not r.kept for r in win) >= sum(not r.kept for r in raw)


def test_b3_is_explicit_risk_only_alias(cases):
    case = next(c for c in cases if c.label == "attack")
    docs = retrieve_docs(case, TargetFirst(case), k=1)
    scorer = DictRisk(case)
    cfg = OursConfig(alpha=1.0, beta=0.8, gamma=0.4, keep=-0.2)
    b3 = select_chunks(case, docs, scorer, "b3", cfg, embedder=HashingEmbedder())
    explicit = select_chunks(case, docs, scorer, "ours", OursConfig(0.0, 0.8, 0.0, -0.2), embedder=HashingEmbedder())
    assert [row.kept for row in b3] == [row.kept for row in explicit]


def test_b2doc_drops_whole_email(cases):
    case = next(c for c in cases if c.label == "attack")
    docs = retrieve_docs(case, TargetFirst(case), k=2)
    risky = DictRisk(case)  # any text containing attack chunk text -> 0.99, so the target email is flagged
    rows = select_chunks(case, docs, risky, "b2doc")
    target = next(d.did for d in case.docs if d.kind == "target")
    assert all(not r.kept for r in rows if r.doc_id == target)
    assert all(r.kept for r in rows if r.doc_id != target)
