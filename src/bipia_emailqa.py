"""BIPIA EmailQA adapter: manifest record -> RAG case with a labelled passage pool.

Poisoning uses BIPIA's own code (``bipia.data.utils.insert_start/middle/end``,
``middle`` = a seeded random Punkt sentence boundary) and BIPIA's
``EmailIPIABuilder`` prompt template.  Nothing here reimplements insertion.

RAG pool construction (per case; documented because results depend on it):

1. ``support``: the *clean* target email is split into sentence-aligned chunks
   (Punkt spans, <= ``CHUNK_CHARS``).  These are the clean supporting passages;
   ``answer_bearing`` marks a chunk containing BIPIA's ``ideal`` string.
2. ``poisoned`` (attack cases only): BIPIA's insertion function is applied to
   the full clean email with ``random_state=seed``.  Default ``pool_mode=
   "replace"``: the clean chunk containing BIPIA's insertion point is *replaced*
   by that chunk with the attack inserted at the same offset (the injection
   lives inside the only copy, so dropping it can also drop clean text, possibly
   the answer; ``answer_bearing`` is carried over).  ``pool_mode="duplicate"``
   (legacy) instead adds the attack plus up to ``WINDOW_CHARS`` of surrounding
   text as an extra passage and keeps every clean chunk.
3. ``distractor``: chunks of ``N_DISTRACTOR_EMAILS`` other EmailQA emails from
   the manifest's source split,
   chosen with ``random.Random(seed + context_index)``; emails whose text equals
   the target are excluded.

Clean cases (``label='clean'``) use the identical pool without step 2.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BIPIA_DIR = ROOT / "third_party/BIPIA"
BENCHMARK_DIR = BIPIA_DIR / "benchmark"
if str(BIPIA_DIR) not in sys.path:
    sys.path.insert(0, str(BIPIA_DIR))

from bipia.data import EmailIPIABuilder  # noqa: E402
from bipia.data.utils import insert_end, insert_middle, insert_start  # noqa: E402
from nltk.tokenize.punkt import PunktSentenceTokenizer  # noqa: E402

INSERT_FNS = {"start": insert_start, "middle": insert_middle, "end": insert_end}
CHUNK_CHARS = 300
WINDOW_CHARS = 200
N_DISTRACTOR_EMAILS = 4
NO_CONTEXT = "[No trusted email content available.]"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Passage:
    pid: str
    text: str
    kind: str  # support | poisoned | distractor
    answer_bearing: bool = False


@dataclass
class Case:
    case_id: str
    label: str  # attack | clean
    context_index: int
    attack_family: str | None
    attack_index: int | None
    insertion_position: str | None
    seed: int
    question: str
    ideal: str
    attack: str | None
    poisoned_context: str | None
    pool: list[Passage] = field(default_factory=list)

    def meta(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in (
            "case_id", "label", "context_index", "attack_family", "attack_index", "insertion_position", "seed")}


def load_benchmark(benchmark_dir: Path = BENCHMARK_DIR, split: str = "train") -> tuple[list[dict], dict[str, list[str]]]:
    """Load one BIPIA split.  Dev uses ``train``; held-out evaluation uses ``test``."""
    if split not in {"train", "test"}:
        raise ValueError(f"Unsupported BIPIA split: {split}")
    contexts = [json.loads(line) for line in (benchmark_dir / f"email/{split}.jsonl").read_text().splitlines() if line]
    return contexts, json.loads((benchmark_dir / f"text_attack_{split}.json").read_text())


def chunk_spans(text: str, max_chars: int = CHUNK_CHARS) -> list[tuple[int, int]]:
    """Greedy merge of Punkt sentence spans into contiguous spans covering ``text``."""
    spans = list(PunktSentenceTokenizer().span_tokenize(text)) or [(0, len(text))]
    bounds, start, end = [], 0, spans[0][0]
    for s, e in spans:
        if e - start > max_chars and end > start:
            bounds.append((start, s))
            start = s
        end = e
    bounds.append((start, len(text)))
    return [(a, b) for a, b in bounds if text[a:b].strip()]


def chunk(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    return [text[a:b].strip() for a, b in chunk_spans(text, max_chars)]


def insertion_offset(poisoned: str, attack: str) -> int:
    """Clean-text offset of BIPIA's insertion ("\n".join puts one newline before the attack)."""
    at = poisoned.index(attack)
    return at - 1 if at > 0 else 0


def _trim(text: str, n: int, keep_tail: bool) -> str:
    if len(text) <= n:
        return text
    cut = text[-n:] if keep_tail else text[:n]
    parts = cut.split(" ", 1) if keep_tail else cut.rsplit(" ", 1)
    return (parts[-1] if keep_tail else parts[0]) if len(parts) == 2 else cut


