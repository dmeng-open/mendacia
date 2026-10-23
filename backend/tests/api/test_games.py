import uuid

from fastapi.testclient import TestClient

from agents.game_master import timeline
from tests.api.conftest import MANOR, Player, leaked

PIKE = "Mrs. Pike"


def test_a_replayed_game_through_every_endpoint_ends_correct_and_leaks_nothing(
    client: TestClient,
) -> None:
    p = Player(client)
    assert (p.view["questions_left"], p.view["hints_left"], p.version) == (20, 3, 0)
    pike = p.suspect(PIKE)

    first = p.ask(pike, "Where were you at 10pm?")
    assert [e["type"] for e in first][:2] == ["thinking", "validating"]
    second = p.ask(pike, "Whom did you see at 10pm?")
    assert second[-1]["questions_left"] == 18

    hits = p.get("/search", params={"q": "empty velvet case in the dressing table"})
    assert hits.status_code == 200
    assert hits.json()[0]["document_id"] == "opener_case_note"
    assert {h["provenance"] for h in hits.json()} == {"case_document"}

    hint = p.post("/hint", {"state_version": p.version})
    assert hint.status_code == 200 and "pavilion" in hint.json()["text"]

    opened = p.post("/documents/pavilion_visitors_book/open", {"state_version": p.version})
    assert opened.status_code == 200
    assert opened.json()["document"]["title"] == "Garden pavilion visitors' book"
    assert len(p.view["clues"]) == 3

    cited = [c["id"] for c in p.view["clues"]]
    early = p.get("/reveal")
    assert early.status_code == 409 and early.json()["code"] == "not_accused"
    accused = p.post(
        "/accuse",
        {"state_version": p.version, "suspect": p.suspect("Clara Ashcombe"), "cited": cited},
    )
    assert accused.status_code == 200
    assert (accused.json()["text"], accused.json()["correct"]) == ("Correct.", True)
    assert leaked(MANOR, p.bodies) == []

    reveal = p.get("/reveal").json()
    assert reveal["culprit"] == "clara" and reveal["correct"]
    assert reveal["timeline"] == timeline(MANOR)
    assert reveal["cited_chain"] == list(MANOR.solution_chain)


def test_reveal_is_409_before_the_accusation(client: TestClient) -> None:
    p = Player(client)
    r = p.get("/reveal")
    assert r.status_code == 409
    assert r.json()["code"] == "not_accused"


def test_a_hint_names_an_unopened_key_document(client: TestClient) -> None:
    p = Player(client)
    hint = p.post("/hint", {"state_version": 0})
    assert hint.status_code == 200
    assert "Garden pavilion visitors' book" in hint.json()["text"]
    assert p.view["hints_left"] == 2


def test_a_replayed_idempotency_key_spends_nothing(client: TestClient) -> None:
    p = Player(client)
    key = uuid.uuid4().hex
    first = p.post("/hint", {"state_version": 0}, key=key)
    again = p.post("/hint", {"state_version": 0}, key=key)
    assert again.status_code == 200 and again.json()["replayed"]
    assert again.json()["text"] == first.json()["text"]
    assert p.refresh()["hints_left"] == 2 and p.version == 1

    pike = p.suspect(PIKE)
    asked = p.ask(pike, "Where were you at 10pm?", key=key + "ask")
    replayed = p.ask(pike, "Where were you at 10pm?", key=key + "ask")
    assert replayed[-1]["replayed"] and replayed[-1]["questions_left"] == 19
    chunks = [e["text"] for e in asked if e["type"] == "chunk"]
    assert [e["text"] for e in replayed if e["type"] == "chunk"] == chunks

    other = p.post("/documents/dinner_menu/open", {"state_version": p.version}, key=key)
    assert other.status_code == 400 and other.json()["code"] == "bad_request"


def test_a_stale_state_version_returns_stale_state(client: TestClient) -> None:
    p = Player(client)
    p.post("/documents/dinner_menu/open", {"state_version": 0})
    stale = p.post("/documents/staff_duties/open", {"state_version": 0})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_state"
    assert p.refresh()["state_version"] == 1

    events = p.ask(p.suspect(PIKE), "Where were you at 10pm?", state_version=0)
    assert [e["type"] for e in events] == ["thinking", "done"]
    assert events[-1]["code"] == "stale_state"


def test_a_missing_idempotency_key_is_a_bad_request(client: TestClient) -> None:
    p = Player(client)
    r = client.post(f"/games/{p.id}/hint", json={"state_version": 0})
    assert r.status_code == 400 and r.json()["code"] == "bad_request"
