"""Turn a suspect's reply into the positive, slot-exact claims the verifier judges.

The model fills a loose wire shape (`ClaimRows`); `to_claims` parses it into `Claim`s.
Parsing never drops a claim the model asserted: a stray id is slugged, a slot on an
untimed predicate is removed, and an out-of-range slot becomes "no slot", which the
verifier blocks with "name the exact time". So a sloppy extraction costs a rewrite,
never an unchecked claim, and never a PydanticAI validation retry (a new replay key).
"""

import re
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, UnexpectedModelBehavior

from agents.claims import Claim
from app.llm import ModelRole
from app.llm_pydantic import CompleteModel
from engine.schema import CLINGO_KEYWORDS, TIMED_PREDICATES, Case, Id

EXTRACT_MAX_TOKENS = 2048


class ExtractionFailed(RuntimeError):
    pass


class ClaimRow(BaseModel):
    subject: str
    predicate: Literal["at", "saw", "heard", "has", "owes", "killed"]
    object: str
    time_slot: int | None


class ClaimRows(BaseModel):
    claims: list[ClaimRow]


async def extract_claims(
    reply: str, case: Case, suspect_id: Id, *, question: str = "", game_id: str | None = None
) -> list[Claim]:
    """Claims `reply` asserts. `question` is read only to resolve "yes", "then", "there"."""
    agent = Agent(
        CompleteModel(
            ModelRole.FAST,
            ClaimRows,
            purpose="extract",
            game_id=game_id,
            max_tokens=EXTRACT_MAX_TOKENS,
        ),
        output_type=ClaimRows,
        instructions=extract_instructions(case, suspect_id),
        retries=0,
    )
    prompt = f"Question: {question}\nReply: {reply}" if question else f"Reply: {reply}"
    try:
        result = await agent.run(prompt)
    except UnexpectedModelBehavior as e:
        raise ExtractionFailed(str(e)) from e
    return to_claims(result.output, len(case.time_slots))


def extract_instructions(case: Case, suspect_id: Id) -> str:
    speaker = next(s for s in case.suspects if s.id == suspect_id)
    people = [*case.suspects, case.victim]
    lines = [
        "You read one reply a suspect gave in a murder-mystery interview and list the facts",
        "it asserts as true. You never judge whether they are true.",
        "",
        f'The speaker is {speaker.name} (id "{speaker.id}"). "I" and "me" mean "{speaker.id}".',
        "",
        "People:",
        *(f'- "{p.id}": {p.name}' for p in people),
        "Places:",
        *(f'- "{k}": {v}' for k, v in case.locations.items()),
        "Items:",
        *(f'- "{k}": {v}' for k, v in case.items.items()),
        "Hours (time_slot):",
        *(f"- {i}: {label}" for i, label in enumerate(case.time_slots, start=1)),
        "",
        "Predicates:",
        "- at: a person was at a place at an hour",
        "- saw: a person saw another person at an hour",
        "- heard: a person heard another person at an hour",
        "- has: a person has or had an item (no hour)",
        "- owes: a person owes another person money (no hour)",
        "- killed: a person killed another person (no hour)",
        "",
        "Rules:",
        "- One claim per assertion, about anyone, the speaker included.",
        "- Use the ids above. For a person, place, or item that is not listed, invent a short",
        "  lowercase snake_case id.",
        "- time_slot is the number of the single hour the reply ties to that assertion.",
        '  "ten", "10 o\'clock", and "about 10pm" are the hour 10pm.',
        '- If the reply names no single hour for an at/saw/heard assertion ("all evening",',
        '  "earlier", "that night", "for a while"), set time_slot to null.',
        "- If it names several hours for one assertion, write one claim per hour.",
        "- time_slot is always null for has, owes, and killed.",
        '- Hedged assertions count: "I believe Clara had it" and "perhaps he was in the',
        '  garden" are claims, exactly as if said plainly.',
        "- Claims come from the reply only. Read the question just to resolve the reply: a",
        '  "yes" asserts what the question proposed, and "then" or "there" mean the hour or',
        "  place the question named.",
        '- Write only what the words assert. "I saw Hobbs in the ballroom at nine" asserts',
        "  both that the speaker saw hobbs at nine and that hobbs was in the ballroom at nine,",
        "  but not that the speaker was in the ballroom.",
        '- Leave out denials and negations ("I never went to the study"), questions,',
        '  hypotheticals ("if I had been there"), feelings, and opinions.',
        "- A reply that asserts nothing gives an empty list.",
    ]
    return "\n".join(lines)


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
        )
        if claim not in out:
            out.append(claim)
    return out


def _slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    if not re.match(r"^[a-z]", slug) or slug in CLINGO_KEYWORDS:
        slug = f"x_{slug}".rstrip("_")
    return slug
