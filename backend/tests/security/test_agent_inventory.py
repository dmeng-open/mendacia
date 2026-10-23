from dataclasses import replace

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
