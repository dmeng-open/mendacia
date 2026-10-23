import importlib.util
import re
import sys
from collections.abc import Collection
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

from agents.screening import screen_input
from engine.schema import Case, EvidenceDoc, Id, Unlock

MIN_DOCS = 15
MAX_DOCS = 20
SCANNER = Path(__file__).resolve().parents[2] / "scripts" / "scan_instructions.py"
ROLE_MARKER = re.compile(r"^\s*(system|assistant|user|developer)\s*:", re.IGNORECASE)
MODEL_MARKER = re.compile(r"<\||\[/?INST\]", re.IGNORECASE)


@dataclass(frozen=True)
class Lint:
    case_id: Id
    docs: int
    key: int
    locked: int
    problems: tuple[str, ...]


def _unlockers(doc: EvidenceDoc) -> frozenset[Id]:
    return (
        frozenset(doc.visibility.unlocked_by) if isinstance(doc.visibility, Unlock) else frozenset()
    )


def obtainable(case: Case) -> frozenset[Id]:
    got: set[Id] = set()
    while True:
        found = {d.id for d in case.documents if d.visibility == "open" or got & _unlockers(d)} | {
            c.id for c in case.clues if c.doc_id is None or c.doc_id in got
        }
        if found <= got:
            return frozenset(got)
        got |= found


def visible_documents(
    case: Case, discovered: Collection[Id], opened: Collection[Id]
) -> tuple[EvidenceDoc, ...]:
    held = {*discovered, *opened}
    return tuple(d for d in case.documents if d.visibility == "open" or held & _unlockers(d))


@cache
def _scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scan_instructions", SCANNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _text_problems(doc: EvidenceDoc) -> list[str]:
    scanner = _scanner()
    hosts = scanner.allowed_hosts()
    problems: list[str] = []
    for part, text in (("title", doc.title), ("body", doc.body)):
        where = f"document '{doc.id}' {part}"
        problems += [
            f"{f.rule}: {where} line {f.line}: {f.detail}"
            for f in scanner.scan_text(where, text, hosts)
        ]
        for number, line in enumerate(text.splitlines(), start=1):
            if ROLE_MARKER.match(line) or MODEL_MARKER.search(line):
                problems.append(f"model_instruction: {where} line {number}: role or chat marker")
            elif (screened := screen_input(line)).rule is not None:
                problems.append(
                    f"model_instruction: {where} line {number}: {screened.rule.value} "
                    f"'{screened.matched}'"
                )
    return problems


def lint_case(case: Case) -> Lint:
    problems: list[str] = []
    if not MIN_DOCS <= len(case.documents) <= MAX_DOCS:
        problems.append(f"{len(case.documents)} documents, need {MIN_DOCS} to {MAX_DOCS}")
    ids = {d.id for d in case.documents}
    clues = {c.id: c for c in case.clues}
    for c in case.clues:
        if c.kind == "evidence" and c.doc_id not in ids:
            problems.append(f"clue '{c.id}': document '{c.doc_id}' does not exist")
    chain_docs = {
        clues[i].doc_id for i in case.solution_chain if i in clues and clues[i].doc_id is not None
    }
    for d in case.documents:
        if d.is_key and d.id not in chain_docs:
            problems.append(f"document '{d.id}': is_key but no solution_chain clue uses it")
        if not d.is_key and d.id in chain_docs:
            problems.append(f"document '{d.id}': a solution_chain clue uses it but is_key is false")
    reachable = obtainable(case)
    locked = [d for d in case.documents if d.visibility != "open"]
    problems += [
        f"document '{d.id}': locked and unreachable, nothing obtainable unlocks it"
        for d in locked
        if d.id not in reachable
    ]
    for d in case.documents:
        problems += _text_problems(d)
    key = sum(d.is_key for d in case.documents)
    return Lint(case.id, len(case.documents), key, len(locked), tuple(problems))
