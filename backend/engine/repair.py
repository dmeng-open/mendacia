from collections.abc import Sequence

from app.llm import ModelRole, complete
from engine.draft import (
    PROMPT,
    CaseDraft,
    Message,
    SchemaRejected,
    ask,
    data_block,
    parse_core,
)
from engine.schema import Case
from engine.solver import (
    Ambiguous,
    CheckReport,
    Conflict,
    Consistent,
    Counterexample,
    DropLeavesNoModel,
    Necessary,
    NecessitySkipped,
    NoCulprit,
    Redundant,
    Unique,
    Uniqueness,
    WrongCulprit,
)

REPAIR_MAX_TOKENS = 16000


def _ids(ids: Sequence[str]) -> str:
    return ", ".join(ids) or "none"


def _world(cx: Counterexample) -> str:
    return (
        f"In that world the clues hold, {cx.culprit} is at the crime scene, and these case "
        f"facts are false: {_ids(cx.breaks)}. Facts that still hold: {_ids(cx.holds)}."
    )


def _uniqueness(check: str, verdict: Uniqueness, clues: str) -> list[str]:
    match verdict:
        case Unique():
            return []
        case Ambiguous(culprits, cx):
            return [
                f"{check}: with {clues}, {_ids(culprits)} can each be the culprit. "
                f"{_world(cx)} Add a clue to solution_chain that reveals an 'at' fact placing "
                f"{cx.culprit} in another location in the crime slot, or reveal one of the "
                "false facts above."
            ]
        case WrongCulprit(culprits, cx):
            return [
                f"{check}: with {clues}, the intended culprit is ruled out and only "
                f"{_ids(culprits)} remain. {_world(cx)} Remove or change the revealed fact "
                "that places the culprit away from the crime scene in the crime slot, and "
                f"rule out {_ids(culprits)} with alibi clues."
            ]
        case NoCulprit():
            return [
                f"{check}: with {clues}, no suspect can be the culprit. A revealed fact places "
                "every suspect, or the victim, away from the crime scene in the crime slot. "
                "Leave the culprit and the victim free to be at the scene."
            ]


def repair_instructions(report: CheckReport) -> str:
    """Turn each failed check into an instruction built from ids only, never model prose."""
    notes: list[str] = []
    match report.consistency:
        case Consistent():
            pass
        case Conflict(fact_ids, with_culprit):
            note = f"consistency: facts {_ids(fact_ids)} cannot all be true together"
            note += " once the intended culprit is at the crime scene" if with_culprit else ""
            notes.append(note + ". Change or remove one of them.")
    notes += _uniqueness("uniqueness", report.uniqueness, "every clue")
    notes += _uniqueness("sufficiency", report.sufficiency, "only the solution_chain clues")
    match report.necessity:
        case NecessitySkipped():
            pass
        case verdicts:
            for v in verdicts:
                match v:
                    case Necessary():
                        pass
                    case Redundant(clue_id):
                        notes.append(
                            f"necessity: solution_chain clue {clue_id} is redundant, the culprit "
                            "stays unique without it. Remove it from solution_chain, or make it "
                            "the only clue that rules out its suspect."
                        )
                    case DropLeavesNoModel(clue_id):
                        notes.append(
                            f"necessity: dropping solution_chain clue {clue_id} leaves no "
                            "possible world. Check the facts it reveals for a contradiction."
                        )
    for lie in report.lies:
        if not lie.exposed:
            notes.append(f"lie {lie.lie_id}: no clue exposes it. Reveal the fact it hides.")
        if lie.true_in_case:
            notes.append(
                f"lie {lie.lie_id}: the case facts allow its claim to be true. Make the claim "
                "contradict a fact."
            )
        if not lie.denies_hidden_fact:
            notes.append(
                f"lie {lie.lie_id}: its claim does not contradict the fact it hides. Place the "
                "same person in another location in the same slot."
            )
    return "\n".join(f"- {n}" for n in notes)


def repair_case(draft: Case, instructions: str, *, run_id: str) -> Case | SchemaRejected:
    def send(messages: list[Message]) -> str:
        return complete(
            ModelRole.STRONG,
            messages,
            response_format=CaseDraft,
            purpose="repair",
            max_tokens=REPAIR_MAX_TOKENS,
            prompt_version=PROMPT.version,
            run_id=run_id,
        ).text

    user = PROMPT.render("repair", instructions=instructions, draft=data_block(draft))
    messages: list[Message] = [
        {"role": "system", "content": PROMPT.render("system")},
        {"role": "user", "content": user},
    ]
    return ask(send, parse_core, messages, "core")
