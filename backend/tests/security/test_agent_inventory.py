from dataclasses import replace

import pytest

from agents.inventory import problems, scan_module, sources
from agents.registry import AGENTS

ROGUE = """
from app.llm import ModelRole, complete


def leak(case):
    return complete(ModelRole.STRONG, [{"role": "user", "content": case.culprit}], purpose="x")
"""


def test_repository_passes_the_gate() -> None:
    assert problems(scan_module(m, s) for m, s in sources()) == []


def test_unregistered_model_call_fails_and_names_the_module() -> None:
    found = problems([scan_module("agents.rogue", ROGUE)])
    assert found == ["agents.rogue:6: model call belongs to no agent"]


def test_use_beyond_the_manifest_fails() -> None:
    found = problems([scan_module("agents.extract", ROGUE)])
    assert "agents.extract:6: extractor uses purpose 'x'" in found
    assert "agents.extract:6: extractor uses role 'strong'" in found
    assert "agents.extract: extractor reads the truth layer outside its manifest" in found


def test_truth_reader_without_a_verifier_fails() -> None:
    doctor = next(a for a in AGENTS if a.name == "doctor")
    reader = replace(doctor, layers=frozenset({"truth"}))
    source = "def f(case):\n    return case.culprit\n"
    found = problems([scan_module("app.doctor", source)], [reader])
    assert found == ["app.doctor: doctor reads the truth layer with no verifier"]


def test_call_through_to_thread_resolves_its_role_constant() -> None:
    (site,) = scan_module(
        "agents.suspect",
        "import asyncio\nfrom app.llm import ModelRole, complete\nROLE = ModelRole.FAST\n"
        "async def f(m):\n    await asyncio.to_thread(complete, ROLE, m, purpose='suspect')\n",
    ).calls
    assert (site.role, site.purpose) == ("fast", "suspect")


@pytest.mark.parametrize(
    "source",
    [
        "from app.llm import ModelRole, complete as ask\nask(ModelRole.STRONG, m, purpose='x')\n",
        "from app.llm import ModelRole, complete\n"
        "loop.run_in_executor(None, complete, ModelRole.STRONG, m)\n",
    ],
)
def test_aliased_and_executor_calls_are_call_sites(source: str) -> None:
    assert problems([scan_module("agents.rogue", source)]) == [
        "agents.rogue:2: model call belongs to no agent"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import litellm\nlitellm.completion(model='x', messages=[])\n",
        "from pydantic_ai import Agent\nAgent('provider:any-model')\n",
    ],
)
def test_calling_a_provider_outside_the_wrapper_fails(source: str) -> None:
    found = problems([scan_module("agents.extract", source)])
    assert any("calls a model outside app.llm" in p for p in found)


def test_getattr_on_a_truth_field_reads_the_truth_layer() -> None:
    assert scan_module("m", "def f(case):\n    return getattr(case, 'culprit')\n").reads_truth


def test_tools_join_the_scan() -> None:
    source = 'async def f(broker, ctx):\n    await broker.call(ctx, "submit_accusation", {})\n'
    assert problems([scan_module("agents.extract", source)]) == [
        "agents.extract: extractor uses tool 'submit_accusation' outside its manifest"
    ]
    assert problems([scan_module("app.rogue", source)]) == [
        "app.rogue: tool 'submit_accusation' belongs to no agent"
    ]


def test_a_suspect_manifest_with_tools_fails() -> None:
    suspect = replace(next(a for a in AGENTS if a.name == "suspect"), tools=("open_document",))
    assert problems([], [suspect]) == ["suspect: suspects get no tools"]
    assert problems([], [replace(suspect, name="x", tools=("reveal_solution",))]) == [
        "x: lists unregistered tool 'reveal_solution'"
    ]
