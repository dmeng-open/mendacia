"""Record generator fixtures: scripted replies for each scenario, or the real model with --live."""

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from engine.generator import THEMES, Brief, generate_with_repair
from tests.engine.generator_scenarios import SCENARIOS, Scenario

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


def main(argv: list[str]) -> int:
    if argv == ["--live"]:
        result = generate_with_repair(LIVE_BRIEF)
        print(f"live: {type(result).__name__} after {len(result.rounds)} rounds")
        return 0
    for name in argv or SCENARIOS:
        _scripted(SCENARIOS[name])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
