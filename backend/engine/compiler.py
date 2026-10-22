from collections.abc import Iterable
from pathlib import Path

from engine.schema import Case, Fact, Statement

RULES = (Path(__file__).with_name("rules.lp")).read_text()


def _slot(statement: Statement) -> str:
    return "none" if statement.time_slot is None else str(statement.time_slot)


def _stmt(s: Statement) -> str:
    return f"{s.predicate},{s.subject},{s.object},{_slot(s)}"


def compile_case(
    case: Case,
    *,
    drop_clues: frozenset[str] = frozenset(),
    extra_facts: Iterable[Fact] = (),
) -> str:
    extra = tuple(extra_facts)
    unknown = drop_clues - {c.id for c in case.clues}
    if unknown:
        raise KeyError(f"unknown clues to drop: {sorted(unknown)}")
    taken = {f.id for f in case.facts} & {f.id for f in extra}
    if taken:
        raise ValueError(f"extra facts reuse case fact ids: {sorted(taken)}")
    lines = [RULES]
    lines += [f"suspect({s.id})." for s in case.suspects]
    lines.append(f"victim({case.victim.id}).")
    lines += [f"loc({loc})." for loc in case.locations]
    lines += [f"item({item})." for item in case.items]
    lines.append(f"slot(1..{len(case.time_slots)}).")
    crime = case.crime
    lines.append(f"crime({crime.location},{crime.time_slot},{crime.means}).")
    lines += [f"fact({f.id},{_stmt(f)})." for f in (*case.facts, *extra)]
    lines += [f"pinned({f.id})." for f in extra]
    lines += [
        f"reveals({clue.id},{fact_id})."
        for clue in case.clues
        if clue.id not in drop_clues
        for fact_id in clue.reveals
    ]
    lines += [f"claim({lie.id},{lie.suspect},{_stmt(lie.claim)})." for lie in case.planned_lies]
    return "\n".join(lines) + "\n"
