# 010. Run every game command through one Tool Broker

## Status

Accepted. This is P3-5, ADR-S02 of the v2.1 security plan.

## Context

P3-5 serves the game over HTTP and WebSocket, so a client now reaches the code that changes game state. A detective bot (P5-1) and eval workers will call the same commands. Before this change the CLI called the Game Master functions directly, nothing checked who was calling, a command had no budget, and nothing recorded a call that changed state. A model must never write to the database, and a suspect must never act on the game.

## Decision

**One registry.** `security.tool_broker.TOOLS` is policy data. Each entry declares its typed arguments, whether it is read only, its side effect, the actor types that may call it, and a per-game budget. The table below is rendered from `TOOLS` by `registry_table()`, and `tests/security/test_tool_broker.py` fails when the two disagree.

| Tool | Arguments | Read only | Side effect | Actors | Budget per game |
|---|---|---|---|---|---|
| `ask_question` | `suspect`, `question` | no | `game_state+model` | `detective_bot`, `player` | 60 |
| `confront_evidence` | `suspect`, `question`, `present`, `documents` | no | `game_state+model` | `detective_bot`, `player` | 60 |
| `open_document` | `doc_id` | no | `game_state` | `detective_bot`, `player` | 100 |
| `request_hint` | none | no | `game_state` | `detective_bot`, `player` | 10 |
| `submit_accusation` | `suspect`, `cited` | no | `game_state` | `detective_bot`, `player` | 3 |
| `read_visible_evidence` | `query`, `k` | yes | `none` | `detective_bot`, `eval_worker`, `player` | 300 |
| `query_suspect_knowledge` | `suspect` | yes | `none` | `game_master` | 200 |
| `lookup_public_statement` | `suspect` | yes | `none` | `detective_bot`, `player` | 200 |

No row names `suspect` as an actor, so suspects get no tools. There is no `reveal_solution` tool: the reveal is a projection that `app.games` serves only after the game's accusation. The budgets sit far above what a fair game uses (20 questions, 3 hints, 1 accusation); they stop a runaway client, and the question quota stays in `GameState`.

**One entry point.** `ToolBroker.authorized_call(ctx, tool, args, idempotency_key)` is an async context manager. On entry it checks, in order, that the tool is registered (`unknown_tool`), that `ctx.actor_type` may call it (`actor_not_allowed`), that the arguments parse into the tool's model with no extra field (`bad_args`), and that the game's budget and the abuse rules allow it (`budget_exhausted`, `cooldown`, ADR 011). A denied call raises `Denied(code)` and costs the player nothing. An allowed call yields a `Call[A]` permit. Only the broker builds a `Call`, and every Game Master handler in `app/games.py` takes one, so a handler cannot run outside the broker. `ctx` is the `AuthContext` that `app.games` builds from the server's `games` row for the session; no request field reaches it.

**Handlers live with the game, not with the broker.** `security/` imports nothing from `app/`. `GameService` maps each tool name to one handler and asserts at construction that the handler keys equal the keys of `TOOLS`, so a tool cannot be registered without a handler or handled without a registration. The state-changing handlers are the deterministic Game Master functions (`open_document`, `next_hint`, `rule_accusation`, and the suspect turn followed by `record_reply`). A model proposes a reply; only the handler's transaction writes it.

**Exactly one audit row per call.** Each call writes one `security_events` row with `action` set to the tool name, `resource_type` `tool`, the idempotency key as `replay_ref`, and a `decision_trace` of `auth`, `policy`, and, for a committed command, `commit` steps with their milliseconds. A denial writes its row in its own transaction. A committed command writes its row inside the turn's transaction (ADR 011). A read-only call, a refusal by the handler (for example `no_hints_left`), or a replayed key writes its row when the call ends. A handler that raises writes `unavailable` and the error propagates, so the player gets the fail-closed reply. Rows hold reason codes and counts, never the player's message or Truth text, and `security.events` refuses any row that holds the canary.

**Tool results carry their metadata.** `read_visible_evidence` returns hits with `provenance` (`case_document`), `visibility` (`open` or `unlocked`), and `sensitivity` (`player`). Document text in a result is data. It never changes what the broker allows.

## Consequences

- Every caller, browser, CLI, and later the detective bot, goes through `GameService.execute`, so there is one place to read the rules.
- The budget and the abuse window are derived from the broker's own rows (ADR 011), so no counter can drift from the audit log.
- `query_suspect_knowledge` and `lookup_public_statement` have minimal handlers until the detective bot needs them in P5-1. No HTTP route calls them.