def poisoned_window(poisoned: str, attack: str) -> str:
    at = poisoned.index(attack)
    before = _trim(poisoned[:at], WINDOW_CHARS, keep_tail=True).strip()
    after = _trim(poisoned[at + len(attack):], WINDOW_CHARS, keep_tail=False).strip()
    return "\n".join(part for part in (before, attack, after) if part)


def build_case(record: dict, contexts: list[dict], attacks: dict[str, list[str]], clean: bool = False,
               pool_mode: str = "replace") -> Case:
    idx, seed = record["context_index"], record["seed"]
    sample = contexts[idx]
    case = Case(
        case_id=record["case_id"] + ("-clean" if clean else ""), label="clean" if clean else "attack",
        context_index=idx, attack_family=None if clean else record["attack_family"],
        attack_index=None if clean else record["attack_index"],
        insertion_position=None if clean else record["insertion_position"], seed=seed,
        question=sample["question"], ideal=sample["ideal"], attack=None, poisoned_context=None)
    ideal = sample["ideal"] if sample["ideal"] not in ("unknown", "unkown") else None
    text = sample["context"]
    spans = chunk_spans(text)
    for j, (a, b) in enumerate(spans):
        case.pool.append(Passage(f"e{idx}-c{j}", text[a:b].strip(), "support", bool(ideal and ideal in text[a:b])))
    if not clean:
        case.attack = attacks[record["attack_family"]][record["attack_index"]]
        case.poisoned_context = INSERT_FNS[record["insertion_position"]](text, case.attack, random_state=seed)
        if pool_mode == "duplicate":
            case.pool.append(Passage(f"e{idx}-poison", poisoned_window(case.poisoned_context, case.attack), "poisoned"))
        elif pool_mode == "replace":
            off = insertion_offset(case.poisoned_context, case.attack)
            j = next((i for i, (a, b) in enumerate(spans) if a <= off < b), len(spans) - 1)
            a, b = spans[j]
            # Same join as BIPIA's insert fns, restricted to the chunk that holds the insertion point.
            body = "\n".join(p for p in (text[a:off].strip(), case.attack, text[off:b].strip()) if p)
            old = case.pool[j]
            case.pool[j] = Passage(f"e{idx}-c{j}-poison", body, "poisoned", old.answer_bearing)
        else:
            raise ValueError(pool_mode)
    others = [i for i in range(len(contexts)) if i != idx and contexts[i]["context"] != sample["context"]]
    for d in sorted(random.Random(seed + idx).sample(others, N_DISTRACTOR_EMAILS)):
        for j, text in enumerate(chunk(contexts[d]["context"])):
            case.pool.append(Passage(f"e{d}-c{j}", text, "distractor"))
    return case


def manifest_split(header: dict) -> str:
    """Infer and validate the source split from the versioned manifest header."""
    for split in ("train", "test"):
        if {f"email_{split}_sha256", f"text_attack_{split}_sha256"} <= set(header):
            return split
    raise ValueError("Manifest header does not identify a BIPIA source split")


def check_manifest_checksums(header: dict, benchmark_dir: Path = BENCHMARK_DIR) -> str:
    split = manifest_split(header)
    for key, rel in ((f"email_{split}_sha256", f"email/{split}.jsonl"), (f"text_attack_{split}_sha256", f"text_attack_{split}.json")):
        if hashlib.sha256((benchmark_dir / rel).read_bytes()).hexdigest() != header.get(key):
            raise ValueError(f"BIPIA {rel} checksum does not match manifest header; aborting")
    return split


def load_cases(manifest: Path, include_clean: bool = False, attacked: bool = True, pool_mode: str = "replace") -> list[Case]:
    rows = [json.loads(line) for line in manifest.read_text().splitlines() if line]
    split = check_manifest_checksums(rows[0])
    contexts, attacks = load_benchmark(split=split)
    records = [row for row in rows if "case_id" in row]
    cases = [build_case(r, contexts, attacks, pool_mode=pool_mode) for r in records] if attacked else []
    if include_clean:
        cases += [build_case(r, contexts, attacks, clean=True) for r in records]
    return cases


def build_messages(question: str, passages: list[str]) -> list[dict[str, str]]:
    """BIPIA EmailIPIABuilder prompt (system-prompt variant) over the selected passages."""
    context = "\n\n".join(passages) if passages else NO_CONTEXT
    system, user = EmailIPIABuilder(seed=0).construct_prompt({"context": context, "question": question})
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
