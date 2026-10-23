import base64
import binascii
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ScreenRule(StrEnum):
    ROLE_OVERRIDE = "role_override"
    PROMPT_PROBE = "prompt_probe"
    ANSWER_DEMAND = "answer_demand"
    AI_PROBE = "ai_probe"


_TARGET = r"(role|character|persona|instructions?|rules|prompt|programming|messages?)"
_THEIRS = r"(your|previous|prior|above|earlier|preceding|initial|original|hidden|system)"

PATTERNS: tuple[tuple[ScreenRule, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(p))
    for rule, p in (
        (
            ScreenRule.ROLE_OVERRIDE,
            rf"\b(ignore|forget|disregard|override)( \w+){{0,5}} {_THEIRS} {_TARGET}\b",
        ),
        (
            ScreenRule.ROLE_OVERRIDE,
            r"\b(ignore|forget|disregard) (everything|all)( \w+){0,2} (above|before|told)\b",
        ),
        (ScreenRule.ROLE_OVERRIDE, r"\b(stop|quit) (role ?playing|the role ?play)\b"),
        (ScreenRule.ROLE_OVERRIDE, r"\b(break|drop|leave) (character|your character|the act)\b"),
        (ScreenRule.ROLE_OVERRIDE, r"\bout of character now\b"),
        (ScreenRule.ROLE_OVERRIDE, r"\b(developer|god|debug|dan) mode\b"),
        (ScreenRule.PROMPT_PROBE, r"\bsystem prompt\b"),
        (
            ScreenRule.PROMPT_PROBE,
            rf"\b(repeat|reveal|print|output|recite)( \w+){{0,2}} {_THEIRS}( \w+)? {_TARGET}\b",
        ),
        (
            ScreenRule.ANSWER_DEMAND,
            r"\bjust tell me (the )?(answer|solution|culprit|killer|murderer|who)\b",
        ),
        (ScreenRule.ANSWER_DEMAND, r"\bwhat( is| s) the (answer|solution)( to (this|the) \w+)?$"),
        (
            ScreenRule.ANSWER_DEMAND,
            r"\b(solve|spoil) (the|this) (case|mystery|game|puzzle) for me\b",
        ),
        (
            ScreenRule.AI_PROBE,
            r"\b(you are|you re|are you|as) an? (ai|llm|language model|chatbot|bot)\b",
        ),
        (ScreenRule.AI_PROBE, r"\blanguage model\b"),
    )
)

_LOOKALIKES = str.maketrans(
    "\u0430\u0435\u0456\u043e\u0440\u0441\u0443\u0445\u0501\u0455\u0458\u04cf", "aeiopcyxdsjl"
)


Via = Literal["plain", "leet", "hex", "base64"]

LEET = str.maketrans("013457@$!", "oieastasi")
HEX_RUN = re.compile(r"(?:[0-9a-fA-F]{2}){8,}")
BASE64_RUN = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")


@dataclass(frozen=True)
class ScreenResult:
    rule: ScreenRule | None
    matched: str | None
    via: Via = "plain"

    @property
    def allowed(self) -> bool:
        return self.rule is None


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold().translate(_LOOKALIKES)
    visible = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    spaced = re.sub(r"[^a-z0-9]+", " ", visible).strip()
    return re.sub(r"\b[a-z]( [a-z]\b){3,}", lambda m: m.group(0).replace(" ", ""), spaced)


def _printable(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if text.strip() and all(c.isprintable() or c.isspace() for c in text) else None


def decodings(text: str) -> Iterator[tuple[Via, str]]:
    yield "leet", text.translate(LEET)
    for m in HEX_RUN.finditer(text):
        if decoded := _printable(bytes.fromhex(m.group())):
            yield "hex", decoded
    for m in BASE64_RUN.finditer(text):
        run = m.group().rstrip("=").replace("-", "+").replace("_", "/")
        try:
            raw = base64.b64decode(run + "=" * (-len(run) % 4), validate=True)
        except (binascii.Error, ValueError):
            continue
        if decoded := _printable(raw):
            yield "base64", decoded


def screen_input(text: str) -> ScreenResult:
    for via, candidate in (("plain", text), *decodings(text)):
        norm = normalize(candidate)
        for rule, pattern in PATTERNS:
            if m := pattern.search(norm):
                return ScreenResult(rule=rule, matched=m.group(0), via=via)
    return ScreenResult(rule=None, matched=None)
