import asyncio
import uuid
from collections.abc import AsyncIterator

from app.cli import play
from tests.agents.test_game_master import LOCKED


async def given(lines: list[str]) -> AsyncIterator[str]:
    for line in lines:
        yield line


def game(lines: list[str]) -> list[str]:
    said: list[str] = []
    asyncio.run(play(LOCKED, uuid.uuid4().hex, given(lines), said.append, echo=False))
    return said


def test_locked_document_says_nothing_about_its_contents() -> None:
    said = game(["/read pavilion_visitors_book"])
    assert said[-1] == "That document is locked."
    key = next(d for d in LOCKED.documents if d.id == "pavilion_visitors_book")
    assert not any(key.title in s or key.body in s for s in said)


def test_listings_show_only_visible_documents() -> None:
    listing = next(s for s in game([]) if s.startswith("Documents:"))
    assert "pavilion_visitors_book" not in listing and "opener_case_note" in listing
    said = game(["/read opener_case_note", "/read nope"])
    assert "pavilion_visitors_book" in said[-1]


def test_an_opened_document_can_be_presented() -> None:
    said = game(["/suspect clara", "/read opener_case_note", "/present opener_case_note"])
    assert said[-1] == "You will show opener_case_note with your next question."
    assert game(["/suspect clara", "/present opener_case_note"])[-1].startswith("You can present")
