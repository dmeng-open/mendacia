import argparse
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import TypeAdapter

from agents.claims import Claim, contradicts
from agents.events import Rule, log_event
from agents.ledger import Ledger, LedgerEntry, LieStatus, Transition
from engine.schema import Case, Fact, Id, PlannedLie, Statement

UNKNOWN = "leave this claim out; it is not something you know or planned to say"


class Verdict(StrEnum):
    BLOCK_CULPRIT = "block_culprit"
    ADMISSION = "admission"
    KNOWN_TRUE = "known_true"
    PLANNED_LIE = "planned_lie"
    BLOCK_UNPLANNED = "block_unplanned"

    @property
    def blocks(self) -> bool:
        return self in (Verdict.BLOCK_CULPRIT, Verdict.BLOCK_UNPLANNED)


@dataclass(frozen=True)
class ClaimCheck:
    claim: Claim
    verdict: Verdict
    ref: Id | None
    reason: str

    @property
    def rule(self) -> Rule:
        if self.verdict is Verdict.BLOCK_CULPRIT:
            return "block_culprit"
        if self.verdict is Verdict.BLOCK_UNPLANNED:
            return "block_unplanned"
        raise ValueError(f"{self.verdict.name} is not logged")


class BlockedReply(Exception):
    pass


@dataclass(frozen=True)
class VerifyResult:
    checks: tuple[ClaimCheck, ...]
    transitions: tuple[Transition, ...]
    ledger: Ledger

    @property
    def passed(self) -> bool:
        return not self.blocked

    @property
    def blocked(self) -> tuple[ClaimCheck, ...]:
        return tuple(c for c in self.checks if c.verdict.blocks)

    def feedback(self) -> str:
        return "\n".join(f"- {c.claim.render()}: {c.reason}" for c in self.blocked)

    def commit(self, turn: int) -> Ledger:
        if not self.passed:
            raise BlockedReply(self.feedback())
        return self.ledger.apply(self.transitions, turn)


def exposed_facts(case: Case, presented_clue_ids: Collection[Id]) -> frozenset[Id]:
    return frozenset(f for c in case.clues if c.id in presented_clue_ids for f in c.reveals)


def stateable_facts(
    case: Case, suspect_id: Id, presented_clue_ids: Collection[Id]
) -> tuple[Fact, ...]:
    exposed = exposed_facts(case, presented_clue_ids)
    hidden = (
        set(case.secrets.get(suspect_id, ())) | set(case.secrets.get(case.culprit, ()))
    ) - exposed
    return tuple(f for f in case.facts if suspect_id in f.known_by and f.id not in hidden)


@dataclass(frozen=True)
class _View:
    suspect: Id
    culprit: Id
    facts: tuple[Fact, ...]
    own_secrets: frozenset[Id]
    culprit_hidden: tuple[Fact, ...]
    exposed: frozenset[Id]
    lies: tuple[PlannedLie, ...]
    admitted: frozenset[Id]
    record: tuple[tuple[Id, Statement], ...]


def verify_reply(
    case: Case,
    suspect_id: Id,
    claims: Sequence[Claim],
    ledger: Ledger,
    presented_clue_ids: Collection[Id],
) -> VerifyResult:
    if suspect_id not in {s.id for s in case.suspects}:
        raise ValueError(f"unknown suspect '{suspect_id}'")
    unknown = set(presented_clue_ids) - {c.id for c in case.clues}
    if unknown:
        raise ValueError(f"unknown clues {sorted(unknown)}")
    foreign = {e.lie.id for e in ledger.entries} - {lie.id for lie in case.planned_lies}
    if foreign:
        raise ValueError(f"ledger holds lies this case does not plan: {sorted(foreign)}")

    entries = ledger.of(suspect_id)
    spent = {LieStatus.EXPOSED, LieStatus.ADMITTED}
    exposed = exposed_facts(case, presented_clue_ids) | {
        e.lie.hides_fact for e in entries if e.status in spent
    }
    by_id = {f.id: f for f in case.facts}
    own = frozenset(case.secrets.get(suspect_id, ()))
    lies = tuple(lie for lie in case.planned_lies if lie.suspect == suspect_id)

    def admits(claim: Claim) -> Id | None:
        return next(
            (f.id for f in case.facts if _is_admission(claim, f, suspect_id, own, exposed)), None
        )

    admitted = frozenset(
        {e.lie.hides_fact for e in entries if e.status is LieStatus.ADMITTED}
        | {f for f in map(admits, claims) if f is not None}
    )
    told_now = [lie for c in claims for lie in lies if c.states(lie.claim)]
    stated_now = [f for c in claims for f in case.facts if c.states(f) and suspect_id in f.known_by]
    view = _View(
        suspect=suspect_id,
        culprit=case.culprit,
        facts=case.facts,
        own_secrets=own,
        culprit_hidden=tuple(
            by_id[f] for f in case.secrets.get(case.culprit, ()) if f not in exposed
        ),
        exposed=exposed,
        lies=lies,
        admitted=admitted,
        record=(
            *((e.lie.id, e.lie.claim) for e in entries if e.status is not LieStatus.ADMITTED),
            *((f, by_id[f]) for f in sorted(admitted | exposed)),
            *((f.id, f) for f in stated_now),
            *((lie.id, lie.claim) for lie in told_now),
        ),
    )
    checks = tuple(_judge(c, view) for c in claims)
    return VerifyResult(checks, _transitions(checks, view, entries), ledger)


