from engine.schema import Case


class Uncontradictable(ValueError):
    pass


def drop_clue(case: Case, clue_id: str) -> Case:
    if clue_id not in {c.id for c in case.clues}:
        raise KeyError(clue_id)
    data = case.model_dump(mode="json")
    data["clues"] = [c for c in data["clues"] if c["id"] != clue_id]
    data["solution_chain"] = [c for c in data["solution_chain"] if c != clue_id]
    return Case.model_validate(data)


def add_contradiction(case: Case, fact_id: str) -> Case:
    fact = next((f for f in case.facts if f.id == fact_id), None)
    if fact is None:
        raise KeyError(fact_id)
    if fact.predicate == "at":
        person, here = fact.subject, fact.object
    elif fact.predicate == "saw":
        anchor = next(
            (
                f
                for f in case.facts
                if f.predicate == "at"
                and f.subject == fact.subject
                and f.time_slot == fact.time_slot
            ),
            None,
        )
        if anchor is None:
            raise Uncontradictable(
                f"{fact_id}: no `at` fact places {fact.subject} in slot {fact.time_slot}"
            )
        person, here = fact.object, anchor.object
    else:
        raise Uncontradictable(
            f"{fact_id}: nothing contradicts '{fact.predicate}' in an open world"
        )
    elsewhere = next((loc for loc in sorted(case.locations) if loc != here), None)
    if elsewhere is None:
        raise Uncontradictable(f"{fact_id}: the case has one location")
    taken = {f.id for f in case.facts}
    new_id = f"{fact_id}_contradiction"
    n = 2
    while new_id in taken:
        new_id, n = f"{fact_id}_contradiction_{n}", n + 1
    data = case.model_dump(mode="json")
    data["facts"].append(
        {
            "id": new_id,
            "subject": person,
            "predicate": "at",
            "object": elsewhere,
            "time_slot": fact.time_slot,
        }
    )
    return Case.model_validate(data)
