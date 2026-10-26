import ast
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.registry import AGENTS, LLM_ADAPTERS, AgentManifest
from security.tool_broker import TOOLS

BACKEND = Path(__file__).resolve().parents[1]
SCANNED = ("agents", "app", "engine", "evals", "security")
LLM_ENTRY = frozenset({"complete", "embed", "CompleteModel"})
TRUTH_ATTRS = frozenset({"culprit", "crime", "solution_chain"})
TABLES = frozenset({"llm_calls", "verifier_events", "security_events", "generation_log"})
PROVIDERS = frozenset({"litellm", "openai", "anthropic"})


@dataclass(frozen=True)
class CallSite:
    module: str
    line: int
    role: str | None
    purpose: str | None


@dataclass(frozen=True)
class ModuleUse:
    module: str
    calls: tuple[CallSite, ...]
    reads_truth: bool
    tables: frozenset[str]
    bypasses: tuple[int, ...] = ()
    tools: frozenset[str] = frozenset()


def sources(root: Path = BACKEND) -> list[tuple[str, str]]:
    found = []
    for package in SCANNED:
        for path in sorted((root / package).rglob("*.py")):
            module = ".".join(path.relative_to(root).with_suffix("").parts).removesuffix(
                ".__init__"
            )
            found.append((module, path.read_text()))
    return found


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _role(node: ast.expr | None, constants: dict[str, ast.expr]) -> str | None:
    if isinstance(node, ast.Name) and node.id in constants:
        node = constants[node.id]
    if isinstance(node, ast.Attribute) and _name(node.value) == "ModelRole":
        return node.attr.lower()
    return None


def scan_module(module: str, source: str) -> ModuleUse:
    tree = ast.parse(source)
    constants = {
        t.id: stmt.value
        for stmt in tree.body
        if isinstance(stmt, ast.Assign)
        for t in stmt.targets
        if isinstance(t, ast.Name)
    }
    entries = set(LLM_ENTRY) | {
        a.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for a in node.names
        if a.name in LLM_ENTRY and a.asname
    }
    calls: list[CallSite] = []
    bypasses: list[int] = []
    truth = False
    tables: set[str] = set()
    tools: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in TOOLS:
            tools.add(str(node.value))
        if isinstance(node, ast.Attribute) and node.attr in TRUTH_ATTRS:
            truth = True
        if isinstance(node, ast.Constant) and node.value in TABLES:
            tables.add(str(node.value))
        if isinstance(node, ast.Import | ast.ImportFrom) and _imports_provider(node):
            bypasses.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        args = list(node.args)
        if _name(node.func) == "getattr" and len(args) > 1:
            attr = args[1]
            truth |= isinstance(attr, ast.Constant) and attr.value in TRUTH_ATTRS
        if _name(node.func) == "Agent" and not _wraps_complete_model(node):
            bypasses.append(node.lineno)
        if _name(node.func) in entries:
            role_arg = args[0] if args else None
        else:
            at = next((i for i, a in enumerate(args) if _name(a) in entries), None)
            if at is None:
                continue
            role_arg = args[at + 1] if len(args) > at + 1 else None
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        role_arg = keywords.get("role", role_arg)
        purpose = keywords.get("purpose")
        text = purpose.value if isinstance(purpose, ast.Constant) else None
        text = text if isinstance(text, str) else None
        calls.append(CallSite(module, node.lineno, _role(role_arg, constants), text))
    return ModuleUse(
        module, tuple(calls), truth, frozenset(tables), tuple(bypasses), frozenset(tools)
    )


def _imports_provider(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".")[0] in PROVIDERS
    return any(a.name.split(".")[0] in PROVIDERS for a in node.names)


def _wraps_complete_model(node: ast.Call) -> bool:
    model = (
        node.args[0]
        if node.args
        else next((k.value for k in node.keywords if k.arg == "model"), None)
    )
    return isinstance(model, ast.Call) and _name(model.func) == "CompleteModel"


def owner(module: str, agents: Sequence[AgentManifest]) -> AgentManifest | None:
    return next((a for a in agents if module in a.modules), None)


def problems(uses: Iterable[ModuleUse], agents: Sequence[AgentManifest] = AGENTS) -> list[str]:
    out = [
        f"{a.name}: lists unregistered tool {t!r}"
        for a in agents
        for t in a.tools
        if t not in TOOLS
    ]
    out += [f"{a.name}: suspects get no tools" for a in agents if a.name == "suspect" and a.tools]
    for use in uses:
        if use.module in LLM_ADAPTERS:
            continue
        out += [f"{use.module}:{line}: calls a model outside app.llm" for line in use.bypasses]
        agent = owner(use.module, agents)
        if agent is None:
            out += [f"{c.module}:{c.line}: model call belongs to no agent" for c in use.calls]
            out += [f"{use.module}: tool {t!r} belongs to no agent" for t in sorted(use.tools)]
            continue
        out += [
            f"{use.module}: {agent.name} uses tool {t!r} outside its manifest"
            for t in sorted(use.tools - set(agent.tools))
        ]
        for c in use.calls:
            if c.purpose not in agent.purposes:
                out.append(f"{c.module}:{c.line}: {agent.name} uses purpose {c.purpose!r}")
            if agent.role is None or c.role != agent.role.value:
                out.append(f"{c.module}:{c.line}: {agent.name} uses role {c.role!r}")
        if use.reads_truth and "truth" not in agent.layers:
            out.append(f"{use.module}: {agent.name} reads the truth layer outside its manifest")
        if use.reads_truth and agent.verified_by is None:
            out.append(f"{use.module}: {agent.name} reads the truth layer with no verifier")
    return out


def report(
    uses: Sequence[ModuleUse], agents: Sequence[AgentManifest] = AGENTS
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent in agents:
        mine = [u for u in uses if u.module in agent.modules]
        rows.append(
            {
                "agent": agent.name,
                "role": agent.role.value if agent.role else None,
                "tools": list(agent.tools),
                "layers": sorted(agent.layers),
                "sensitivity": agent.sensitivity,
                "verified_by": agent.verified_by,
                "planned": agent.planned,
                "call_sites": [f"{c.module}:{c.line}" for u in mine for c in u.calls],
                "reads_truth": any(u.reads_truth for u in mine),
                "tables": sorted({t for u in mine for t in u.tables}),
            }
        )
    return rows


def main(argv: Sequence[str]) -> int:
    uses = [scan_module(m, s) for m, s in sources()]
    found = problems(uses)
    rows = report(uses)
    out = BACKEND.parent / "reports" / "agent-inventory.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"agents": rows, "problems": found}, indent=2) + "\n")
    for row in rows:
        layers = ",".join(row["layers"]) or "-"
        tools = str(len(row["tools"])) if row["tools"] else "-"
        status = f"PLANNED {row['planned']}" if row["planned"] else "OK"
        role = row["role"] or "-"
        print(f"{row['agent']:<14} {role:<7} tools={tools:<4} layers={layers:<38} {status}")
    for p in found:
        print(f"FAIL {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