def _is_admission(
    claim: Claim, f: Fact, suspect: Id, own: frozenset[Id], exposed: frozenset[Id]
) -> bool:
    return claim.states(f) and f.id in own and suspect in f.known_by and f.id in exposed


def _judge(claim: Claim, v: _View) -> ClaimCheck:
    if claim.predicate == "killed" and claim.subject == v.culprit:
        return ClaimCheck(claim, Verdict.BLOCK_CULPRIT, None, _block_reason(claim, v))
    for f in v.culprit_hidden:
        if claim.could_mean(f):
            return ClaimCheck(claim, Verdict.BLOCK_CULPRIT, f.id, _block_reason(claim, v))

    for f in v.facts:
        if _is_admission(claim, f, v.suspect, v.own_secrets, v.exposed):
            return ClaimCheck(claim, Verdict.ADMISSION, f.id, "admits a fact the player exposed")

    for f in v.facts:
        if claim.states(f) and v.suspect in f.known_by and f.id not in v.own_secrets - v.exposed:
            return ClaimCheck(claim, Verdict.KNOWN_TRUE, f.id, "true and known to you")

    for lie in v.lies:
        if claim.states(lie.claim):
            return _judge_lie(claim, lie, v)

    return ClaimCheck(claim, Verdict.BLOCK_UNPLANNED, None, _block_reason(claim, v))


def _judge_lie(claim: Claim, lie: PlannedLie, v: _View) -> ClaimCheck:
    def block(reason: str) -> ClaimCheck:
        return ClaimCheck(claim, Verdict.BLOCK_UNPLANNED, lie.id, reason)

    if lie.hides_fact in v.exposed:
        return block("the player has shown evidence against this lie; admit it or deflect")
    if lie.hides_fact in v.admitted:
        return block("you already admitted the truth this lie hides")
    for source, earlier in v.record:
        if source != lie.id and contradicts(earlier, lie.claim):
            return block("this contradicts what you already said")
    return ClaimCheck(claim, Verdict.PLANNED_LIE, lie.id, "your planned lie")


def _block_reason(claim: Claim, v: _View) -> str:
    if claim.unspecified:
        return "name the exact time or leave the claim out"
    if any(claim.states(f) and f.id in v.own_secrets for f in v.facts):
        return "that is your secret and no presented clue reveals it yet"
    return UNKNOWN


def _transitions(
    checks: Sequence[ClaimCheck], v: _View, entries: Sequence[LedgerEntry]
) -> tuple[Transition, ...]:
    out: list[Transition] = []
    by_id = {lie.id: lie for lie in v.lies}
    for c in checks:
        if c.verdict is Verdict.PLANNED_LIE and c.ref is not None:
            out.append(Transition(by_id[c.ref], LieStatus.TOLD))
        if c.verdict is Verdict.ADMISSION:
            out += [
                Transition(lie, LieStatus.ADMITTED) for lie in v.lies if lie.hides_fact == c.ref
            ]
    out += [
        Transition(e.lie, LieStatus.EXPOSED)
        for e in entries
        if e.status is LieStatus.TOLD and e.lie.hides_fact in v.exposed
    ]
    return tuple(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.verifier")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--suspect", required=True)
    parser.add_argument("--claims", type=Path, required=True, help="JSON file: a list of claims")
    parser.add_argument("--present", default="", help="comma-separated clue ids")
    parser.add_argument("--ledger", type=Path, help="JSON file: a Ledger")
    parser.add_argument(
        "--log", action="store_true", help="write blocked claims to verifier_events"
    )
    parser.add_argument("--game-id", default="debug")
    parser.add_argument("--turn", type=int, default=0)
    args = parser.parse_args(argv)

    case = Case.model_validate_json(args.case.read_text())
    claims = TypeAdapter(list[Claim]).validate_json(args.claims.read_text())
    ledger = Ledger.model_validate_json(args.ledger.read_text()) if args.ledger else Ledger()
    presented = frozenset(filter(None, args.present.split(",")))
    result = verify_reply(case, args.suspect, claims, ledger, presented)

    for c in result.checks:
        print(f"{c.verdict.name:<16} {c.claim.render():<36} {c.ref or '-':<22} {c.reason}")
    if args.log:
        for c in result.blocked:
            log_event(
                game_id=args.game_id,
                suspect=args.suspect,
                turn=args.turn,
                rule=c.rule,
                claim=c.claim.render(),
                action="block",
            )
        print(f"logged {len(result.blocked)} verifier_events rows")
    return 1 if result.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
