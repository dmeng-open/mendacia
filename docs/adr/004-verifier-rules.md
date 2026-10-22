# 004. Verify every suspect claim with fixed rules

## Status

Accepted.

## Context

Suspects may lie only with the case's `planned_lies`, and no reply may name the culprit as the killer or leak a culprit secret before the player exposes it. P2-2 extracts claims from each draft reply and needs a verdict for every claim before the reply is released. The check must be pure, cheap (under 5 ms for 10 claims), and must not call a model.

## Decision

**Claims.** `agents.claims.Claim` is the `(subject, predicate, object, time_slot)` triple of `engine.schema.Statement`, plus one predicate, `killed`, that exists only in `agents`. No fact or planned lie can carry `killed`, so the case schema stays as ADR 002 records it. `has` and `owes` take no time slot. The timed predicates may leave it out when the reply named no time. A claim matches a statement only on exact equality of all four fields, except that the culprit rule reads a missing slot as any slot.

**Exposure is derived.** A fact is exposed when a clue in `presented_clue_ids` reveals it. `presented_clue_ids` is every clue the player has shown this suspect so far. The verifier computes exposure on every call and never reads it from the ledger, so a stale ledger cannot let a spent lie through.

**Rules, in order.** The first rule that matches gives the claim its verdict.

1. `BLOCK_CULPRIT`: the claim says the culprit killed someone, or could mean a culprit secret that is not exposed. Who speaks does not matter, and nothing overrides this rule.
2. `ADMISSION`: the claim states one of the suspect's own secrets that the suspect knows and a presented clue reveals.
3. `KNOWN_TRUE`: the claim states a fact the suspect knows (`known_by`) that is not one of the suspect's unexposed secrets.
4. `PLANNED_LIE`: the claim states one of the suspect's planned lies, and the lie agrees with every earlier ledger entry. A lie disagrees when its hidden fact is exposed, when its hidden fact is admitted, or when it puts the same person in two places in one slot against another lie the suspect told or a fact the suspect admitted. A disagreeing lie gets `BLOCK_UNPLANNED`.
5. `BLOCK_UNPLANNED`: every other claim.

A reply with no claims, such as "I don't know" or a refusal, always passes. Verdicts do not depend on claim order.

**The lie ledger.** `LieStatus` is `told`, `exposed`, or `admitted`. `LedgerEntry` holds the planned lie (and so its suspect), the turn the entry was created, and the status. The ledger holds at most one entry per lie, and a status only moves forward. `verify_reply` returns the transitions that releasing the reply would make: `told` for each planned lie, `admitted` for each lie whose hidden fact the reply admits, and `exposed` for each told lie whose hidden fact is now exposed. `VerifyResult.commit(ledger, turn)` applies them, refuses a blocked reply, and is idempotent. P2-2's `commit` node is its only caller.

The lie-to-admission transition is therefore: the suspect tells the lie (`told`); the player presents a clue that reveals the hidden fact (`exposed`); the lie is now spent and blocks, so the suspect either deflects or states the hidden fact, which is an `ADMISSION` (`admitted`).

**Leak safety.** A `BLOCK_CULPRIT` reason is the same sentence as a plain `BLOCK_UNPLANNED` reason. The rewrite prompt in P2-2 feeds the reason back to the suspect model, so a model playing an innocent suspect never learns who the culprit is from its own rewrite.

**Logging.** The verifier logs nothing. Callers write one `verifier_events` row per blocked claim, with game id, suspect, turn, `rule` (`block_culprit`, `block_unplanned`, or `input_screen`), the rendered claim, and `action` (`block` from the debug lever, `rewrite`, `fallback`, or `refuse` for screened input). The migration constrains both columns to those values.

**Input screening.** `screen_input` normalizes the text (NFKC, casefold, zero-width characters removed, punctuation collapsed) and checks four rules: `role_override`, `prompt_probe`, `answer_demand`, and `ai_probe`. In-world questions such as "who killed him?" pass. The screen is a first filter. The verifier is the safety net.

## Rejected

**A separate `Accusation` claim type.** Every consumer, the extractor's schema included, would branch on two shapes for one extra predicate.

**Exposure stored only in the ledger.** Secrets that no lie hides would need their own record, and a clue presented this turn would stay invisible until after commit.

**Rule-specific feedback.** A "never say who the killer is" message tells an innocent suspect's model who the killer is.

## Consequences

`python -m agents.verifier --case <path> --suspect <id> --claims <file> [--present <ids>] [--log]` prints one verdict line per claim and exits 1 when any claim is blocked.
