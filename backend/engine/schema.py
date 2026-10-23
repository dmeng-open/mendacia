from collections.abc import Iterable
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

CLINGO_KEYWORDS = frozenset({"not"})


def _not_a_keyword(value: str) -> str:
    if value in CLINGO_KEYWORDS:
        raise ValueError(f"'{value}' is a clingo keyword")
    return value


Id = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$"), AfterValidator(_not_a_keyword)]
Predicate = Literal["at", "has", "saw", "owes", "heard"]
ClueKind = Literal["testimony", "evidence"]

TIMED_PREDICATES: frozenset[Predicate] = frozenset({"at", "saw", "heard"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Person(_Model):
    id: Id
    name: str
    description: str


class Statement(_Model):
    subject: Id
    predicate: Predicate
    object: Id
    time_slot: int | None = None

    @model_validator(mode="after")
    def _time_slot_matches_predicate(self) -> Self:
        timed = self.predicate in TIMED_PREDICATES
        if timed and self.time_slot is None:
            raise ValueError(f"'{self.predicate}' needs a time_slot")
        if not timed and self.time_slot is not None:
            raise ValueError(f"'{self.predicate}' takes no time_slot")
        if self.predicate in {"saw", "owes", "heard"} and self.subject == self.object:
            raise ValueError(f"'{self.predicate}' needs two different people")
        return self


class Fact(Statement):
    id: Id
    known_by: tuple[Id, ...] = ()


class PlannedLie(_Model):
    id: Id
    suspect: Id
    hides_fact: Id
    claim: Statement
    says: str


class Clue(_Model):
    id: Id
    kind: ClueKind
    description: str
    reveals: tuple[Id, ...] = Field(min_length=1)
    doc_id: Id | None = None

    @model_validator(mode="after")
    def _doc_matches_kind(self) -> Self:
        if self.kind == "evidence" and self.doc_id is None:
            raise ValueError("an evidence clue needs a doc_id")
        if self.kind == "testimony" and self.doc_id is not None:
            raise ValueError("a testimony clue takes no doc_id")
        return self


class Unlock(_Model):
    unlocked_by: tuple[Id, ...] = Field(min_length=1)


Visibility = Literal["open"] | Unlock


class EvidenceDoc(_Model):
    id: Id
    title: str
    source: Id
    body: str
    is_key: bool
    visibility: Visibility


class Crime(_Model):
    location: Id
    time_slot: int
    means: Id


class DanglingReferences(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


class Case(_Model):
    id: Id
    title: str
    summary: str
    victim: Person
    suspects: tuple[Person, ...] = Field(min_length=2)
    locations: dict[Id, str]
    items: dict[Id, str]
    time_slots: tuple[str, ...] = Field(min_length=1)
    crime: Crime
    facts: tuple[Fact, ...]
    secrets: dict[Id, tuple[Id, ...]]
    planned_lies: tuple[PlannedLie, ...]
    clues: tuple[Clue, ...]
    documents: tuple[EvidenceDoc, ...]
    solution_chain: tuple[Id, ...] = Field(min_length=1)
    culprit: Id

    @property
    def people(self) -> tuple[Person, ...]:
        return (self.victim, *self.suspects)

    @model_validator(mode="after")
    def _references_resolve(self) -> Self:
        problems = _reference_problems(self)
        if problems:
            raise DanglingReferences(problems)
        return self


def _reference_problems(case: Case) -> list[str]:
    people = {p.id for p in case.people}
    suspects = {p.id for p in case.suspects}
    facts = {f.id for f in case.facts}
    clues = {c.id for c in case.clues}
    documents = {d.id for d in case.documents}
    slots = range(1, len(case.time_slots) + 1)
    problems: list[str] = []

    def check(path: str, value: str, known: Iterable[str], kind: str) -> None:
        if value not in known:
            problems.append(f"{path}: unknown {kind} '{value}'")

    def check_slot(path: str, slot: int | None) -> None:
        if slot is not None and slot not in slots:
            problems.append(f"{path}: unknown time slot '{slot}'")

    def check_statement(path: str, s: Statement) -> None:
        check(f"{path}.subject", s.subject, people, "person")
        if s.predicate == "at":
            check(f"{path}.object", s.object, case.locations, "location")
        elif s.predicate == "has":
            check(f"{path}.object", s.object, case.items, "item")
        else:
            check(f"{path}.object", s.object, people, "person")
        check_slot(f"{path}.time_slot", s.time_slot)

    for kind, ids in (
        ("person", [p.id for p in case.people]),
        ("fact", [f.id for f in case.facts]),
        ("planned lie", [lie.id for lie in case.planned_lies]),
        ("clue", [c.id for c in case.clues]),
        ("document", [d.id for d in case.documents]),
        ("solution_chain", list(case.solution_chain)),
    ):
        problems += [f"duplicate {kind} id '{i}'" for i in sorted(set(ids)) if ids.count(i) > 1]

    check("crime.location", case.crime.location, case.locations, "location")
    check("crime.means", case.crime.means, case.items, "item")
    check_slot("crime.time_slot", case.crime.time_slot)

    for i, fact in enumerate(case.facts):
        check_statement(f"facts[{i}]", fact)
        for j, person in enumerate(fact.known_by):
            check(f"facts[{i}].known_by[{j}]", person, people, "person")

    for suspect, hidden in case.secrets.items():
        check(f"secrets.{suspect}", suspect, suspects, "suspect")
        for j, fact_id in enumerate(hidden):
            check(f"secrets.{suspect}[{j}]", fact_id, facts, "fact")

    for i, lie in enumerate(case.planned_lies):
        check(f"planned_lies[{i}].suspect", lie.suspect, suspects, "suspect")
        check(f"planned_lies[{i}].hides_fact", lie.hides_fact, facts, "fact")
        check_statement(f"planned_lies[{i}].claim", lie.claim)
        if lie.hides_fact in facts and lie.hides_fact not in case.secrets.get(lie.suspect, ()):
            problems.append(
                f"planned_lies[{i}].hides_fact: '{lie.hides_fact}' is not a secret of "
                f"'{lie.suspect}'"
            )

    for i, clue in enumerate(case.clues):
        for j, fact_id in enumerate(clue.reveals):
            check(f"clues[{i}].reveals[{j}]", fact_id, facts, "fact")
        if clue.doc_id is not None:
            check(f"clues[{i}].doc_id", clue.doc_id, documents, "document")

    for i, doc in enumerate(case.documents):
        if doc.id in clues:
            problems.append(f"documents[{i}].id: '{doc.id}' is also a clue id")
        if isinstance(doc.visibility, Unlock):
            for j, ref in enumerate(doc.visibility.unlocked_by):
                path = f"documents[{i}].visibility.unlocked_by[{j}]"
                if ref == doc.id:
                    problems.append(f"{path}: '{ref}' cannot unlock itself")
                else:
                    check(path, ref, clues | documents, "clue or document")

    for i, clue_id in enumerate(case.solution_chain):
        check(f"solution_chain[{i}]", clue_id, clues, "clue")
    check("culprit", case.culprit, suspects, "suspect")
    return problems
