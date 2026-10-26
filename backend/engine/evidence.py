import importlib.util
import re
import sys
from collections.abc import Collection
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Literal

from agents.documents import invisible, plain
from agents.screening import screen_input
from engine.schema import Case, EvidenceDoc, Id, Unlock

MIN_DOCS = 15
MAX_ID = 40
MAX_DOCS = 20
SCANNER = Path(__file__).resolve().parents[2] / "scripts" / "scan_instructions.py"
ROLE_MARKER = re.compile(
    r"^\s*(system|assistant|user|developer|human|model|ai|bot)\s*:", re.IGNORECASE
)
MODEL_MARKER = re.compile(
    r"<\||\[/?INST\]|<\s*/?\s*(system|assistant|user|start_of_turn|end_of_turn)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    message: str
    hint: str
    kind: Literal["structure", "text", "id"] = "text"


@dataclass(frozen=True)
class Lint:
    case_id: Id
    docs: int
    key: int
    locked: int
    findings: tuple[Finding, ...]

    @property
    def problems(self) -> tuple[str, ...]:
        return tuple(f.message for f in self.findings)


def _structural(message: str) -> Finding:
    return Finding(message, message, kind="structure")


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


def ids(case: Case) -> list[tuple[str, str]]:
    return [
        ("case id", case.id),
        *((f"people[{i}].id", p.id) for i, p in enumerate(case.people)),
        *((f"locations key {i}", k) for i, k in enumerate(case.locations)),
        *((f"items key {i}", k) for i, k in enumerate(case.items)),
        *((f"facts[{i}].id", f.id) for i, f in enumerate(case.facts)),
        *((f"planned_lies[{i}].id", lie.id) for i, lie in enumerate(case.planned_lies)),
        *((f"clues[{i}].id", c.id) for i, c in enumerate(case.clues)),
        *(
            (f"documents[{i}].{part}", value)
            for i, d in enumerate(case.documents)
            for part, value in (("id", d.id), ("source", d.source))
        ),
    ]


def _id_findings(case: Case) -> list[Finding]:
    found: list[Finding] = []
    for where, value in ids(case):
        if len(value) > MAX_ID:
            found.append(
                Finding(
                    f"unsafe_id: {where} '{value}' is longer than {MAX_ID}",
                    f"unsafe_id: {where} is too long",
                    "id",
                )
            )
        elif (screened := screen_input(value.replace("_", " "))).rule is not None:
            found.append(
                Finding(
                    f"unsafe_id: {where} '{value}': {screened.rule.value}",
                    f"unsafe_id: {where} reads as an instruction",
                    "id",
                )
            )
    return found


def prose(case: Case) -> list[tuple[str, str]]:
    return [
        ("case title", case.title),
        ("case summary", case.summary),
        *(
            (f"person '{p.id}' {part}", text)
            for p in case.people
            for part, text in (("name", p.name), ("description", p.description))
        ),
        *((f"location '{k}'", v) for k, v in case.locations.items()),
        *((f"item '{k}'", v) for k, v in case.items.items()),
        *((f"time slot {n}", label) for n, label in enumerate(case.time_slots, start=1)),
        *((f"planned lie '{lie.id}' says", lie.says) for lie in case.planned_lies),
        *((f"clue '{c.id}' description", c.description) for c in case.clues),
        *(
            (f"document '{d.id}' {part}", text)
            for d in case.documents
            for part, text in (("title", d.title), ("body", d.body))
        ),
    ]


def _text_findings(where: str, text: str) -> list[Finding]:
    scanner = _scanner()
    hosts = scanner.allowed_hosts()
    found = [
        Finding(f"{f.rule}: {where} line {f.line}: {f.detail}", f"{f.rule} in {where}")
        for f in scanner.scan_text(where, text, hosts)
    ]
    hidden = sorted({f"U+{ord(ch):04X}" for ch in text if invisible(ch)})
    if hidden:
        found.append(
            Finding(
                f"invisible_unicode: {where}: {', '.join(hidden)}", f"invisible_unicode in {where}"
            )
        )
    instruction = f"model_instruction in {where}"
    if (whole := screen_input(text)).rule is not None:
        found.append(
            Finding(
                f"model_instruction: {where}: {whole.rule.value} '{whole.matched}'", instruction
            )
        )
    for number, line in enumerate(plain(text).splitlines(), start=1):
        if ROLE_MARKER.match(line) or MODEL_MARKER.search(line):
            found.append(
                Finding(
                    f"model_instruction: {where} line {number}: role or chat marker", instruction
                )
            )
        elif (screened := screen_input(line)).rule is not None:
            found.append(
                Finding(
                    f"model_instruction: {where} line {number}: {screened.rule.value} "
                    f"'{screened.matched}'",
                    instruction,
                )
            )
    return found


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
    people = {p.id for p in case.people}
    for d in case.documents:
        if d.source in people:
            problems.append(
                f"document '{d.id}': source '{d.source}' is a person id, the player sees it; "
                "name the kind of document instead, such as letter or ledger"
            )
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
    findings = [*_id_findings(case), *(_structural(p) for p in problems)]
    for where, text in prose(case):
        findings += _text_findings(where, text)
    findings += [
        Finding(
            f"quote_in_says: planned lie '{lie.id}' says contains a double quote",
            f"quote_in_says: planned lie '{lie.id}' says contains a double quote",
        )
        for lie in case.planned_lies
        if any(q in lie.says for q in '"\u201c\u201d')
    ]
    key = sum(d.is_key for d in case.documents)
    return Lint(case.id, len(case.documents), key, len(locked), tuple(findings))
