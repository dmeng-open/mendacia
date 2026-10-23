import json
import os
import re
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.session import COOKIE
from tests.api.conftest import Player, app_of

HEADERS = {"X-Debug": "1", "X-Debug-Reveal": "true", "LLM_MODE": "replay", "X-Role": "game_master"}
COOKIES = {"LLM_MODE": "replay", "role": "game_master", "debug": "1"}
PARAMS = {"debug": "1", "LLM_MODE": "live", "role": "game_master", "actor_type": "game_master"}
BODY = {"role": "game_master", "actor_type": "game_master", "debug": True, "LLM_MODE": "live"}


def play(p: Player, params: dict[str, str], body: dict[str, Any]) -> list[str]:
    pike, clara = p.suspect("Mrs. Pike"), p.suspect("Clara Ashcombe")
    out = [p.get("", params=params).text]
    out.append(
        p.get("/search", params={"q": "empty velvet case in the dressing table", **params}).text
    )
    out.append(p.get("/reveal", params=params).text)
    out.append(p.post("/hint", {"state_version": p.version, **body}, params=params).text)
    out += [json.dumps(e) for e in p.ask(pike, "Where were you at 10pm?", **body)]
    out.append(
        p.post("/documents/pavilion_visitors_book/open", {"state_version": p.version, **body}).text
    )
    cited = [c["id"] for c in p.view["clues"]]
    out.append(
        p.post(
            "/accuse", {"state_version": p.version, "suspect": clara, "cited": cited, **body}
        ).text
    )
    out.append(p.get("/reveal", params=params).text)
    return [re.sub(r'h_[0-9a-f]{10}|"game_id":"[0-9a-f]+"', "", o) for o in out]


def test_debug_headers_mode_and_role_fields_change_nothing(client: TestClient) -> None:
    clean = play(Player(client), {}, {})
    with TestClient(client.app, headers=HEADERS, cookies=COOKIES) as dirty_client:
        dirty = play(Player(dirty_client), PARAMS, BODY)
    assert dirty == clean
    assert '"correct":true' in clean[-1]


def params(dep: Dependant) -> dict[str, set[str]]:
    found = {
        "header": {p.alias for p in dep.header_params},
        "query": {p.alias for p in dep.query_params},
        "cookie": {p.alias for p in dep.cookie_params},
    }
    for sub in dep.dependencies:
        for kind, names in params(sub).items():
            found[kind] |= names
    return found


def test_no_route_reads_a_header_cookie_or_query_field_beyond_its_contract(
    client: TestClient,
) -> None:
    for route in app_of(client).routes:
        if not isinstance(route, APIRoute):
            continue
        found = params(route.dependant)
        assert found["header"] <= {"Idempotency-Key"}, route.path
        assert found["query"] <= {"q"}, route.path
        assert found["cookie"] == set(), route.path


def forged(p: Player, victim: Player) -> dict[str, str]:
    mine = p.client.cookies.get(COOKIE, path=f"/games/{p.id}")
    assert mine is not None
    _, token, mac = mine.split(".")
    return {
        "someone else's cookie": mine,
        "victim id, my token": f"{victim.id}.{token}.{mac}",
        "victim id, unsigned": f"{victim.id}.{uuid.uuid4().hex}.",
    }


ROUTES = [
    ("GET", ""),
    ("GET", "/search?q=ledger"),
    ("POST", "/documents/dinner_menu/open"),
    ("POST", "/hint"),
    ("POST", "/accuse"),
    ("GET", "/reveal"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_a_forged_game_cookie_gets_403_on_every_route(
    client: TestClient, method: str, path: str
) -> None:
    attacker, victim = Player(client), Player(client)
    for label, cookie in forged(attacker, victim).items():
        r = client.request(
            method,
            f"/games/{victim.id}{path}",
            json={"state_version": 0, "suspect": "x", "cited": []},
            headers={"Idempotency-Key": uuid.uuid4().hex, "Cookie": f"{COOKIE}={cookie}"},
        )
        assert (r.status_code, r.json()["code"]) == (403, "denied"), label
    assert victim.refresh()["state_version"] == 0


def test_a_forged_game_cookie_cannot_open_the_ask_socket(client: TestClient) -> None:
    attacker, victim = Player(client), Player(client)
    for label, cookie in forged(attacker, victim).items():
        url = f"/games/{victim.id}/ask"
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect(url, headers={"Cookie": f"{COOKIE}={cookie}"}) as ws,
        ):
            ws.receive_json()
        assert closed.value.code == 4403, label


def test_the_honeypot_404s_logs_and_flags_the_game(client: TestClient) -> None:
    p = Player(client)
    r = p.get("/solution")
    assert r.status_code == 404
    with sa.create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        flag = conn.scalar(sa.text("select abuse_flag from games where id = :g"), {"g": p.id})
        reasons = conn.scalars(
            sa.text(
                "select reason_code from security_events where game_id = :g and action = 'honeypot'"
            ),
            {"g": p.id},
        ).all()
    assert flag is True
    assert reasons == ["honeypot"]
    assert "/games/{game_id}/solution" not in client.get("/openapi.json").json()["paths"]


def honeypot_rows(game_id: str) -> tuple[bool, list[str]]:
    with sa.create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        flag = conn.scalar(sa.text("select abuse_flag from games where id = :g"), {"g": game_id})
        reasons = conn.scalars(
            sa.text(
                "select reason_code from security_events where game_id = :g and action = 'honeypot'"
            ),
            {"g": game_id},
        ).all()
    return bool(flag), list(reasons)


def test_a_stranger_hitting_the_honeypot_cannot_cool_down_the_owner(client: TestClient) -> None:
    p = Player(client)
    with TestClient(client.app) as stranger:
        for _ in range(8):
            assert stranger.get(f"/games/{p.id}/solution").status_code == 404
    assert honeypot_rows(p.id) == (False, ["honeypot_anonymous"] * 8)
    done = p.ask(p.suspect("Mrs. Pike"), "Where were you at 10pm?")[-1]
    assert done["code"] is None and done["questions_left"] == 19


def test_raw_ids_over_http_are_refused_without_a_model_call(client: TestClient) -> None:
    p = Player(client)
    done = p.ask("mrs_pike", "Where were you at 10pm?")[-1]
    assert done["code"] is not None
    assert p.refresh()["questions_left"] == 20


def test_stale_and_reused_key_refusals_write_their_audit_rows(client: TestClient) -> None:
    p = Player(client)
    key = uuid.uuid4().hex
    assert p.post("/hint", {"state_version": p.version}, key=key).status_code == 200
    assert p.post("/hint", {"state_version": 0}).status_code == 409
    reused = p.post("/documents/dinner_menu/open", {"state_version": p.version}, key=key)
    assert reused.status_code == 400
    with sa.create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        reasons = conn.scalars(
            sa.text(
                "select reason_code from security_events where game_id = :g and decision = 'deny'"
            ),
            {"g": p.id},
        ).all()
    assert sorted(reasons) == ["bad_request", "stale_state"]


def test_an_oversized_ask_frame_is_refused_before_parsing(client: TestClient) -> None:
    p = Player(client)
    frame = json.dumps({"question": "x" * 9000})
    with client.websocket_connect(f"/games/{p.id}/ask") as ws:
        ws.send_text(frame)
        assert ws.receive_json()["code"] == "bad_request"
