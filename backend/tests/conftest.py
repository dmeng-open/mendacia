import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import pytest


@pytest.fixture(autouse=True)
def llm_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    live = request.node.get_closest_marker("live") is not None
    monkeypatch.setenv("LLM_MODE", "live" if live else "replay")
