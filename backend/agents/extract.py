import json
import re
from typing import Literal

import pydantic_ai
from pydantic import BaseModel
from pydantic_ai import Agent, UnexpectedModelBehavior

from agents import prompts
from agents.claims import Claim
from app.llm import ModelRole
from app.llm_pydantic import CompleteModel
from engine.schema import CLINGO_KEYWORDS, TIMED_PREDICATES, Case, Id

EXTRACT_MAX_TOKENS = 2048
EXTRACT = prompts.load("extract")
pydantic_ai.BANNER_ENABLED = False


class ExtractionFailed(RuntimeError):
    pass


class ClaimRow(BaseModel):
    subject: str
    predicate: Literal["at", "saw", "heard", "has", "owes", "killed"]
    object: str
    time_slot: int | None
    negated: bool


class ClaimRows(BaseModel):
    claims: list[ClaimRow]


async def extract_claims(
    reply: str, case: Case, suspect_id: Id, *, question: str = "", game_id: str | None = None
) -> list[Claim]:
    agent = Agent(
        CompleteModel(
            ModelRole.FAST,
            ClaimRows,
            purpose="extract",
            game_id=game_id,
            max_tokens=EXTRACT_MAX_TOKENS,
            prompt_version=EXTRACT.version,
        ),
        output_type=ClaimRows,
        instructions=extract_instructions(case, suspect_id),
        retries=0,
    )
    prompt = json.dumps({"question": question, "reply": reply})
    try:
        result = await agent.run(prompt)
    except UnexpectedModelBehavior as e:
        raise ExtractionFailed(str(e)) from e
    return to_claims(result.output, len(case.time_slots))


def extract_instructions(case: Case, suspect_id: Id) -> str:
    speaker = next(s for s in case.suspects if s.id == suspect_id)
    catalog = EXTRACT.render(
        "catalog",
        people="\n".join(f'- "{p.id}": {p.name}' for p in (*case.suspects, case.victim)),
        places="\n".join(f'- "{k}": {v}' for k, v in case.locations.items()),
        items="\n".join(f'- "{k}": {v}' for k, v in case.items.items()),
        hours="\n".join(f"- {i}: {label}" for i, label in enumerate(case.time_slots, start=1)),
    )
    intro = EXTRACT.render("intro", speaker_name=speaker.name, speaker_id=speaker.id)
    return "\n\n".join((intro, catalog, EXTRACT.render("rules")))


def to_claims(rows: ClaimRows, slots: int) -> list[Claim]:
    out: list[Claim] = []
    for row in rows.claims:
        timed = row.predicate in TIMED_PREDICATES
        slot = row.time_slot if timed and row.time_slot in range(1, slots + 1) else None
        claim = Claim(
            subject=_slug(row.subject),
            predicate=row.predicate,
            object=_slug(row.object),
            time_slot=slot,
            negated=row.negated,
        )
        if claim not in out:
            out.append(claim)
    return out


def _slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    if not re.match(r"^[a-z]", slug) or slug in CLINGO_KEYWORDS:
        slug = f"x_{slug}".rstrip("_")
    return slug
