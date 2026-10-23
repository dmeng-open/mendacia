import hashlib
import json
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from agents.suspect import suspect_brief
from agents.view import SuspectView, build_view, suspect_context
from engine.schema import Case, Crime
from security.context import canary
from tests.security.brief_states import brief_states, load_cases

CASES = load_cases()
BEFORE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "brief_hashes_before_view.json").read_text()
)
TRUTH_FIELDS = {"culprit", "crime", "solution_chain", "secrets", "facts", "clues", "documents"}


def views() -> list[tuple[Case, str, str, SuspectView]]:
    out = []
    for case in CASES:
        for s in case.suspects:
            for label, state in brief_states(case, s.id):
                subject = suspect_context(case, s.id, "game", len(state.history))
                view, _ = build_view(case, subject, state.shown, state.ledger.of(s.id), ())
                out.append((case, s.id, label, view))
    return out


VIEWS = views()


def _types(model: type[BaseModel]) -> set[type]:
    seen: set[type] = set()
    stack: list[object] = [model]
    while stack:
        tp = stack.pop()
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            if tp in seen:
                continue
            seen.add(tp)
            stack += [f.annotation for f in tp.model_fields.values()]
        else:
            stack += typing.get_args(tp)
    return seen


def test_view_types_cannot_reach_the_truth_layer() -> None:
    reachable = _types(SuspectView)
    assert Case not in reachable and Crime not in reachable
    fields = {n for tp in reachable if issubclass(tp, BaseModel) for n in tp.model_fields}
    assert not fields & TRUTH_FIELDS


@pytest.mark.parametrize(("case", "me", "label", "view"), VIEWS, ids=lambda v: str(v)[:24])
def test_no_unshown_culprit_secret_chain_id_or_canary(
    case: Case, me: str, label: str, view: SuspectView
) -> None:
    shown = {c.id for c in view.shown}
    exposed = {f for c in case.clues if c.id in shown for f in c.reveals}
    culprit_hidden = set(case.secrets.get(case.culprit, ())) - exposed
    if me != case.culprit:
        held = {f.id for f in (*view.stateable, *view.hidden, *view.proven)}
        assert not held & culprit_hidden
    rendered = view.model_dump_json() + suspect_brief(view)
    assert canary(case) not in rendered
    for clue in set(case.solution_chain) - shown:
        assert f'"{clue}"' not in rendered


@pytest.mark.parametrize(("case", "me", "label", "view"), VIEWS, ids=lambda v: str(v)[:24])
def test_brief_is_unchanged_from_before_the_view(
    case: Case, me: str, label: str, view: SuspectView
) -> None:
    digest = hashlib.sha256(suspect_brief(view).encode()).hexdigest()
    assert digest == BEFORE[f"{case.id}:{me}:{label}"]


def test_every_recorded_state_is_covered() -> None:
    assert len(VIEWS) == len(BEFORE)
