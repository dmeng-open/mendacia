import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from agents import prompts
from engine.schema import (
    Case,
    Clue,
    Crime,
    DanglingReferences,
    EvidenceDoc,
    Fact,
    Id,
    Person,
    PlannedLie,
    _Model,
)

PROMPT = prompts.load("generator")
Message = dict[str, str]
Send = Callable[[list[Message]], str]
Stage = Literal["core", "documents"]

_ID = re.compile(r"[a-z][a-z0-9_]*")
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
_UNSAFE = re.compile(r"[^A-Za-z0-9 _.,:;()\[\]<>='-]")
MAX_ERRORS = 20
MAX_MESSAGE = 300
TRUSTED_MESSAGES = frozenset(
    {
        "value_error",
        "missing",
        "extra_forbidden",
        "string_pattern_mismatch",
        "string_type",
        "int_type",
        "int_parsing",
        "bool_type",
        "literal_error",
        "too_short",
        "tuple_type",
        "model_type",
        "dict_type",
        "json_invalid",
        "union_tag_invalid",
    }
)


MIN_CALL_S = 20


class OverBudget(Exception):
    pass


@dataclass(frozen=True)
class Budget:
    run_id: str
    max_usd: float
    max_s: float
    spent_usd: Callable[[], float]
    started: float = field(default_factory=time.monotonic)

    def next_call_timeout(self) -> float:
        left = self.max_s - (time.monotonic() - self.started)
        if left < MIN_CALL_S or self.spent_usd() >= self.max_usd:
            raise OverBudget
        return left


@dataclass(frozen=True)
class SchemaRejected:
    stage: Stage
    errors: tuple[str, ...]


class Named(_Model):
    id: Id
    label: str


class SecretSet(_Model):
    suspect: Id
    facts: tuple[Id, ...]


class CaseDraft(_Model):
    """Case without documents, as the model writes it: no maps keyed by id."""

    id: Id
    title: str
    summary: str
    victim: Person
    suspects: tuple[Person, ...] = Field(min_length=2)
    locations: tuple[Named, ...]
    items: tuple[Named, ...]
    time_slots: tuple[str, ...] = Field(min_length=1)
    crime: Crime
    facts: tuple[Fact, ...]
    secrets: tuple[SecretSet, ...]
    planned_lies: tuple[PlannedLie, ...]
    clues: tuple[Clue, ...]
    solution_chain: tuple[Id, ...] = Field(min_length=1)
    culprit: Id

    @model_validator(mode="after")
    def _keys_unique(self) -> Self:
        for name, keys in (
            ("locations", [n.id for n in self.locations]),
            ("items", [n.id for n in self.items]),
            ("secrets", [s.suspect for s in self.secrets]),
        ):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            if dupes:
                raise ValueError(f"{name}: duplicate id {', '.join(repr(d) for d in dupes)}")
        return self

    def to_case(self, documents: tuple[EvidenceDoc, ...]) -> Case:
        data = self.model_dump(mode="json")
        data["documents"] = [d.model_dump(mode="json") for d in documents]
        data["locations"] = {n.id: n.label for n in self.locations}
        data["items"] = {n.id: n.label for n in self.items}
        data["secrets"] = {s.suspect: s.facts for s in self.secrets}
        return Case.model_validate(data)

    @classmethod
    def of(cls, case: Case) -> "CaseDraft":
        data = case.model_dump(mode="json", exclude={"documents"})
        data["locations"] = [{"id": k, "label": v} for k, v in case.locations.items()]
        data["items"] = [{"id": k, "label": v} for k, v in case.items.items()]
        data["secrets"] = [{"suspect": k, "facts": v} for k, v in case.secrets.items()]
        return cls.model_validate(data)


def placeholders(draft: CaseDraft) -> tuple[EvidenceDoc, ...]:
    cited = dict.fromkeys(c.doc_id for c in draft.clues if c.doc_id is not None)
    chain = {c.doc_id for c in draft.clues if c.id in draft.solution_chain}
    return tuple(
        EvidenceDoc(id=i, title="", source="pending", body="", is_key=i in chain, visibility="open")
        for i in cited
    )


def parse_core(reply: str) -> Case:
    draft = CaseDraft.model_validate_json(reply)
    return draft.to_case(placeholders(draft))


class Archive(_Model):
    documents: tuple[EvidenceDoc, ...]


def documents_parser(core: Case) -> Callable[[str], Case]:
    draft = CaseDraft.of(core)
    return lambda reply: draft.to_case(Archive.model_validate_json(reply).documents)


def prompt_safe(text: str) -> str:
    def keep(m: re.Match[str]) -> str:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return f"'{inner}'" if _ID.fullmatch(inner) else "'<value>'"

    quoted = _QUOTED.sub(keep, text)
    if quoted.count("'") % 2:
        quoted = quoted.replace("'", "")
    return " ".join(_UNSAFE.sub(" ", quoted).split())[:MAX_MESSAGE]


def _loc(parts: tuple[int | str, ...]) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if _ID.fullmatch(part) else ".<key>"
    return out.lstrip(".") or "<root>"


def schema_errors(error: ValidationError) -> tuple[str, ...]:
    lines: list[str] = []
    for e in error.errors(include_input=False, include_url=False):
        cause = e.get("ctx", {}).get("error")
        if isinstance(cause, DanglingReferences):
            lines += [prompt_safe(p) for p in cause.problems]
        else:
            message = e["msg"] if e["type"] in TRUSTED_MESSAGES else e["type"]
            lines.append(f"{_loc(tuple(e['loc']))}: {prompt_safe(message)}")
    return tuple(lines[:MAX_ERRORS])


def data_block(core: Case) -> str:
    draft = CaseDraft.of(core).model_dump(mode="json")
    return json.dumps(draft, indent=1).replace("<", "\\u003c")


def ask[T](
    send: Send, parse: Callable[[str], T], messages: list[Message], stage: Stage
) -> T | SchemaRejected:
    try:
        return parse(send(messages))
    except ValidationError as first:
        errors = schema_errors(first)
    retry = [
        *messages,
        {"role": "user", "content": PROMPT.render("schema_feedback", errors="\n".join(errors))},
    ]
    try:
        return parse(send(retry))
    except ValidationError as second:
        return SchemaRejected(stage, schema_errors(second))
