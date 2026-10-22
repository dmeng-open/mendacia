import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class ScreenRule(StrEnum):
    ROLE_OVERRIDE = "role_override"
    PROMPT_PROBE = "prompt_probe"
    ANSWER_DEMAND = "answer_demand"
    AI_PROBE = "ai_probe"


_ROLE_WORDS = r"(role|character|persona|instructions|rules|prompt|programming)"

PATTERNS: tuple[tuple[ScreenRule, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(p))
    for rule, p in (
        (
            ScreenRule.ROLE_OVERRIDE,
            rf"\b(ignore|forget|disregard|override|drop)( \w+){{0,3}} {_ROLE_WORDS}\b",
        ),
        (ScreenRule.ROLE_OVERRIDE, r"\b(stop|quit|break) (role ?playing|pretending|character)\b"),
        (ScreenRule.ROLE_OVERRIDE, r"\bout of character\b"),
        (ScreenRule.ROLE_OVERRIDE, r"\b(developer|god|debug) mode\b"),
        (ScreenRule.PROMPT_PROBE, r"\bsystem (prompt|message|instructions?)\b"),
        (
            ScreenRule.PROMPT_PROBE,
            rf"\b(repeat|reveal|print|show|output|recite) (your|the) {_ROLE_WORDS}\b",
        ),
        (
            ScreenRule.ANSWER_DEMAND,
            r"\bjust tell me (the )?(answer|solution|culprit|killer|murderer|who)\b",
        ),
        (ScreenRule.ANSWER_DEMAND, r"\b(what|who) is the (answer|solution)\b"),
        (ScreenRule.ANSWER_DEMAND, r"\b(solve|spoil) (the|this) (case|mystery|game|puzzle)\b"),
        (ScreenRule.AI_PROBE, r"\b(you are|you re|as) an? (ai|llm|language model|chatbot|bot)\b"),
        (ScreenRule.AI_PROBE, r"\blanguage model\b"),
    )
)


@dataclass(frozen=True)
class ScreenResult:
    rule: ScreenRule | None
    matched: str | None

    @property
    def allowed(self) -> bool:
        return self.rule is None


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    visible = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    return re.sub(r"[^a-z0-9]+", " ", visible).strip()


def screen_input(text: str) -> ScreenResult:
    norm = normalize(text)
    for rule, pattern in PATTERNS:
        if m := pattern.search(norm):
            return ScreenResult(rule=rule, matched=m.group(0))
    return ScreenResult(rule=None, matched=None)
