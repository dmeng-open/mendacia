from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from engine.schema import Id
from security.context import ActorType, AuthContext
from security.grants import AfterClue, Always, KnowledgeGrant, NeverBeforeReveal

POLICY_VERSION = "p3-2.1"

Action = Literal["know_fact", "disclose_fact", "tell_lie", "read_truth", "commit_turn"]
Effect = Literal["allow", "deny", "transition_required"]
ResourceType = Literal["fact", "lie", "truth", "turn"]
Layer = Literal["truth", "knowledge", "player", "conversation"]


@dataclass(frozen=True)
class Resource:
    type: ResourceType
    id: Id
    case_version: str
    classification: Layer
    owner: Id | None = None
    grant: KnowledgeGrant | None = None


@dataclass(frozen=True)
class PolicyContext:
    state_version: int
    unlocks: frozenset[Id] = field(default_factory=frozenset)
    spent: frozenset[Id] = field(default_factory=frozenset)
    purpose: str = ""


@dataclass(frozen=True)
class Decision:
    effect: Effect
    reason_code: str
    policy_version: str = POLICY_VERSION

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"


def allow(reason: str) -> Decision:
    return Decision("allow", reason)


def deny(reason: str) -> Decision:
    return Decision("deny", reason)


Rule = Callable[[AuthContext, Resource, PolicyContext], Decision]


def _know(subject: AuthContext, resource: Resource, ctx: PolicyContext) -> Decision:
    g = resource.grant
    mine = g is not None and (g.suspect, g.fact) == (subject.actor_id, resource.id)
    if resource.type != "fact" or g is None or not mine or not g.can_know:
        return deny("not_granted")
    return allow("granted")


def _disclose(subject: AuthContext, resource: Resource, ctx: PolicyContext) -> Decision:
    known = _know(subject, resource, ctx)
    if not known.allowed:
        return known
    assert resource.grant is not None
    match resource.grant.can_disclose_when:
        case Always():
            return allow("always")
        case AfterClue(clues):
            if ctx.unlocks & set(clues):
                return allow("clue_shown")
            return Decision("transition_required", "needs_clue")
        case NeverBeforeReveal():
            return deny("never_before_reveal")


def _tell_lie(subject: AuthContext, resource: Resource, ctx: PolicyContext) -> Decision:
    if resource.type != "lie" or resource.owner != subject.actor_id:
        return deny("not_owner")
    return deny("lie_spent") if resource.id in ctx.spent else allow("planned_lie")


def _game_master(subject: AuthContext, resource: Resource, ctx: PolicyContext) -> Decision:
    return allow("server_rule")


POLICY: dict[tuple[ActorType, Action], tuple[str, Rule]] = {
    ("suspect", "know_fact"): ("a grant names this suspect and fact", _know),
    ("suspect", "disclose_fact"): (
        "known, and the grant's disclosure rule holds: always, after one of its clues is "
        "shown, or never before the reveal",
        _disclose,
    ),
    ("suspect", "tell_lie"): ("the lie is the suspect's own and is not spent", _tell_lie),
    ("game_master", "read_truth"): ("verification, scoring, and the reveal", _game_master),
    ("game_master", "commit_turn"): ("the version the turn was authorized at", _game_master),
}


def authorize(
    subject: AuthContext, action: Action, resource: Resource, context: PolicyContext
) -> Decision:
    if resource.case_version != subject.case_version:
        return deny("stale_case")
    if context.state_version != subject.state_version:
        return deny("stale_state")
    entry = POLICY.get((subject.actor_type, action))
    if entry is None:
        return deny("unknown_action")
    if resource.classification == "truth" and subject.actor_type != "game_master":
        return deny("truth_layer")
    return entry[1](subject, resource, context)
