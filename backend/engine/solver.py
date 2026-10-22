from collections.abc import Sequence
from dataclasses import dataclass

import clingo

from engine.compiler import compile_case
from engine.schema import Case, Fact


@dataclass(frozen=True)
class Counterexample:
    culprit: str
    breaks: tuple[str, ...]
    holds: tuple[str, ...]


@dataclass(frozen=True)
class Consistent:
    pass


@dataclass(frozen=True)
class Conflict:
    fact_ids: tuple[str, ...]
    with_culprit: bool


Consistency = Consistent | Conflict


@dataclass(frozen=True)
class Unique:
    culprit: str


@dataclass(frozen=True)
class Ambiguous:
    culprits: tuple[str, ...]
    counterexample: Counterexample


@dataclass(frozen=True)
class WrongCulprit:
    counterexample: Counterexample


@dataclass(frozen=True)
class NoCulprit:
    pass


Uniqueness = Unique | Ambiguous | WrongCulprit | NoCulprit


@dataclass(frozen=True)
class Necessary:
    clue_id: str
    counterexample: Counterexample


@dataclass(frozen=True)
class Redundant:
    clue_id: str


@dataclass(frozen=True)
class DropLeavesNoModel:
    clue_id: str


ClueVerdict = Necessary | Redundant | DropLeavesNoModel


@dataclass(frozen=True)
class NecessitySkipped:
    pass


Necessity = tuple[ClueVerdict, ...] | NecessitySkipped


@dataclass(frozen=True)
class LieCheck:
    lie_id: str
    exposed: bool
    true_in_case: bool


@dataclass(frozen=True)
class CheckReport:
    case_id: str
    consistency: Consistency
    uniqueness: Uniqueness
    necessity: Necessity
    lies: tuple[LieCheck, ...]

    @property
    def passed(self) -> bool:
        return (
            isinstance(self.consistency, Consistent)
            and isinstance(self.uniqueness, Unique)
            and not isinstance(self.necessity, NecessitySkipped)
            and all(isinstance(v, Necessary) for v in self.necessity)
        )


def check_case(case: Case) -> CheckReport:
    full = compile_case(case)
    no_clues = compile_case(case, drop_clues=frozenset(c.id for c in case.clues))
    uniqueness = _uniqueness(case, full)
    return CheckReport(
        case_id=case.id,
        consistency=_consistency(case, no_clues),
        uniqueness=uniqueness,
        necessity=_necessity(case) if isinstance(uniqueness, Unique) else NecessitySkipped(),
        lies=tuple(_lie_check(case, lie.id, full, no_clues) for lie in case.planned_lies),
    )


def _consistency(case: Case, no_clues: str) -> Consistency:
    tagged = {f.id: _atom("holds", f.id) for f in case.facts}
    tagged["culprit"] = _atom("culprit", case.culprit)
    core = _minimal_conflict(no_clues, tagged, delete_last=_colliding(case.facts))
    if core is None:
        return Consistent()
    return Conflict(tuple(t for t in core if t != "culprit"), "culprit" in core)


def _uniqueness(case: Case, program: str) -> Uniqueness:
    culprits = _culprits(program)
    if not culprits:
        return NoCulprit()
    if culprits == (case.culprit,):
        return Unique(case.culprit)
    other = next(c for c in culprits if c != case.culprit)
    witness = _witness(program, other)
    if case.culprit not in culprits:
        return WrongCulprit(witness)
    return Ambiguous(culprits, witness)


def _necessity(case: Case) -> tuple[ClueVerdict, ...]:
    verdicts: list[ClueVerdict] = []
    for clue_id in case.solution_chain:
        program = compile_case(case, drop_clues=frozenset({clue_id}))
        culprits = _culprits(program)
        if not culprits:
            verdicts.append(DropLeavesNoModel(clue_id))
        elif culprits == (case.culprit,):
            verdicts.append(Redundant(clue_id))
        else:
            other = next(c for c in culprits if c != case.culprit)
            verdicts.append(Necessary(clue_id, _witness(program, other)))
    return tuple(verdicts)


def _lie_check(case: Case, lie_id: str, full: str, no_clues: str) -> LieCheck:
    claim = _atom("claim_holds", lie_id)
    return LieCheck(
        lie_id=lie_id,
        exposed=not _possible(full, [claim]),
        true_in_case=_possible(no_clues, [claim, *(_atom("holds", f.id) for f in case.facts)]),
    )


def _atom(name: str, value: str) -> clingo.Symbol:
    return clingo.Function(name, [clingo.Function(value)])


def _ground(program: str, *args: str) -> clingo.Control:
    control = clingo.Control([*args, "--warn=none"])
    control.add("base", [], program)
    control.ground([("base", [])])
    return control


def _possible(program: str, atoms: Sequence[clingo.Symbol]) -> bool:
    control = _ground(program)
    return bool(control.solve(assumptions=[(a, True) for a in atoms]).satisfiable)


def _culprits(program: str) -> tuple[str, ...]:
    control = _ground(program, "0", "--project")
    found: set[str] = set()
    with control.solve(yield_=True) as handle:
        for model in handle:
            found |= {str(s.arguments[0]) for s in model.symbols(shown=True)}
    return tuple(sorted(found))


def _witness(program: str, culprit: str) -> Counterexample:
    control = _ground(
        program
        + f":- not culprit({culprit}).\n"
        + "#minimize { 1,F : fact(F,_,_,_,_), not holds(F) }.\n"
        + "#show holds/1.\n"
    )
    best: Sequence[clingo.Symbol] = ()
    with control.solve(yield_=True) as handle:
        for model in handle:
            best = model.symbols(shown=True)
    holds = {str(s.arguments[0]) for s in best if s.name == "holds"}
    facts = sorted(
        str(a.symbol.arguments[0]) for a in control.symbolic_atoms.by_signature("fact", 5)
    )
    return Counterexample(
        culprit=culprit,
        breaks=tuple(f for f in facts if f not in holds),
        holds=tuple(f for f in facts if f in holds),
    )


def _minimal_conflict(
    program: str,
    tagged: dict[str, clingo.Symbol],
    delete_last: frozenset[str] = frozenset(),
) -> tuple[str, ...] | None:
    control = _ground(program)

    def unsat(tags: Sequence[str]) -> bool:
        return bool(control.solve(assumptions=[(tagged[t], True) for t in tags]).unsatisfiable)

    core = sorted(tagged, key=lambda t: (t in delete_last, t))
    if not unsat(core):
        return None
    for tag in list(core):
        trial = [t for t in core if t != tag]
        if unsat(trial):
            core = trial
    return tuple(core)


def _colliding(facts: Sequence[Fact]) -> frozenset[str]:
    # Deleting these last makes the core the local clash, such as two `at` facts for one
    # person and slot, instead of a longer chain that rules out every suspect.
    def touches(f: Fact) -> set[tuple[str, int]]:
        if f.time_slot is None:
            return set()
        people = {f.subject, f.object} if f.predicate == "saw" else {f.subject}
        return {(p, f.time_slot) for p in people}

    counts: dict[tuple[str, int], int] = {}
    for f in facts:
        for key in touches(f):
            counts[key] = counts.get(key, 0) + 1
    return frozenset(f.id for f in facts if any(counts[k] > 1 for k in touches(f)))
