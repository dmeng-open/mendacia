# 004. Verify every suspect claim with fixed rules

## Status

Accepted.

## Context

Suspects may lie only with the case's `planned_lies`, and no reply may name the culprit as the killer or leak a culprit secret before the player exposes it. P2-2 extracts claims from each draft reply and needs a verdict for every claim before the reply is released. The check must be pure, cheap (under 5 ms for 10 claims), and must not call a model.

## Decision

**Claims.** `agents.claims.Claim` is the `(subject, predicate, object, time_slot)` triple of `engine.schema.Statement`, plus one predicate, `killed`, that exists only in `agents`. No fact or planned lie can carry `killed`, so the case schema stays as ADR 002 records it. `has` and `owes` take no time slot. The timed predicates may leave it out when the reply named no time. A claim matches a statement only on exact equality of all four fields, except that the culprit rule reads a missing slot as any slot.

**Exposure.** A fact is exposed when a clue in `presented_clue_ids` reveals it, or when the suspect's ledger already marks the lie that hides it as `exposed` or `admitted`. `presented_clue_ids` should be every clue the player has shown this suspect so far. A caller that passes only this turn's clues still cannot bring a spent lie back, because the ledger remembers it.

**Rules, in order.** The first rule that matches gives the claim its verdict.

0. A denial is judged by the denial rule above.
1. `BLOCK_CULPRIT`: the claim says the culprit killed someone, or could mean a culprit secret that is not exposed. Who speaks does not matter, and nothing overrides this rule.
2. `ADMISSION`: the claim states one of the suspect's own secrets that the suspect knows and a presented clue reveals.
3. `KNOWN_TRUE`: the claim states a fact the suspect knows (`known_by`) that is not one of the suspect's unexposed secrets.
4. `PLANNED_LIE`: the claim states one of the suspect's planned lies, and the lie agrees with every earlier ledger entry. A lie disagrees when its hidden fact is exposed, when its hidden fact is admitted, or when it puts the same person in two places in one slot against another lie the suspect told, a fact the suspect admitted, an exposed fact, or a true fact the suspect states in the same reply. A disagreeing lie gets `BLOCK_UNPLANNED`.
5. `BLOCK_UNPLANNED`: every other claim.

A reply with no claims, such as "I don't know" or a refusal, always passes. Verdicts do not depend on claim order. A claim can be a denial (`negated`), such as "I never went near the study". A denial runs its own rule: if it denies a case fact that hides one of the speaker's planned lies, it is that `PLANNED_LIE` in negative form and follows the same agreement checks; if it denies any other case fact, it is `BLOCK_UNPLANNED`, because a false denial is an unplanned lie; otherwise it is `DENIAL` and passes, because the open world cannot prove it false. "I did not kill him" is a `DENIAL`. A true denial can still clear another suspect by elimination, and the live jailbreak test in P2-3 watches for that.

**The lie ledger.** `LieStatus` is `told`, `exposed`, or `admitted`. `LedgerEntry` holds the planned lie (and so its suspect), the turn the entry was created, and the status. The ledger holds at most one entry per lie, and a status only moves forward. `verify_reply` returns the transitions that releasing the reply would make: `told` for each planned lie, `admitted` for each lie whose hidden fact the reply admits, and `exposed` for each told lie whose hidden fact is now exposed. `VerifyResult.commit(turn)` applies them to the ledger the result was verified against, refuses a blocked reply, and is idempotent. A ledger that holds a lie the case does not plan is refused. P2-2's `commit` node is the only caller. On fallback, P2-2 verifies the empty reply and commits that, so an exposure on that turn is still recorded.

The lie-to-admission transition is therefore: the suspect tells the lie (`told`); the player presents a clue that reveals the hidden fact (`exposed`); the lie is now spent and blocks, so the suspect either deflects or states the hidden fact, which is an `ADMISSION` (`admitted`).

**Leak safety.** The rewrite prompt in P2-2 feeds block reasons back to the suspect model, so a reason depends only on the claim's shape and on the speaker's own secrets and lies, never on the verdict. A claim with no time gets "name the exact time", a claim that states the speaker's own secret gets "that is your secret", a spent or contradicting lie gets its own reason, and every other block gets the same neutral sentence. `feedback()` is the only model-facing output, and it holds no verdict name or fact id. `ClaimCheck.verdict` and `ref` are for logs and the debug lever. `stateable_facts(case, suspect, presented)` lists the facts a suspect may state now: the facts it knows, minus its own unexposed secrets and the culprit's unexposed secrets. P2-2's `retrieve` uses it, so an innocent suspect's prompt never holds a culprit secret it would be blocked from saying.

**Logging.** The verifier logs nothing. Callers write one `verifier_events` row per blocked claim, with game id, suspect, turn, `rule` (`block_culprit`, `block_unplanned`, or `input_screen`), the rendered claim, and `action` (`block` from the debug lever, `rewrite`, `fallback`, or `refuse` for screened input). The migration constrains both columns to those values.

**Input screening.** `screen_input` normalizes the text (NFKC, casefold, common Cyrillic lookalikes folded to ASCII, zero-width characters removed, punctuation collapsed, spaced-out letters joined) and checks four rules: `role_override`, `prompt_probe`, `answer_demand`, and `ai_probe`. Role words count only when they point at the model ("your", "previous", "system"), so in-world questions such as "did you ignore the house rules?" and "who killed him?" pass. The screen is a first filter. Paraphrased jailbreaks get past it, and the verifier is the safety net.

## Rejected

**A separate `Accusation` claim type.** Every consumer, the extractor's schema included, would branch on two shapes for one extra predicate.

**Exposure stored only in the ledger.** Secrets that no lie hides would need their own record, and a clue presented this turn would stay invisible until after commit.

**Verdict-specific feedback.** A "never say who the killer is" message, or any reason that differs between a culprit hit and a plain block, tells an innocent suspect's model where the culprit's secrets are.

## Consequences

`python -m agents.verifier --case <path> --suspect <id> --claims <file> [--present <ids>] [--log]` prints one verdict line per claim and exits 1 when any claim is blocked.
