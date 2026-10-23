# 011. Release only verified text, charge only for it, and fail closed

## Status

Accepted. This is P3-5, ADR-S03 of the v2.1 security plan.

## Context

P3-5 puts the suspect turn behind a WebSocket. Three questions follow. What may reach the player, and when? What costs the player a question? What happens when the database, the policy, or the verifier fails halfway through a turn? Before this change a turn's state lived in three places: the LangGraph checkpointer held each suspect's ledger and history, the `commit` node wrote audit rows on its own connection, and the CLI held the quota in memory. No transaction spanned the three, so a crash could leave the ledger ahead of the quota.

## Decision

**One row is the game.** The `games` row holds the case version, `GameState` as JSONB, `state_version`, the created and finished times, and `abuse_flag`. `GameState` now holds each suspect's `Talk` (ledger, presented clues, history) and the accusation. The suspect graph runs with no checkpointer: `Interrogation.ask` starts from the stored `Talk`, returns the proposed next `Talk` and the turn's audit rows, and writes nothing. The `commit` node still authorizes `commit_turn` at the turn's `state_version`.

**One transaction per turn.** `GameService._commit` updates the `games` row with `WHERE state_version = :v`, inserts the `turns` row (idempotency key, `args_hash`, released reply, verdict summary, cost), inserts the `outbox` row, and inserts the graph's audit rows and the broker's row, all on one connection. The update runs first, so it takes the row lock. A second writer at the same version waits, then updates nothing. It then looks up its own key: if a parallel request with the same key won, it returns that stored turn; otherwise it answers `stale_state`. Authorization and commit share one `state_version` across processes, which closes the gap ADR 007 left open. A suspect turn now authorizes at the `games` row's `state_version`, not at the count of that suspect's committed turns as ADR 007 described.

**The unit of verified output is the whole reply.** A reply is released only after every claim in it passed the verifier (ADR 004, ADR 005) and the turn committed. The WebSocket sends `thinking` when the frame is accepted and `validating` when the first draft enters claim extraction. It sends `chunk` messages only after the commit, cut from the committed text at word boundaries (two or more for a reply of two or more words), then one `done` with `questions_left`, `state_version`, and the newly discovered clues. Raw model tokens are never streamed. A screened, fallback, or refused turn sends only a fixed in-character line. This takes default 4 of the plan: every reply is verified whole, then chunked.

**What costs a question.** Only a released verified reply costs one. This takes default 3 of the plan. Nothing else does:

| Turn | Commits | Costs a question |
|---|---|---|
| Released verified reply | yes | yes |
| Graph fallback after 3 drafts (`I'd rather not answer that.`) | yes, so the history stays true | no |
| Screened input (`code=screened`) | no | no |
| Repeated idempotency key | no, returns the stored turn | no |
| Stale `state_version` (`code=stale_state`) | no | no |
| Cooldown, budget, or rule refusal (`not_visible`, `no_questions_left`, `already_accused`) | no | no |
| Database, policy, verifier, or timeout failure (`code=unavailable`) | no | no |

A hostile but valid follow-up is a question like any other. If the verifier releases a reply, it costs one.

**Idempotency.** Every mutation carries a key: the `Idempotency-Key` header over HTTP (400 `bad_request` when missing) and `idempotency_key` in each WebSocket frame. A stored key returns the stored outcome with `replayed=true` before any model call. The same key with different arguments or a different tool is `bad_request`. Inside one process every command on a game runs under that game's lock, so a duplicate waits and then replays the stored turn, and a burst of asks at one `state_version` runs the model once and refuses the rest with `stale_state` before any model call. Stale and reused-key refusals write their `security_events` row like every other call. Across workers a duplicate in flight at the same moment may run the model twice. The loser's tokens are logged in `llm_calls` and nothing is charged, because the loser commits nothing. We accept this instead of a `pending` turn state that would need expiry and recovery.

**Abuse thresholds.** `security/abuse.py` derives both budgets from rows the system already writes; there are no counter columns.

- Strikes: 8 player-attributable denials (`screened`, `bad_args`, `actor_not_allowed`, `unknown_tool`, `honeypot`) in 10 minutes put the game on a 60 s cooldown for model-calling tools. A verifier block is the model's error and is never a strike.
- Token cap: once the game's `llm_calls` rows sum to 200,000 tokens, model-calling tools answer `cooldown` for the rest of the game. A cumulative sum never falls back under the cap, so a recurring 60 s cooldown would re-trigger at once; the cap is a hard stop for the game. `docs/QUESTIONS.md` records this default.
- A cooldown spends no question, and documents, hints, the accusation, and search stay available.

A session is one game: `POST /games` issues a cookie bound to that game's id, so "per session" and "per game" are the same budget.

**Fail closed.** `GameService.execute` runs each command under a 15 s timeout. A timeout, a database error, a policy error, or a verification error returns the in-character fallback with `code=unavailable`, commits nothing, and spends nothing, so a retry with the same key runs again. The broker writes an `unavailable` row when it can still reach the database.

**Bypass guards.** Routes read only the path id, the signed session cookie, the `Idempotency-Key` header, the search `q`, and the body or frame. Request models ignore unknown fields, so `role=game_master` is dropped rather than rejected. A test checks that no route declares any other header, query, or cookie input, and plays a game with debug headers, `LLM_MODE`, and role fields everywhere to show nothing changes. The cookie is an HMAC over the game id and a random token with `SESSION_SECRET`, `HttpOnly`, `SameSite=Strict`, and `Path=/games/{id}`; the server also checks the token's SHA-256 against the `games` row. A forged cookie gets 403, or a 4403 close before the WebSocket is accepted. `GET /games/{id}/solution` is a honeypot. It always returns 404. When the request's cookie owns the game it logs `reason_code=honeypot`, sets `abuse_flag`, and counts as a strike. Without that cookie it logs `honeypot_anonymous` and changes nothing, so a stranger who knows a game id cannot put that game into cooldown. Over HTTP a request must name suspects and clues by their handles; a raw id does not parse.

**Public ids.** Every suspect id and clue id in a response before the reveal is a per-game handle, `h_` plus the first 10 hex digits of HMAC(`SESSION_SECRET`, `game_id:id`). Requests map handles back by recomputing them over the case's ids. Document ids stay raw: a document is visible data, not Truth. The CLI uses raw ids. The reveal names raw ids.

## Consequences

- The `checkpoint*` tables from P2-2 are no longer written. This PR leaves them in place; a later cleanup can drop them.
- `turns.cost_usd` sums the game's `llm_calls` since the turn started, which is approximate if two turns of one game overlap.
- `verifier_events` rows from rewrites and fallbacks stay outside the turn transaction. They describe attempts, not state.
- The game routes need `SESSION_SECRET`. Without it they answer 503 `unavailable` and `/healthz` still works.

- Screening decodes plain base64, plain hex, and leetspeak. It does not catch base64 split by spaces, double encoding, URL encoding, ROT13, reversed text, or a phrase split across turns. Screening is a supplement (spec §6.4); the boundary is that suspects see only authorized facts and every reply is verified.
- `POST /games` has no rate limit, so one client can open many games. Per-client limits belong to the deployment (P6).
