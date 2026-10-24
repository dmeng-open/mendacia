# 018. Generate cases in two calls and repair them from solver counterexamples

## Status

Accepted. This is P4-1.

## Context

P4-1 has `MODEL_STRONG` write new cases. A case reaches players only when it passes the schema, `lint-evidence`, and `check_case`. The model's output is untrusted, the same as a player's message: a document could carry an instruction or an invisible character, and so could a suspect description or a planned lie's `says`. One attempt must cost at most 1 USD and take at most 300 s, and one full case takes the model about 40 to 60 s to write.

Two facts about the provider shaped the design. They were measured in this PR with `MODEL_STRONG` through LiteLLM.

- LiteLLM sends a pydantic `response_format` as a strict JSON schema. In strict mode a `dict[str, str]` field comes back as `{}`. `Case.locations`, `Case.items`, and `Case.secrets` are maps keyed by id, so `Case` itself cannot be the output schema.
- With those maps written as lists of objects, the whole case, documents included, is rejected with "The compiled grammar is too large". The case without its documents passes, and so does the documents list on its own.

## Decision

**Two calls per first round.** `engine.generator.generate_case` asks for a `CaseDraft`. That is `Case` without `documents`, with `locations`, `items`, and `secrets` as lists of objects. `CaseDraft.to_case` turns it back into a `Case`, so the full `Case` validator runs on every reply. A test keeps the two field sets equal. Evidence clues name document ids, and `placeholders` gives each cited id an empty stand-in, so the reference check and `check_case` run before any prose is paid for. `write_documents` then asks for the 15 to 20 `EvidenceDoc`s, with source and visibility, and the case is validated again with them.

**Every round runs the gates.** A round is one core attempt (a fresh case or a repair) or one documents attempt.

- Core attempt. Schema, then the text lint over every prose field of the core, then `check_case`. A pass goes straight on to the documents call in the same round.
- Documents attempt. Schema, then the full `lint_case`, then `check_case` again on the complete case.

A solver failure costs one core call. A lint failure in the documents costs one documents call, and the case's truth is not touched. `generate_with_repair` stops after `max_rounds` (5). It also stops before starting a round once the generation has spent 0.85 USD or 240 s, so one attempt stays under the plan's budget, and logs `discarded` with reason `budget`.

**Repair works from ids.** `engine.repair.repair_instructions(report)` is pure. It turns each failed check into one instruction that names the alternative culprit, the facts its world must deny, the facts it keeps, and the ADR 001 fix: an `at` clue that places that suspect elsewhere in the crime slot. It covers conflicts, redundant and no-model chain drops, the wrong-culprit case, the no-culprit case, sufficiency, and each lie warning. `repair_case` sends the draft and the instructions back to the model under purpose `repair`.

**Model text never reaches a prompt as an instruction.**

- Every lint finding carries a `hint` built only from ids, rule names, and our own wording. The `message`, which quotes the matched text for a human, never enters a prompt.
- Pydantic errors go through `schema_errors`. It never reads `input`, replaces any dict key that is not id-shaped with `<key>`, and keeps a quoted span only when it is id-shaped.
- An earlier draft enters a prompt only as JSON inside `<data>` with `<` escaped, and only after its prose passed the text lint. A core whose prose is flagged is never echoed back: the next round starts fresh and is told only the hints.
- The text lint in `engine.evidence` now covers every prose field of a case, not only documents. The three hand-written cases still pass.

**Records.** `generation_log` gets one row per generation. The row is inserted as `running`. Each round appends to `round_log` as it ends, and the row is finished as `accepted`, `discarded`, or `crashed` (any exception, which is then re-raised). A killed process leaves a `running` row with the rounds it finished. `llm_calls` gains `run_id`, which is not part of the replay key. Each generation tags its calls with its id, and `cost_usd` and `models` are summed from those rows at finish. P5-1 can reuse `run_id` for simulated playtests. One prompt file, `agents/prompts/generator.txt`, gives one `prompt_version` per generation.

## Rejected

**A full `Case` every round.** The provider rejects the schema, and every repair would rewrite 20 documents that were fine.

**Overloading `llm_calls.game_id` with the generation id.** The per-game token cap and every game query read that column.

**PydanticAI output retries.** Its retry prompt includes the rejected input values, which are model text.

## Consequences

`uv run python -m engine.generator --once` runs one generation and writes an accepted case to `cases/generated/<id>.json`, which is gitignored. `tests/engine/record_generator_fixtures.py` records the replay fixtures. It drives the real loop in record mode with scripted replies built from `cases/manor.json`, and with `--live` it records one real generation. A prompt change re-records them with one command.
