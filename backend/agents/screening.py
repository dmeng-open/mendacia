import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


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


@dataclass(frozen=True)
class ScreenResult:
    rule: ScreenRule | None
    matched: str | None

    @property
    def allowed(self) -> bool:
        return self.rule is None


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold().translate(_LOOKALIKES)
    visible = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    spaced = re.sub(r"[^a-z0-9]+", " ", visible).strip()
    return re.sub(r"\b[a-z]( [a-z]\b){3,}", lambda m: m.group(0).replace(" ", ""), spaced)


def screen_input(text: str) -> ScreenResult:
    norm = normalize(text)
    for rule, pattern in PATTERNS:
        if m := pattern.search(norm):
            return ScreenResult(rule=rule, matched=m.group(0))
    return ScreenResult(rule=None, matched=None)
