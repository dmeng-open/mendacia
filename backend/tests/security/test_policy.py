from pathlib import Path

import pytest

from engine.schema import Case, Unlock, Visibility
from security.context import ActorType, AuthContext, case_version
from security.grants import AfterClue, Always, KnowledgeGrant, NeverBeforeReveal, grants_for
from security.policy import POLICY, Action, Decision, PolicyContext, Resource, authorize

REPO = Path(__file__).resolve().parents[3]
MANOR = Case.model_validate_json((REPO / "cases" / "manor.json").read_text())
VERSION = case_version(MANOR)
GRANTS = grants_for(MANOR)


def who(actor: str, actor_type: ActorType = "suspect", state: int = 0) -> AuthContext:
    return AuthContext(actor, actor_type, "game", VERSION, state)


def fact(suspect: str, fact_id: str) -> Resource:
    return Resource("fact", fact_id, VERSION, "knowledge", grant=GRANTS.get((suspect, fact_id)))


def decide(
    subject: AuthContext,
    action: Action,
    resource: Resource,
    unlocks: frozenset[str] = frozenset(),
    spent: frozenset[str] = frozenset(),
) -> Decision:
    ctx = PolicyContext(subject.state_version, unlocks=unlocks, spent=spent)
    return authorize(subject, action, resource, ctx)


def test_grants_follow_known_by_secrets_and_clues() -> None:
    assert GRANTS["hobbs", "pike_in_kitchen"].can_disclose_when == Always()
    assert GRANTS["hobbs", "clara_has_opener"].can_disclose_when == AfterClue(("opener_case",))
    assert GRANTS["clara", "clara_in_study"].can_disclose_when == AfterClue(("diary_page",))
    assert ("hobbs", "clara_in_study") not in GRANTS


def test_unknown_action_is_denied() -> None:
    decision = decide(who("p1", "player"), "know_fact", fact("hobbs", "pike_in_kitchen"))
    assert (decision.effect, decision.reason_code) == ("deny", "unknown_action")


def test_suspect_cannot_read_another_suspects_secret() -> None:
    for action in ("know_fact", "disclose_fact"):
        decision = decide(who("hobbs"), action, fact("hobbs", "clara_in_study"))
        assert (decision.effect, decision.reason_code) == ("deny", "not_granted")


def test_borrowed_grant_is_denied() -> None:
    stolen = fact("clara", "clara_in_study")
    assert decide(who("hobbs"), "know_fact", stolen).reason_code == "not_granted"


def test_fact_becomes_disclosable_once_its_clue_is_shown() -> None:
    secret = fact("hobbs", "clara_has_opener")
    assert decide(who("hobbs"), "know_fact", secret).allowed
    before = decide(who("hobbs"), "disclose_fact", secret)
    assert (before.effect, before.reason_code) == ("transition_required", "needs_clue")
    after = decide(who("hobbs"), "disclose_fact", secret, unlocks=frozenset({"opener_case"}))
    assert (after.effect, after.reason_code) == ("allow", "clue_shown")


def test_never_before_reveal_is_denied_even_with_clues_shown() -> None:
    grant = KnowledgeGrant("finch", "finch_owes_ashcombe", True, NeverBeforeReveal())
    r = Resource("fact", "finch_owes_ashcombe", VERSION, "knowledge", grant=grant)
    shown = frozenset(c.id for c in MANOR.clues)
    assert decide(who("finch"), "disclose_fact", r, unlocks=shown).reason_code == (
        "never_before_reveal"
    )


def test_stale_state_version_is_denied() -> None:
    ctx = PolicyContext(state_version=3)
    decision = authorize(who("hobbs", state=2), "know_fact", fact("hobbs", "pike_in_kitchen"), ctx)
    assert (decision.effect, decision.reason_code) == ("deny", "stale_state")


def test_other_case_version_is_denied() -> None:
    r = Resource("fact", "pike_in_kitchen", "0" * 64, "knowledge")
    assert decide(who("hobbs"), "know_fact", r).reason_code == "stale_case"


def test_suspect_never_reads_the_truth_layer() -> None:
    r = Resource(
        "fact", "pike_in_kitchen", VERSION, "truth", grant=GRANTS["hobbs", "pike_in_kitchen"]
    )
    assert decide(who("hobbs"), "know_fact", r).reason_code == "truth_layer"


@pytest.mark.parametrize(
    ("actor", "spent", "reason"),
    [
        ("clara", frozenset(), "planned_lie"),
        ("clara", frozenset({"clara_library_lie"}), "lie_spent"),
        ("hobbs", frozenset(), "not_owner"),
    ],
)
def test_tell_lie(actor: str, spent: frozenset[str], reason: str) -> None:
    r = Resource("lie", "clara_library_lie", VERSION, "knowledge", owner="clara")
    assert decide(who(actor), "tell_lie", r, spent=spent).reason_code == reason


def test_adr_007_lists_every_policy_row() -> None:
    adr = (REPO / "docs" / "adr" / "007-knowledge-vs-disclosure.md").read_text()
    for (actor, action), (condition, _) in POLICY.items():
        assert f"| `{actor}` | `{action}` | {condition} |" in adr


@pytest.mark.parametrize(
    ("visibility", "unlocks", "effect", "reason"),
    [
        ("open", frozenset(), "allow", "open"),
        (Unlock(unlocked_by=("diary_page",)), frozenset(), "deny", "locked"),
        (
            Unlock(unlocked_by=("diary_page", "opener_case")),
            frozenset({"opener_case"}),
            "allow",
            "unlocked",
        ),
        (Unlock(unlocked_by=("diary_page",)), frozenset({"debt_ledger"}), "deny", "locked"),
    ],
)
def test_open_document(
    visibility: Visibility, unlocks: frozenset[str], effect: str, reason: str
) -> None:
    r = Resource("document", "ashcombe_ledger", VERSION, "player", visibility=visibility)
    decision = decide(who("p1", "player"), "open_document", r, unlocks=unlocks)
    assert (decision.effect, decision.reason_code) == (effect, reason)


def test_suspect_cannot_open_a_document() -> None:
    r = Resource("document", "ashcombe_ledger", VERSION, "player", visibility="open")
    assert decide(who("hobbs"), "open_document", r).reason_code == "unknown_action"
