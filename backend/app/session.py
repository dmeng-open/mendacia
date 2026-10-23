import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import NewType

from pydantic import SecretStr

COOKIE = "mendacia_session"

VerifiedGameId = NewType("VerifiedGameId", str)


class Forbidden(Exception):
    pass


@dataclass(frozen=True)
class Session:
    game_id: VerifiedGameId
    token: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.token.encode()).hexdigest()


def new_session(game_id: str) -> Session:
    return Session(VerifiedGameId(game_id), secrets.token_urlsafe(32))


def _mac(secret: SecretStr, message: str) -> str:
    return hmac.new(secret.get_secret_value().encode(), message.encode(), "sha256").hexdigest()


def sign(session: Session, secret: SecretStr) -> str:
    body = f"{session.game_id}.{session.token}"
    return f"{body}.{_mac(secret, body)}"


def parse(cookie: str | None, path_game_id: str, secret: SecretStr) -> Session:
    game_id, _, rest = (cookie or "").partition(".")
    token, _, mac = rest.rpartition(".")
    expected = _mac(secret, f"{game_id}.{token}")
    if not (token and hmac.compare_digest(mac, expected) and game_id == path_game_id):
        raise Forbidden(path_game_id)
    return Session(VerifiedGameId(game_id), token)


def cookie_path(game_id: str) -> str:
    return f"/games/{game_id}"
