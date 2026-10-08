"""BIPIA EmailQA adapter: manifest record -> RAG case with a labelled passage pool.

Poisoning uses BIPIA's own code (``bipia.data.utils.insert_start/middle/end``,
``middle`` = a seeded random Punkt sentence boundary) and BIPIA's
``EmailIPIABuilder`` prompt template.  Nothing here reimplements insertion.

RAG construction (document-level retrieval, sentence-level defence):

* Retrieval unit = one whole email.  The pool of documents per case is the
  target email -- for attack cases exactly BIPIA's attacked context (official
  insertion fn on the full email, ``random_state=seed``) -- plus
  ``N_DISTRACTOR_EMAILS`` other emails of the same split chosen with
  ``random.Random(seed + context_index)`` (emails identical to the target, and
  emails mentioning the question's entity, are excluded; exclusions recorded).  The poisoned email is therefore retrieved by its clean content.
* Each document is split into sentence-level chunks (1-2 Punkt sentences,
  ~<= ``CHUNK_CHARS``).  For the attacked email the text before the attack, the
  attack itself, and the text after it are chunked separately (BIPIA joins them
  with newlines), so every chunk is either pure attack (``poisoned``) or pure
  clean text (``support``); distractor chunks are ``distractor``.
  ``answer_bearing`` marks clean chunks containing BIPIA's ``ideal`` string.
* Defences act on chunks inside the retrieved documents; the surviving chunks
  are passed to the generator in document order.

Clean cases (``label='clean'``) use the unpoisoned target email.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
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
CHUNK_CHARS = 150
MAX_SENTENCES = 2
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


@dataclass(frozen=True)
class Doc:
    did: str
    kind: str  # target | distractor
    text: str
    chunks: tuple[Passage, ...]


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
    split: str = "train"
    pool: list[Passage] = field(default_factory=list)  # all chunks of all docs (for scoring/caching)
    docs: list["Doc"] = field(default_factory=list)
    entity: str | None = None
    excluded_distractors: list[int] = field(default_factory=list)

    def meta(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in (
            "case_id", "label", "split", "context_index", "attack_family", "attack_index", "insertion_position", "seed",
            "entity", "excluded_distractors")}
        return {**out, "ideal_known": self.ideal not in ("unknown", "unkown")}


def load_benchmark(benchmark_dir: Path = BENCHMARK_DIR, split: str = "train") -> tuple[list[dict], dict[str, list[str]]]:
    """Load one BIPIA split.  Dev uses ``train``; held-out evaluation uses ``test``."""
    if split not in {"train", "test"}:
        raise ValueError(f"Unsupported BIPIA split: {split}")
    contexts = [json.loads(line) for line in (benchmark_dir / f"email/{split}.jsonl").read_text().splitlines() if line]
    return contexts, json.loads((benchmark_dir / f"text_attack_{split}.json").read_text())


def _split_long(text: str, a: int, b: int, max_chars: int) -> list[tuple[int, int]]:
    """Split one over-long sentence span at whitespace so pieces stay <= max_chars."""
    out = []
    while b - a > max_chars:
        cut = text.rfind(" ", a + 1, a + max_chars)
        cut = cut if cut > a else a + max_chars
        out.append((a, cut))
        a = cut
    return out + [(a, b)]


def chunk_spans(text: str, max_chars: int = CHUNK_CHARS, max_sentences: int = MAX_SENTENCES) -> list[tuple[int, int]]:
    """Contiguous spans covering ``text``: 1-``max_sentences`` Punkt sentences, <= ~``max_chars``."""
    sents = list(PunktSentenceTokenizer().span_tokenize(text)) or [(0, len(text))]
    sents = [(0 if i == 0 else a, sents[i + 1][0] if i + 1 < len(sents) else len(text)) for i, (a, _) in enumerate(sents)]
    pieces = [p for a, b in sents for p in _split_long(text, a, b, max_chars)]
    bounds, start, count = [], pieces[0][0], 0
    for a, b in pieces:
        if count and (b - start > max_chars or count >= max_sentences):
            bounds.append((start, a))
            start, count = a, 0
        count += 1
    bounds.append((start, len(text)))
    return [(a, b) for a, b in bounds if text[a:b].strip()]


def chunk(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    return [text[a:b].strip() for a, b in chunk_spans(text, max_chars)]


def question_entity(question: str) -> str | None:
    """EmailQA questions read "Find the $ value paid to/by <entity>? ..."."""
    m = re.search(r"\bpaid (?:to|by) (.+?)\?", question, re.I)
    return m.group(1).strip() if m else None


def _chunks(text: str, prefix: str, kind: str, ideal: str | None, start: int = 0) -> list[Passage]:
    return [Passage(f"{prefix}-c{start + j}", t, kind, bool(kind == "support" and ideal and ideal in t))
            for j, t in enumerate(chunk(text))]


def build_case(record: dict, contexts: list[dict], attacks: dict[str, list[str]], clean: bool = False) -> Case:
    idx, seed = record["context_index"], record["seed"]
    sample = contexts[idx]
    case = Case(
        case_id=record["case_id"] + ("-clean" if clean else ""), label="clean" if clean else "attack",
        context_index=idx, attack_family=None if clean else record["attack_family"],
        attack_index=None if clean else record["attack_index"],
        insertion_position=None if clean else record["insertion_position"], seed=seed,
        question=sample["question"], ideal=sample["ideal"], attack=None, poisoned_context=None)
    ideal = sample["ideal"] if sample["ideal"] not in ("unknown", "unkown") else None
    text, did = sample["context"], f"e{idx}"
    if clean:
        chunks = _chunks(text, did, "support", ideal)
    else:
        case.attack = attacks[record["attack_family"]][record["attack_index"]]
        text = case.poisoned_context = INSERT_FNS[record["insertion_position"]](text, case.attack, random_state=seed)
        at = text.index(case.attack)
        chunks = _chunks(text[:at], did, "support", ideal)
        chunks += _chunks(case.attack, did + "-atk", "poisoned", ideal)
        chunks += _chunks(text[at + len(case.attack):], did, "support", ideal, start=len(chunks))
    case.docs.append(Doc(did, "target", text, tuple(chunks)))
    # Distractors must not mention the question's entity (otherwise they may hold a competing answer).
    case.entity = question_entity(sample["question"])
    others = [i for i in range(len(contexts)) if i != idx and contexts[i]["context"] != sample["context"]]
    case.excluded_distractors = [i for i in others if case.entity and case.entity.lower() in contexts[i]["context"].lower()]
    others = [i for i in others if i not in case.excluded_distractors]
    for d in sorted(random.Random(seed + idx).sample(others, min(N_DISTRACTOR_EMAILS, len(others)))):
        case.docs.append(Doc(f"e{d}", "distractor", contexts[d]["context"],
                             tuple(_chunks(contexts[d]["context"], f"e{d}", "distractor", None))))
    case.pool = [c for doc in case.docs for c in doc.chunks]
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


def load_cases(manifest: Path, include_clean: bool = False, attacked: bool = True) -> list[Case]:
    rows = [json.loads(line) for line in manifest.read_text().splitlines() if line]
    split = check_manifest_checksums(rows[0])
    contexts, attacks = load_benchmark(split=split)
    records = [row for row in rows if "case_id" in row]
    clean_records = [r for r in records if r.get("label") == "clean"]  # clean-only manifests (Test)
    records = [r for r in records if r.get("label") != "clean"]
    cases = [build_case(r, contexts, attacks) for r in records] if attacked else []
    if include_clean:
        cases += [build_case(r, contexts, attacks, clean=True) for r in records]
    cases += [build_case({**r, "case_id": r["case_id"].removesuffix("-clean")}, contexts, attacks, clean=True)
              for r in clean_records]
    for case in cases:
        case.split = split
    return cases


def build_messages(question: str, passages: list[str], template: str = "system") -> list[dict[str, str]]:
    """BIPIA EmailIPIABuilder prompt; ``passages`` = surviving text per retrieved doc.

    ``template="system"``: context in the system message (require_system_prompt=True);
    ``template="user"``: BIPIA's no-system variant, context + question in one user message."""
    context = "\n\n".join(passages) if passages else NO_CONTEXT
    example = {"context": context, "question": question}
    if template == "user":
        return [{"role": "user", "content": EmailIPIABuilder(seed=0).construct_prompt(example, require_system_prompt=False)}]
    system, user = EmailIPIABuilder(seed=0).construct_prompt(example)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def risk_windows(doc: Doc) -> list[str]:
    """PIGuard input per chunk: previous + current + next chunk of the same email."""
    texts = [c.text for c in doc.chunks]
    return ["\n".join(texts[max(0, i - 1): i + 2]) for i in range(len(texts))]


def scoring_texts(cases: list[Case]) -> list[str]:
    """Every text PIGuard must score: raw chunks and their windows."""
    return list(dict.fromkeys([c.text for case in cases for c in case.pool]
                              + [w for case in cases for d in case.docs for w in risk_windows(d)]))
