# 002. The case schema

## Status

Accepted.

## Context

A case is the single input to the solver, the verifier, the suspect agents, and the game master. P1-1 asks for `Person`, `Fact`, `PlannedLie`, `Clue`, `EvidenceDoc`, and `Case` "per `docs/spec.md`". `docs/spec.md` is not on `main` (see `docs/QUESTIONS.md`), so this record derives each field from the uses that `docs/plan.md` names: the reference checks in P1-1, the ASP compiler in P1-2, the verifier rules in P2-1, and the game master in P2-3. When the spec lands, a field that differs from it changes here, in the cases, and in the tests in one PR.

## Decision

`backend/engine/schema.py` holds frozen Pydantic models that forbid unknown keys.

- **Ids.** Every id matches `^[a-z][a-z0-9_]*$`. The compiler writes ids as clingo constants, and clingo constants must start with a lowercase letter.
- **`Statement`.** A `(subject, predicate, object, time_slot)` triple. `predicate` is the closed literal `at`, `has`, `saw`, `owes`, `heard`, so an unknown predicate fails validation. `at`, `saw`, and `heard` need a `time_slot`, and `has` and `owes` take none. `subject` is always a person. The object of `at` is a location, the object of `has` is an item, and the object of `saw`, `owes`, and `heard` is a person.
- **`Fact`.** A `Statement` with an `id` and `known_by`, the people who know it. `saw(A, B, T)` has no location field. It means A and B were in the same place at slot T, so the solver places B wherever A is.
- **`PlannedLie`.** `suspect`, `hides_fact`, `claim`, and `says`. `claim` is a `Statement`, so the verifier in P2-1 matches an extracted claim against it field by field. `says` is the line the suspect agent starts from. `hides_fact` must be one of that suspect's `secrets`.
- **`Clue`.** `kind` is `testimony` or `evidence`. `reveals` lists one or more fact ids. An evidence clue needs a `doc_id`, and a testimony clue takes none.
- **`EvidenceDoc`.** `id`, `title`, `body`, and `is_key`. P3-1 grows each case to 15 to 20 documents and lints `is_key` against the chain.
- **`Crime`.** `location`, `time_slot`, and `means`. The compiler reads the scene here instead of searching the facts.
- **`Case`.** `victim` and `suspects` are separate, because the victim can never be the culprit. `locations` and `items` map ids to display names. `time_slots` lists slot labels, and slot numbers start at 1. `secrets` maps a suspect to the facts that suspect hides. `solution_chain` lists the clue ids that together prove the culprit.

One `model_validator` on `Case` collects every dangling reference and raises `DanglingReferences` with one line per problem, in the form `<json path>: unknown <kind> '<id>'`. It covers `known_by`, `secrets` keys and values, `planned_lies.suspect`, `planned_lies.hides_fact`, the lie's `claim`, `clues.reveals`, `clues.doc_id`, `solution_chain`, `culprit`, fact subjects and objects, `crime`, time slots, and duplicate ids. The validator reports every problem at once, so one renamed suspect lists every path that still points at the old id.

## Consequences

`python -m engine.cli validate <path>...` and `make validate-cases` print `OK <path>` or `FAIL <path>` and the problem lines, and exit 1 on any failure. A schema change after this PR updates the three cases in `cases/`, the solver, and the tests in the same PR, and adds an ADR.
