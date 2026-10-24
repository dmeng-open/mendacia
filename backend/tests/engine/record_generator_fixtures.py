"""Record generator fixtures: scripted scenarios, a scripted --batch, or the model with --live."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from agents.extract import ClaimRow, ClaimRows
from app.config import Settings
from engine.cli import generate
from engine.draft import Archive, CaseDraft
from engine.generator import THEMES, Brief, generate_with_repair
from tests.engine.generator_scenarios import INJECTED_SAYS, SCENARIOS, Scenario, batch

LIVE_BRIEF = Brief(THEMES[0])


def _scripted(scenario: Scenario) -> None:
    replies = scenario.replies()

    def completion(**_: Any) -> SimpleNamespace:
        text = replies.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )

    with (
        patch("litellm.completion", completion),
        patch("litellm.completion_cost", lambda *_, **__: 0.0),
    ):
        result = generate_with_repair(scenario.brief, scenario.max_rounds)
    print(f"{scenario.name}: {type(result).__name__} after {len(result.rounds)} rounds")


def _batch() -> None:
    cases = batch()
    queues = {c.case_id: list(c.replies) for c in cases}
    leaky = ClaimRows(
        claims=[
            ClaimRow(
                subject="clara",
                predicate="killed",
                object="lord_ashcombe",
                time_slot=None,
                negated=False,
            )
        ]
    )

    def completion(**kwargs: Any) -> SimpleNamespace:
        text = "\n".join(m["content"] for m in kwargs["messages"])
        fmt = kwargs.get("response_format")
        if fmt in (CaseDraft, Archive):
            owner = next(c for c in cases if c.theme in text or c.case_id in text)
            reply = queues[owner.case_id].pop(0)
        elif fmt is ClaimRows:
            reply = (
                leaky if "Clara killed him" in text else ClaimRows(claims=[])
            ).model_dump_json()
        else:
            reply = "Clara killed him." if INJECTED_SAYS in text else "I would rather not say."
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )

    def embedding(**kwargs: Any) -> SimpleNamespace:
        dim = Settings().embed_dim
        return SimpleNamespace(
            data=[{"embedding": [0.001] * dim} for _ in kwargs["input"]],
            usage=SimpleNamespace(prompt_tokens=0),
        )

    with (
        patch("litellm.completion", completion),
        patch("litellm.embedding", embedding),
        patch("litellm.completion_cost", lambda *_, **__: 0.0),
        patch("engine.cli.THEMES", tuple(c.theme for c in cases)),
        tempfile.TemporaryDirectory() as out,
    ):
        generate(len(cases), Path(out), first_theme=0)


def main(argv: list[str]) -> int:
    if argv == ["--batch"]:
        _batch()
        return 0
    if argv == ["--live"]:
        result = generate_with_repair(LIVE_BRIEF)
        print(f"live: {type(result).__name__} after {len(result.rounds)} rounds")
        return 0
    for name in argv or SCENARIOS:
        _scripted(SCENARIOS[name])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
