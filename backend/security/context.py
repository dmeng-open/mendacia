import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from engine.schema import Case

ActorType = Literal["player", "suspect", "extractor", "game_master", "eval_worker", "detective_bot"]

CANARY_PREFIX = "MENDACIA-CANARY-"


@dataclass(frozen=True)
class AuthContext:
    actor_id: str
    actor_type: ActorType
    game_id: str
    case_version: str
    state_version: int


def case_version(case: Case) -> str:
    canonical = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def canary(case: Case) -> str:
    return CANARY_PREFIX + case_version(case)[:12]
