import time
from collections import Counter
from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict

from agents.ledger import LedgerEntry, LieStatus
from engine.schema import Case, Clue, Fact, Id, Person, PlannedLie
from security.context import AuthContext, case_version
from security.events import TraceStep
from security.grants import grants_for
from security.policy import Action, Decision, PolicyContext, Resource, authorize


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Exchange(Frozen):
    question: str
    shown: tuple[Id, ...]
    reply: str


class PublicCase(Frozen):
    title: str
    summary: str
    victim: Person
    suspects: tuple[Person, ...]
    locations: dict[Id, str]
    items: dict[Id, str]
    time_slots: tuple[str, ...]

    @classmethod
    def of(cls, case: Case) -> "PublicCase":
        return cls(
            title=case.title,
            summary=case.summary,
            victim=case.victim,
            suspects=case.suspects,
            locations=case.locations,
            items=case.items,
            time_slots=case.time_slots,
        )


class LieState(Frozen):
    lie: PlannedLie
    spent: bool


class SuspectView(Frozen):
    case_version: str
    state_version: int
    public: PublicCase
    me: Person
    stateable: tuple[Fact, ...]
    hidden: tuple[Fact, ...]
    proven: tuple[Fact, ...]
    lies: tuple[LieState, ...]
    shown: tuple[Clue, ...]
    history: tuple[Exchange, ...]


class PermittedClaims(Frozen):
    facts: tuple[Id, ...]
    lies: tuple[Id, ...]

    @classmethod
    def of(cls, view: SuspectView) -> "PermittedClaims":
        return cls(
            facts=tuple(f.id for f in view.stateable),
            lies=tuple(s.lie.id for s in view.lies if not s.spent),
        )


def suspect_context(case: Case, suspect: Id, game_id: str, state_version: int) -> AuthContext:
    return AuthContext(suspect, "suspect", game_id, case_version(case), state_version)


def build_view(
    case: Case,
    subject: AuthContext,
    shown: Collection[Id],
    entries: Sequence[LedgerEntry],
    history: tuple[Exchange, ...],
) -> tuple[SuspectView, tuple[TraceStep, ...]]:
    started = time.perf_counter()
    me = subject.actor_id
    unlocks = frozenset(shown)
    exposed = {f for c in case.clues if c.id in unlocks for f in c.reveals}
    gone = {LieStatus.EXPOSED, LieStatus.ADMITTED}
    spent = frozenset(
        lie.id
        for lie in case.planned_lies
        if lie.hides_fact in exposed
        or any(e.lie.id == lie.id and e.status in gone for e in entries)
    )
    ctx = PolicyContext(subject.state_version, unlocks=unlocks, spent=spent, purpose="suspect_turn")
    grants = grants_for(case)
    tally: Counter[str] = Counter()

    def ask(action: Action, resource: Resource) -> Decision:
        decision = authorize(subject, action, resource, ctx)
        tally[f"{action}:{decision.reason_code}"] += 1
        return decision

    known: set[Id] = set()
    sayable: set[Id] = set()
    for f in case.facts:
        r = Resource("fact", f.id, subject.case_version, "knowledge", grant=grants.get((me, f.id)))
        if ask("know_fact", r).allowed:
            known.add(f.id)
            if ask("disclose_fact", r).allowed:
                sayable.add(f.id)

    lies = []
    for lie in case.planned_lies:
        r = Resource("lie", lie.id, subject.case_version, "knowledge", owner=lie.suspect)
        decision = ask("tell_lie", r)
        if decision.allowed or decision.reason_code == "lie_spent":
            lies.append(LieState(lie=lie, spent=not decision.allowed))

    by_id = {f.id: f for f in case.facts}
    own = [by_id[f] for f in case.secrets.get(me, ()) if f in known]
    view = SuspectView(
        case_version=subject.case_version,
        state_version=subject.state_version,
        public=PublicCase.of(case),
        me=next(s for s in case.suspects if s.id == me),
        stateable=tuple(f for f in case.facts if f.id in sayable),
        hidden=tuple(f for f in own if f.id not in sayable),
        proven=tuple(f for f in own if f.id in sayable),
        lies=tuple(lies),
        shown=tuple(c for c in case.clues if c.id in unlocks),
        history=history,
    )
    ms = (time.perf_counter() - started) * 1000
    outcome = " ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    identity = f"suspect state_version={subject.state_version}"
    return view, (
        TraceStep(step="identity", outcome=identity, ms=0.0),
        TraceStep(step="policy", outcome=outcome, ms=round(ms, 3)),
    )
