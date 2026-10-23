from dataclasses import dataclass, field
from typing import Literal

from app.llm import ModelRole

Layer = Literal["truth", "knowledge", "player", "conversation"]


@dataclass(frozen=True)
class AgentManifest:
    name: str
    role: ModelRole | None
    purposes: frozenset[str]
    layers: frozenset[Layer]
    sensitivity: Layer
    modules: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    verified_by: str | None = None
    planned: str | None = field(default=None, compare=False)


AGENTS = (
    AgentManifest(
        "suspect",
        ModelRole.FAST,
        frozenset({"suspect"}),
        frozenset({"knowledge", "conversation"}),
        "knowledge",
        modules=("agents.suspect", "agents.view"),
        verified_by="agents.verifier",
    ),
    AgentManifest(
        "extractor",
        ModelRole.FAST,
        frozenset({"extract"}),
        frozenset({"conversation"}),
        "conversation",
        modules=("agents.extract",),
        verified_by="agents.verifier",
    ),
    AgentManifest(
        "game_master",
        None,
        frozenset(),
        frozenset({"truth", "knowledge", "player", "conversation"}),
        "truth",
        modules=(
            "agents.game_master",
            "agents.verifier",
            "agents.events",
            "security.context",
            "security.events",
            "security.grants",
            "security.policy",
        ),
        verified_by="deterministic rules",
    ),
    AgentManifest(
        "doctor",
        ModelRole.FAST,
        frozenset({"doctor"}),
        frozenset(),
        "player",
        modules=("app.doctor",),
    ),
    AgentManifest(
        "generator",
        ModelRole.STRONG,
        frozenset({"generate"}),
        frozenset({"truth"}),
        "truth",
        verified_by="engine.solver",
        planned="P4-1",
    ),
    AgentManifest(
        "repair",
        ModelRole.STRONG,
        frozenset({"repair"}),
        frozenset({"truth"}),
        "truth",
        verified_by="engine.solver",
        planned="P4-1",
    ),
    AgentManifest(
        "detective_bot",
        ModelRole.STRONG,
        frozenset({"detective"}),
        frozenset({"player"}),
        "player",
        planned="P5-1",
    ),
    AgentManifest(
        "attack_runner",
        None,
        frozenset(),
        frozenset({"player", "truth"}),
        "truth",
        modules=("evals.security_regress",),
        verified_by="deterministic rules",
    ),
)

LLM_ADAPTERS = frozenset({"app.llm", "app.llm_pydantic"})
