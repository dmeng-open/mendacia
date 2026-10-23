from dataclasses import dataclass

from engine.schema import Case, Id


@dataclass(frozen=True)
class Always:
    @property
    def ref(self) -> str:
        return "always"


@dataclass(frozen=True)
class AfterClue:
    clues: tuple[Id, ...]

    @property
    def ref(self) -> str:
        return f"after_clue({','.join(self.clues)})"


@dataclass(frozen=True)
class NeverBeforeReveal:
    @property
    def ref(self) -> str:
        return "never_before_reveal"


Disclosure = Always | AfterClue | NeverBeforeReveal


@dataclass(frozen=True)
class KnowledgeGrant:
    suspect: Id
    fact: Id
    can_know: bool
    can_disclose_when: Disclosure


def grants_for(case: Case) -> dict[tuple[Id, Id], KnowledgeGrant]:
    suspects = {s.id for s in case.suspects}
    culprit_secrets = set(case.secrets.get(case.culprit, ()))
    revealed_by: dict[Id, list[Id]] = {}
    for clue in case.clues:
        for fact_id in clue.reveals:
            revealed_by.setdefault(fact_id, []).append(clue.id)
    grants: dict[tuple[Id, Id], KnowledgeGrant] = {}
    for fact in case.facts:
        for suspect in (s for s in fact.known_by if s in suspects):
            guarded = culprit_secrets | set(case.secrets.get(suspect, ()))
            rule: Disclosure = Always()
            if fact.id in guarded:
                clues = tuple(revealed_by.get(fact.id, ()))
                rule = AfterClue(clues) if clues else NeverBeforeReveal()
            grants[suspect, fact.id] = KnowledgeGrant(suspect, fact.id, True, rule)
    return grants
