# 001. Prove each case with an open-world ASP encoding

## Status

Accepted.

## Context

No case reaches a player unless clingo proves it has exactly one culprit. The solver must also show that every `solution_chain` clue is needed, and when a check fails it must hand back a counterexample that the P4 repair loop can act on. Planned lies are testimony. The spec says suspects lie, but it does not say how a lie constrains the culprit.

## Decision

All rules live in `backend/engine/rules.lp`. `compile_case` appends the case as ground data only (`suspect`, `victim`, `loc`, `item`, `slot`, `crime`, `fact/5`, `reveals/2`, `pinned/1`, `claim/6`), so the encoding is reviewed in one file and the compiler can be wrong only about data.

**Open world.** Every world atom is a guess, and only clue pins rule worlds out.

- Every person, the victim included, is in exactly one location per slot. That one choice rule is "nobody is in two places in one slot".
- `has`, `saw`, `heard`, and `owes` are free choices. `saw(A, B, T)` forces B into A's location at T. `heard` and `owes` constrain nothing yet.
- `has` is not exclusive. With an exclusive `has`, the clue that gives the culprit the means names the culprit on its own, and every `solution_chain` clue becomes redundant.
- `holds(F)` is true when fact F's statement is true in the model. A clue pins its facts with `:- revealed(F), not holds(F).` A fact no clue reveals stays a free choice.
- The culprit is at the crime location in the crime slot and has the means. The victim is at the crime location in the crime slot.

**Lies enter as testimony.** A planned lie compiles to `claim/6`, which derives `claim_holds/1` and nothing else, so a lie never changes the set of culprits. The solver reports two warnings per lie, and neither fails a check. `exposed` is false when some world that fits every clue makes the claim true, so no evidence can catch the lie. Exposure counts reasoning, not only a clue that reveals the hidden fact. `true_in_case` is true when the case's own facts allow the claim, so the "lie" may not be false at all.

**Checks.**

- Consistency drops every clue, assumes `holds(F)` for every case fact and `culprit(<case.culprit>)`, and solves. On unsat it shrinks the assumptions to a subset-minimal core by deletion. Facts that share a (person, slot) with another fact are deleted last, so a two-places clash reports its two fact ids instead of a longer chain that rules out every suspect.
- Uniqueness solves the full program with `0 --project` and `#show culprit/1.`, which enumerates distinct culprits. The result is `Unique`, `Ambiguous`, `WrongCulprit`, or `NoCulprit`. Zero models is its own reason.
- Necessity reruns uniqueness once per chain clue with that clue dropped. A clue is `Necessary` when another suspect becomes possible, `Redundant` when the culprit stays unique, and `DropLeavesNoModel` when no model remains. Dropping a clue only removes constraints, so a case with any model never reaches `DropLeavesNoModel`. The type keeps that reason distinct anyway. Necessity is `NecessitySkipped` when uniqueness fails.
- Each alternative culprit gets a `Counterexample` from a second solve with `:- not culprit(X).` and a `#minimize` over case facts that do not hold. `breaks` lists the case facts that world must deny, and `holds` lists the rest. On every chain drop in the three hand-written cases, `breaks` is exactly the dropped clue's fact, which tells the repair loop what to reveal.

`check_case` returns these as closed union types, and `CheckReport.passed` is derived from them. `drop_clue` removes a clue from `clues` and `solution_chain`. `add_contradiction` adds an `at` fact that places the same person somewhere else in the same slot, for `at` and `saw` facts. Other predicates raise `Uncontradictable`, because the schema has no negative statements.

## Rejected

**Closed world.** Asserting clue facts directly and ruling suspects out with `not has_key(S)` returns zero models when a chain clue is dropped, not two culprits (`docs/plan.md` Appendix A). A necessity check on that encoding reports "no culprit" and gives the repair loop no counterexample.

**Per-fact integrity constraints from the compiler.** Writing `:- not at(dan, garden, 3).` per clue spreads the logic across Python templates and `rules.lp`.

**One grounded program with `#external` switches per clue.** It is faster at large sizes, but `compile_case(drop_clues=...)` would no longer be the program that ran. Each check takes well under the 2 s budget, so this waits until generated cases need it.

## Consequences

`make check-case CASE=<path>` prints one line per check, the counterexample when one exists, and the lie warnings, and exits 1 when the case fails. `backend/pyproject.toml` gains `clingo`, the one file outside the Phase 1 boundary this PR edits.
