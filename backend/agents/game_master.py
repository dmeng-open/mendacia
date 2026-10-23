from collections.abc import Collection, Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from agents.verifier import Verdict
from engine.evidence import obtainable, visible_documents
from engine.schema import Case, EvidenceDoc, Id, Unlock
from security.context import AuthContext, case_version
from security.policy import PolicyContext, Resource, authorize

QUESTIONS = 20
HINTS = 3
MIN_CHAIN_CLUES = 2
TELLING = frozenset({Verdict.KNOWN_TRUE, Verdict.ADMISSION})


class GameState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: Id
    game_id: str
    questions_left: int = QUESTIONS
    hints_left: int = HINTS
    discovered: tuple[Id, ...] = ()
    opened: tuple[Id, ...] = ()
    stated_facts: tuple[Id, ...] = ()

    def visible(self, case: Case) -> tuple[EvidenceDoc, ...]:
        return visible_documents(case, self.discovered, self.opened)

    def discover(self, case: Case) -> "GameState":
        stated = set(self.stated_facts)
        found = [
            c.id
            for c in case.clues
            if (c.doc_id in self.opened if c.doc_id else set(c.reveals) <= stated)
        ]
        return self.model_copy(update={"discovered": tuple(found)})


def new_game(case: Case, game_id: str) -> GameState:
    return GameState(case_id=case.id, game_id=game_id)


class DocumentLocked(Exception):
    def __init__(self, doc_id: Id) -> None:
        super().__init__(doc_id)
        self.doc_id = doc_id


@dataclass(frozen=True)
class Hint:
    clue_id: Id
    text: str


@dataclass(frozen=True)
class NoHint:
    text: str


@dataclass(frozen=True)
class Ruling:
    correct: bool
    accused: Id
    chain_cited: tuple[Id, ...]
    text: str


def spend_question(state: GameState) -> GameState:
    if state.questions_left <= 0:
        raise ValueError("no questions left")
    return state.model_copy(update={"questions_left": state.questions_left - 1})


def record_reply(
    case: Case, state: GameState, told: Iterable[tuple[Verdict, Id | None]]
) -> GameState:
    facts = {ref for verdict, ref in told if verdict in TELLING and ref is not None}
    stated = tuple(sorted(set(state.stated_facts) | facts))
    return state.model_copy(update={"stated_facts": stated}).discover(case)


def open_document(case: Case, state: GameState, doc_id: Id) -> tuple[GameState, EvidenceDoc]:
    doc = next((d for d in case.documents if d.id == doc_id), None)
    if doc is None:
        raise KeyError(doc_id)
    version = case_version(case)
    reader = AuthContext(state.game_id, "player", state.game_id, version, 0)
    resource = Resource("document", doc.id, version, "player", visibility=doc.visibility)
    unlocks = frozenset({*state.discovered, *state.opened})
    if not authorize(reader, "open_document", resource, PolicyContext(0, unlocks=unlocks)).allowed:
        raise DocumentLocked(doc_id)
    opened = tuple(sorted({*state.opened, doc_id}))
    return state.model_copy(update={"opened": opened}).discover(case), doc


def next_hint(case: Case, state: GameState) -> tuple[GameState, Hint | NoHint]:
    if state.hints_left <= 0:
        return state, NoHint("You have no hints left.")
    missing = [c for c in case.solution_chain if c not in state.discovered]
    if not missing:
        return state, NoHint("You already hold every clue you need. Make your accusation.")
    reachable = obtainable(case)
    for clue_id in missing:
        text = _lead(case, state, clue_id, reachable, set())
        if text is not None:
            spent = state.model_copy(update={"hints_left": state.hints_left - 1})
            return spent, Hint(clue_id, text)
    return state, NoHint("You have no lead on that yet.")


def _lead(
    case: Case, state: GameState, target: Id, reachable: frozenset[Id], seen: set[Id]
) -> str | None:
    seen.add(target)
    clue = next((c for c in case.clues if c.id == target), None)
    if clue is not None and clue.doc_id is None:
        return _testimony_hint(case, clue.reveals[0])
    doc_id = clue.doc_id if clue is not None else target
    doc = next(d for d in case.documents if d.id == doc_id)
    if doc in state.visible(case):
        return f"Read {doc.title} (/read {doc.id})."
    assert isinstance(doc.visibility, Unlock)
    for unlocker in doc.visibility.unlocked_by:
        if unlocker in reachable and unlocker not in seen:
            text = _lead(case, state, unlocker, reachable, seen)
            if text is not None:
                return text
    return None


def _testimony_hint(case: Case, fact_id: Id) -> str:
    fact = next(f for f in case.facts if f.id == fact_id)
    names = {s.id: s.name for s in case.suspects}
    secret_of = {f for hidden in case.secrets.values() for f in hidden}
    knowers = [p for p in fact.known_by if p in names and fact.id not in secret_of]
    who = names[knowers[0]] if knowers else names.get(fact.subject, "the household")
    if fact.time_slot is None:
        return f"Ask {who} what they know about {names.get(fact.subject, 'the household')}."
    return f"Ask {who} where everyone was at {case.time_slots[fact.time_slot - 1]}."


def rule_accusation(case: Case, suspect_id: Id, cited_clue_ids: Collection[Id]) -> Ruling:
    chain = tuple(c for c in case.solution_chain if c in set(cited_clue_ids))
    if suspect_id != case.culprit:
        return Ruling(False, suspect_id, chain, "Wrong. That suspect did not do it.")
    if len(chain) < MIN_CHAIN_CLUES:
        return Ruling(
            False,
            suspect_id,
            chain,
            f"Not proven. Cite at least {MIN_CHAIN_CLUES} clues that prove it; "
            f"you cited {len(chain)}.",
        )
    return Ruling(True, suspect_id, chain, "Correct.")


def timeline(case: Case) -> list[str]:
    names = {p.id: p.name for p in (case.victim, *case.suspects)}
    lines = []
    for slot, label in enumerate(case.time_slots, start=1):
        for f in case.facts:
            if f.time_slot != slot:
                continue
            if f.predicate == "at":
                lines.append(f"{label}  {names[f.subject]} was in {case.locations[f.object]}.")
            elif f.predicate == "saw":
                lines.append(f"{label}  {names[f.subject]} saw {names[f.object]}.")
            elif f.predicate == "heard":
                lines.append(f"{label}  {names[f.subject]} heard {names[f.object]}.")
        if slot == case.crime.time_slot:
            lines.append(
                f"{label}  {names[case.culprit]} killed {names[case.victim.id]} in "
                f"{case.locations[case.crime.location]} with {case.items[case.crime.means]}."
            )
    return lines
