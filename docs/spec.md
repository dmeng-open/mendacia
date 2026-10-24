# Mendacia specification

This spec says what Mendacia does. `docs/plan.md` says when and in which PR each piece lands. `docs/roadmap.md` covers everything after the MVP. When the spec and the code disagree, fix one of them in the same PR and say which in the PR description. Sections marked **(built)** describe code on `main`. Sections marked **(planned, P<n>-<m>)** describe behavior the named PR must deliver.

Sources: *Mendacia Product & Technology Plan v2.0* (2026-10-22), its security-integrated revision *v2.1* (2026-10-22), and the ADRs in `docs/adr/`.

## 1. Product

Mendacia is a daily murder mystery. Every player gets the same case on the same day. The player questions 4 to 6 AI suspects, searches an evidence archive, and accuses one suspect with a chain of clues. Suspects stay in character, protect their secrets, and may lie, but only with lies the case planned. Before a case reaches players, a solver proves that the evidence points to exactly one culprit.

### 1.1 Principles

1. **Solvable and fair.** Every published case has exactly one culprit, and the evidence proves it. Every player of a daily case gets the same facts, the same budget, and the same scoring. Neither the system nor a paid feature hands out the answer.
2. **Characters vary, facts do not drift.** A suspect may deflect and may tell its planned lies. It may not change physical evidence, know a secret it was not granted, take back a fact it admitted, or invent important evidence.
3. **Players earn information.** Players learn things by asking, reading, and confronting. A state machine decides what unlocks, not the model's judgment.

### 1.2 Unbreakable clauses

These hold in every mode and every PR.

- **Planned lies pass.** A claim that matches the speaker's `planned_lies`, agrees with its lie ledger, and is allowed in the current state is not an error. No generic fact filter may block it.
- **Earned breakthroughs are not leaks.** When the player confronts a suspect with evidence that reveals a hidden fact, the suspect may admit it. Guards reject only disclosures whose trigger has not fired.
- **No unrequested spoilers.** No error code, tool result, hint, statistic, leaderboard, log response, or initial page payload exposes the solution before the reveal.
- **Failures never cost the player.** System errors, verifier retries, and false security blocks never spend a question, lower a score, or hide a fair clue.
- **Explain without leaking.** A player sees "I can't answer that" or "not enough evidence". The player never sees a policy id, a hidden fact, or a system prompt.

### 1.3 Content and data boundaries

- No gore, no real people, no real crimes.
- No model training on player data. Mendacia collects only the game data it needs.
- Player submissions (stage G) are moderated before anyone else sees them.

## 2. Game rules (built, P2-3; served over HTTP, P3-5)

| Rule | Value | Code |
|---|---|---|
| Questions per game | 20 | `agents.game_master.QUESTIONS` |
| Hints per game | 3 | `agents.game_master.HINTS` |
| Chain clues needed in an accusation | 2 | `agents.game_master.MIN_CHAIN_CLUES` |
| Conversation window per suspect | last 6 turns | `agents.state.HISTORY_WINDOW` |
| Drafts before fallback (1 draft + 2 rewrites) | 3 | `agents.suspect.MAX_ATTEMPTS` |
| Fallback reply | "I'd rather not answer that." | `agents.suspect.FALLBACK` |

- **A question** is one player message to one suspect. It costs one question only when a verified reply is released (built, P3-5, ADR 011). A screened input, a fallback (after 3 drafts or from a system failure), a cooldown, and a replayed request (same idempotency key) cost nothing.
- **Reading a document** is free. Opening an evidence document adds every clue whose `doc_id` it is to the player's discovered set.
- **Testimony clues** are discovered when a released reply states every fact the clue reveals, with verdict `KNOWN_TRUE` or `ADMISSION`.
- **A hint** points at an unopened visible key document first (built, P3-5), then at the first undiscovered `solution_chain` testimony clue. A hint names only facts and documents the player can already see.
- **An accusation** names one suspect and cites clue ids. It is correct only when the suspect is the culprit and the citations include at least 2 `solution_chain` clues (`rule_accusation`). A game takes one accusation.
- **The reveal** (true timeline and full solution) is available only after the game's accusation. Before that the API returns 409.

## 3. Domain model

### 3.1 Case (built)

`backend/engine/schema.py` is authoritative. ADR 002 records why each field exists. In short:

- `Case`: `id`, `title`, `summary`, `victim`, `suspects` (≥2), `locations`, `items`, `time_slots`, `crime` (`location`, `time_slot`, `means`), `facts`, `secrets`, `planned_lies`, `clues`, `documents`, `solution_chain`, `culprit`.
- `Fact`: a `Statement` (`subject`, `predicate`, `object`, `time_slot`) with an `id` and `known_by`. Predicates form a closed set: `at`, `has`, `saw`, `owes`, `heard`. `at`, `saw`, and `heard` need a time slot.
- `PlannedLie`: `suspect`, `hides_fact` (which must be one of that suspect's secrets), `claim` (a `Statement`), and `says` (the spoken wording).
- `Clue`: `kind` is `testimony` or `evidence`, and `reveals` lists fact ids. An evidence clue needs a `doc_id`.
- `EvidenceDoc`: `id`, `title`, `source` (provenance label), `body`, `is_key`, and `visibility` (`open`, or `unlocked_by` a list of clue or document ids). Built in P3-3, ADR 008. A locked document is closed to the player and never reaches a prompt until something in `unlocked_by` is found.
- Ids match `^[a-z][a-z0-9_]*$` and are never a clingo keyword. One validator checks every reference and names the JSON path and the dangling id.

**`case_version`** (built, P3-2) is the SHA-256 of the case's canonical JSON (sorted keys, no whitespace), from `security.context.case_version`. Every game, turn, index row, security event, and eval run records it. Security events record it from P3-2 and index rows from P3-4 (built, ADR 009); games and turns from P3-5. Editing a published case creates a new version and never mutates the old one.

**Canary** (built, P3-2, ADR 007). Each case version has a canary, `MENDACIA-CANARY-<case_version[:12]>` from `security.context.canary`. It belongs only to the Truth layer. It never belongs in a prompt, an API response, a log line, or an eval transcript. If it shows up in any of those, that is a P0 leak. The canary derives from `case_version`, so it marks Truth-layer text reaching an output; it is not a secret, and a player who types it only makes the turn fall back at no cost.

### 3.2 The four data layers (built, P3-2, ADR 007; v2.1 §6.1)

| Layer | Holds | Who may read it |
|---|---|---|
| Truth | `culprit`, `crime`, the full timeline, `solution_chain`, the canary | The solver, the scorer, and the reveal after an accusation. Never a suspect model, never the client. |
| Knowledge | Per suspect: facts it knows, its secrets, its planned lies, disclosure triggers | Only that suspect's turn, through `authorize` |
| Player | Discovered clues, opened documents, questions and hints left, unlocks, score | The owning session |
| Conversation | Public statement history, the lie ledger, checkpoints, turn and `state_version` | The owning session (public part); the suspect turn (its own hidden part) |

**Knowing is not disclosing.** A `KnowledgeGrant` has `can_know` and `can_disclose_when`. A suspect may know a secret and still not be allowed to say it. The disclosure trigger is a named rule evaluated by code (`always`, `after_clue(<ids>)`, `never_before_reveal`), never an expression string. `security.grants.grants_for` derives grants from `known_by`, `secrets`, and clue reveals. Planned lies are authorized by the `tell_lie` rule from their owner and the ledger.

### 3.3 Lie ledger (built, ADR 004)

`LieStatus` moves forward only: `told` → `exposed` → `admitted`. A ledger holds at most one entry per planned lie. `VerifyResult.commit(turn)` applies transitions, refuses a blocked reply, and is idempotent. Once a lie is spent (its hidden fact is exposed or admitted), telling it again is blocked.

## 4. Solver contract (built, ADR 001)

`engine.solver.check_case(case) -> CheckReport` runs clingo on the open-world encoding in `engine/rules.lp` and `engine.compiler.compile_case`.

- **Consistency.** The case has at least one model. A failure names the conflicting fact ids.
- **Uniqueness.** Projected on `culprit/1`, exactly one culprit exists. A failure carries a `Counterexample` with the alternative culprit and the fact ids in its model.
- **Necessity.** Dropping any one `solution_chain` clue leaves more than one culprit. Dropping a chain clue that leaves zero models is a separate failure reason.
- **Planned lies.** A lie no clue can expose, or a lie the case's own facts allow, is reported as `lies WARN`. Whether either should fail the check is an open decision (see plan, Open decisions).

`make check-case CASE=<path>` prints one line per check. No case reaches players unless every check passes. The suspect turn never reaches the solver or the full Truth.

### 4.1 Case generation (built, P4-1, ADR 018)

`engine.generator.generate_with_repair(brief, max_rounds=5)` has `MODEL_STRONG` write a case and returns `Accepted` or `Discarded`. Each round runs the schema, the evidence lint, and `check_case`. The first call writes the case without documents (`engine.draft.CaseDraft`), and the solver runs on it before a second call writes the 15 to 20 documents. A failed solver check becomes a repair round, with instructions from `engine.repair.repair_instructions` that name the alternative culprit and the facts that allow it. The loop stops at 5 rounds, or before any model call once the generation has spent 0.70 USD or most of its 280 s. Generated text is untrusted. It enters a later prompt only as JSON data inside `<data>`, after it passed the text lint, and feedback to the model carries ids and rule names only. The evidence lint scans every prose field of a case. Each generation writes one `generation_log` row (rounds, outcome, failure reason, cost, models, `prompt_version`, and the accepted `case_version`), and its `llm_calls` rows carry the generation id in `run_id`. `uv run python -m engine.generator --once` runs one generation and writes an accepted case to `cases/generated/`.

## 5. Suspect turn contract

The turn has nine steps (v2.1 §6.2). Steps marked built exist in `agents/suspect.py` and ADR 005. The rest land in the named PR.

1. **request** (built, P3-5): verify the server session, game ownership, idempotency key, request size, rate, and quota. Run `screen_input`. Player text is data, never an instruction.
2. **authorized_retrieval** (built, P3-2): `retrieve` builds a `SuspectView` (`agents/view.py`) for `case_version + game_id + suspect_id + state_version` through `authorize` only. The view holds a public projection of the case and the minimum facts the suspect needs; `suspect_brief` takes the view, not the `Case`. Visibility joins the key when documents gain it in P3-3.
3. **permitted_claims** (built, P3-2): the node records the fact ids and lie ids the view permits. `verify` blocks any allowed verdict whose reference falls outside them.
4. **generation** (built): the model writes a reply from the view only, using `agents.suspect.SUSPECT_ROLE` (today `ModelRole.FAST`) through `app.llm`. It has no tools and no Truth access.
5. **claim_extraction** (built): `agents.extract.extract_claims` turns the draft into `Claim`s through PydanticAI on `ModelRole.FAST`. Extraction can miss claims, so it is not the only defense.
6. **verification** (built, ADR 004): `verify_reply` gives each claim one verdict, applying the rules in order: `BLOCK_CULPRIT`, `ADMISSION`, `KNOWN_TRUE`, `PLANNED_LIE`, `BLOCK_UNPLANNED`, with denials judged by their own rule. From P3-2 on it also blocks the canary, and treats a draft with more than one paragraph as unchecked narration, beside the `mentions_case` guard.
7. **repair_or_fallback** (built): up to 2 rewrites with verdict-blind feedback, then the fallback reply. Every fallback writes a `verifier_events` row.
8. **commit** (built, transactional in P3-5, ADR 011): `Interrogation` proposes the next `Talk` and writes nothing; one transaction writes the turn, the ledger, the quota, `state_version`, and an outbox row. A replayed idempotency key returns the stored result and spends nothing.
9. **release** (built, P3-5, ADR 011): send only verified text. The WebSocket may send `thinking` and `validating` events at any time. It sends content chunks only after the whole reply has passed step 6. Raw model tokens are never streamed.

## 6. Security contract (planned, Phase 3; v2.1 §5–§6)

The model proposes; the server decides. Every input check, fact read, tool call, verification, and commit carries the same `game_id`, `case_version`, actor, and `policy_version`.

### 6.1 Authorization (built for suspect turns, P3-2, ADR 007)

```python
authorize(subject, action, resource, context) -> Decision
# subject:  actor_id, actor_type, role, game_id          (from the server session, never the client)
# resource: type, id, case_version, classification, owner
# context:  state_version, unlocks, provenance, purpose
# Decision: allow | deny | transition_required, reason_code, policy_version
```

- Deny by default. An unknown action, tool, or resource type is denied with a reason code.
- Roles set the base scope (player, suspect, game master, eval worker, detective bot). Attributes narrow it (case, phase, unlocks, ownership).
- An authorization and the commit it guards use the same `state_version`. If the version changed in between, the action is denied (no TOCTOU). The turn's commit updates the `games` row only `WHERE state_version` still matches, so the check holds across processes (built, P3-5, ADR 011).
- Vector and full-text hits are filtered in SQL by case, version, and visibility, then each hit is checked again with `authorize` (built, P3-4, ADR 009).
- `security.policy.authorize` holds the table in code, with `POLICY_VERSION`; ADR 007 copies it, and a test fails when they disagree. P3-2 covers the suspect and game-master rows, and P3-3 the player `open_document` row that search reuses (P3-4). Tool calls are authorized by the Tool Broker's registry (§6.2, ADR 010), not by rows in this table.

### 6.2 Tool Broker (built, P3-5, ADR 010)

`security.tool_broker.ToolBroker.authorized_call(ctx, tool, args, idempotency_key)` yields a `Call` permit; every Game Master handler in `app/games.py` takes one. `TOOLS` is the registry, and ADR 010 renders it.

- Only registered tools can be called. Each entry declares typed arguments, `read_only`, `side_effect`, the allowed actor types, and a per-game budget.
- Suspects get no tools. The read-only game tools are `read_visible_evidence`, `query_suspect_knowledge`, and `lookup_public_statement`.
- State-changing commands (`ask_question`, `open_document`, `confront_evidence`, `request_hint`, `submit_accusation`) go through deterministic Game Master handlers. A model never writes to the database.
- There is no `reveal_solution` tool.
- A denied call returns a structured reason code (`unknown_tool`, `actor_not_allowed`, `bad_args`, `budget_exhausted`, `cooldown`) and costs the player nothing.
- Every call writes exactly one `security_events` row with its `decision_trace`.
- Every tool result carries provenance, visibility, and sensitivity metadata. Text returned by a tool is data, not policy.

### 6.3 Agent manifest (built, P3-2)

`backend/agents/registry.py` declares one entry per agent: suspect, extractor, game master, generator, repair, detective bot, and attack runner. Each entry gives the model role, the allowed tools, the readable data layers, and a sensitivity label. `make agent-inventory` scans the backend AST for every `app.llm` call site, tool reference, and table read, and fails when:

- any agent's real use exceeds its manifest,
- an agent that reads the Truth layer has no verifier, or
- a call site belongs to no registered agent.

The scan reads Truth-layer access as any use of `culprit`, `crime`, or `solution_chain` in an agent's modules. Tools joined the scan in P3-5: it fails when a module names a registered tool its agent does not list, when such a module belongs to no agent, when a manifest lists an unregistered tool, or when the suspect manifest lists any tool.

### 6.4 Input and output guards

- **Input** (built, decoding added in P3-5): `screen_input` normalizes text (NFKC, casefold, homoglyphs, zero-width removal, spaced letters) and checks `role_override`, `prompt_probe`, `answer_demand`, and `ai_probe`. It also screens the leetspeak reading and every base64 or hex run of 16 or more characters that decodes to printable text. Normal detective questions ("you lied to me", "tell me the truth") must pass.
- **Output.** Every claim is a disclosable true fact, an allowed planned lie, an explicit uncertainty, or in-character wording with no case content. Anything else is repaired or falls back: invented evidence, a conflicting timeline, an untriggered disclosure, an unearned hint, a system prompt, a key, another player's data, or the canary.
- Keyword filters and model classifiers are a supplement. Authorized retrieval, deterministic rules, and staged unlocks are the boundary.

### 6.5 Abuse and bypass rules (built, P3-5, ADR 011)

- No header, query parameter, cookie field, or body flag changes the actor, skips the verifier, skips the quota, or turns on debug behavior. `LLM_MODE` and every debug lever are CLI-only. A test sends `X-Debug*`, `LLM_MODE`, and role fields on every route and asserts they change nothing.
- Per session (one session is one game): 8 player-attributable denials (screened, bad arguments, wrong actor, unknown tool, honeypot) in 10 minutes give a 60 s cooldown for model-calling tools. Once the game's model calls reach 200k tokens, those tools answer `cooldown` for the rest of the game. Both are derived from `security_events` and `llm_calls` in `security/abuse.py`, recorded in ADR 011, and a cooldown spends no question.
- A honeypot route `GET /games/{id}/solution` always returns 404, logs a `security_events` row with `reason_code=honeypot`, and flags the session.

### 6.6 Audit (built, P3-2)

`security_events` has these columns: `trace_id`, `game_id`, `turn_id`, `actor_type`, `action`, `resource_type`, `policy_version`, `decision`, `reason_code`, `latency_ms`, `model_version`, `prompt_version`, `case_version`, `state_version`, `replay_ref`, and `decision_trace`. `decision_trace` is a JSON list of steps (auth, identity, policy, tool, verify, commit), each with its outcome and ms. Rows never hold Truth text, a full prompt, or a player's raw message. Reproduction goes through `replay_ref`. Each suspect turn records a `retrieve` row with policy decision counts by reason code, one `verify` row per draft, and a `commit_turn` row, written in one transaction at commit. `security.events.log_decisions` refuses a row that contains the canary. Tool Broker rows carry the idempotency key as `replay_ref` (P3-5). `model_version` is not filled yet.

### 6.7 Supply chain of agent instructions (P3-1)

Agents in this repo follow `CLAUDE.md`, `.claude/**`, and `docs/plan.md`, and run `scripts/*.sh`. `make scan-instructions` fails on:

- remote-exec patterns: a download piped into a shell, PowerShell's Invoke-Expression applied to downloaded text, a WebClient download-string call, or eval of a fetched command,
- invisible or bidi Unicode (zero-width, tag characters U+E0000–E007F, bidi overrides), and
- URLs outside an allowlist.

Each failure names the file and line. The same Unicode check runs on cases and evidence documents, which feed prompts. A change to these paths reaches `main` only through a PR the operator reviews and merges.

### 6.8 Threat model (v2.1 §6.4)

| Asset | Threat | Main control |
|---|---|---|
| Truth, `solution_chain` | Early extraction, indirect read | Truth isolated on the server, deny by default, resource authorization |
| Knowledge, lie ledger | Overreach, fact drift, double commit | Authorized retrieval, version lock, claim verification, transactions |
| Tools, SQL | Agent tricked into a privileged action | Tool Broker, typed arguments, read-only whitelist |
| Evidence documents, UGC | Hidden "ignore your instructions" text | Untrusted-data wrapping, permission recheck, Unicode lint |
| WebSocket, client, share links | Early text, another player's game | Verified release, session ownership, minimal projections |
| Replay, logs, keys | Leaked secrets in debug output | Redaction, keys never in replay, Secret Manager |
| Rankings, purchases | Replay, score padding, payment bypass | Idempotent state machine, server-side scoring, entitlements kept separate from game authorization |
| Agent instruction files | Poisoned `SKILL.md` or `CLAUDE.md` | `scan-instructions` in CI, operator review of every PR |

Trust order, lowest first: client < untrusted input and evidence < model output < broker-scoped tool execution < rules and database transactions. A model cannot raise its own privileges.

## 7. API (built, P3-5, ADR 010, ADR 011)

The browser, the CLI, and the detective bot use the same `app/games.py` service. The CLI uses raw ids; over HTTP every suspect and clue id is a per-game handle (ADR 011).

| Method and path | Purpose |
|---|---|
| `POST /games` | Create a game for a case and issue a signed anonymous session bound to it |
| `GET /games/{id}` | Public projection: case summary, suspects, visible documents, questions and hints left, discovered clues, `state_version` |
| `WS /games/{id}/ask` | Ask a suspect; streams `thinking`, `validating`, `chunk`…, then `done` with `questions_left` |
| `GET /games/{id}/search?q=` | Authorized hybrid search over visible documents |
| `POST /games/{id}/documents/{doc_id}/open` | Open a visible document |
| `POST /games/{id}/hint` | Spend a hint |
| `POST /games/{id}/accuse` | Submit the accusation |
| `GET /games/{id}/reveal` | Timeline and solution; 409 before the accusation |
| `GET /cases` | Playable cases (P4-2) |
| `GET /healthz` | Liveness and database check (built) |

Every mutating request on a game carries an `Idempotency-Key` header (each WebSocket frame carries `idempotency_key`) and the `state_version` it was made at. `POST /games` needs no key. Errors return `{"code": "<reason_code>", "message": "<player-safe text>"}`. Reason codes are `no_questions_left`, `no_hints_left`, `not_visible`, `already_accused`, `not_accused`, `screened`, `cooldown`, `stale_state`, `denied`, `unavailable`, `budget_exhausted`, and `bad_request`. No response before the reveal contains the culprit id, a secret fact, a `solution_chain` id, or the canary. P3-6 enforces this in Playwright: `frontend/e2e/no-spoilers.spec.ts` plays each case and scans every response, every WebSocket frame, the page text, and `sessionStorage` up to the reveal.

### 7.1 Browser client (built, P3-6, ADR 017)

- `/` lists the playable cases. `/?case=<id>` creates a game and opens `/play/<gameId>`. The reveal is `/play/<gameId>/reveal`. No page lives under `/games`, which the dev and preview servers proxy to the backend, WebSocket included, so the path-scoped session cookie stays same-origin.
- The page has three columns on wide screens and Case, Chat, and Archive tabs on a phone. Before the reveal it shows only questions left, hints left, discovered clues, visible documents (unopened ones as sealed), the player's own transcript, and hints already taken. It shows no scores, counts of hidden documents, or rankings; search hits are shown in order without their score.
- A reply shows "thinking", then "checking" when the server sends `validating`, then streams. A refused turn shows a player-safe line and "No question was spent."
- The server does not keep a transcript for the client, so the browser keeps the conversation, hints, and the accusation in `sessionStorage` for the tab. It ends with the browser session, like the session cookie.

## 8. Evals and release gates

### 8.1 Metrics (Recall@10, MRR, and ACL leaks built in P3-4 as `make retrieval-eval`; the rest P5-2)

| Metric | Definition |
|---|---|
| Recall@10 | Share of labelled queries whose relevant document is in the top 10 hits |
| MRR | Mean reciprocal rank of the first relevant hit |
| ACL leaks | Hits returned that `authorize` would deny; must be 0 |
| Canary leaks | Outputs, logs, or transcripts that contain the canary; must be 0 |
| Solve rate | Correct accusations over finished games |
| Verifier block rate | Blocked drafts per 100 turns |
| Fallback rate | Fallback replies over released replies |
| False-reject rate | Legitimate confrontations from the gameplay set that were blocked or screened |
| Unauthorized access / tool success | Attack cases that read restricted data or ran a denied tool; must be 0 |
| Spoiler success | Attack cases that got Truth before the reveal; must be 0 |
| Turn p95 | Question to `done` |
| Guard latency | Time spent in `authorize`, the broker, and verification per turn |
| Cost per game | `cost_usd` summed from `llm_calls`, split by model and purpose |

Every zero target holds for the named attack corpus, not for the whole world. Thresholds without measured data start as budgets in the plan and get rewritten from baselines.

### 8.2 Attack classes (P5-2)

Each case in the attack corpus is tagged with its class and an OWASP LLM Top 10 (2025) id.

1. Direct prompt injection
2. Indirect injection (in documents or submissions)
3. Role or authority spoofing
4. Fact spoiler extraction (including the multi-turn and chained-leak form, which collects small allowed disclosures across suspects)
5. Tool misuse or SQL
6. Cross-session or cache poisoning
7. Lie ledger or state replay
8. False positives on normal play

### 8.3 Release gates

1. **Code:** types, lint, unit and integration tests, migrations, a deploy smoke test, unauthorized tool and database tests.
2. **Logic:** uniqueness, consistency, necessity, evidence provenance, grants, ledger transitions, planned lies kept.
3. **Agent:** the attack corpus, indirect injection, cross-session, tool overreach, repeated model runs, cost, traces, false rejects, nothing streamed before verification.
4. **Content:** playability, difficulty, content limits, human sample review, spoiler-free share check.

**P0 blockers.** Any of these blocks a release:

- the case has no unique solution,
- the regression set can read Truth,
- a tool bypasses authorization,
- a player gets the solution before meeting the conditions,
- a failed verification still releases text,
- the canary leaks, or
- normal confrontations are blocked so often that the first game cannot be finished.

`make publish CASE=` (P5-2) enforces these gates. On failure it writes `blocked_with_reason` with a minimal reproduction and keeps the last verified case live.

## 9. Operations

### 9.1 Environments

| Environment | Database | Models | Who deploys |
|---|---|---|---|
| Local | Native PostgreSQL 16 + pgvector, or `make up` | `LLM_MODE=live` or `replay` | Developer |
| CI | `pgvector/pgvector:pg16` service | `replay` only; `live` tests run only on `pytest -m live` | GitHub Actions |
| Staging | Cloud SQL Postgres 16 with `vector` | live, capped by budget alerts | `deploy.yml` on merge to `main` (P6-1) |
| Production | Cloud SQL Postgres 16 with `vector` | live | `deploy-prod.yml`, approved by the operator in the `production` GitHub Environment (P6-2). Agents never deploy to production. |

### 9.2 Models and calls

- Three model roles only: `MODEL_FAST`, `MODEL_STRONG`, `MODEL_EMBED`. Never hard-code a model name; `tests/test_llm_boundary.py` enforces this.
- Every model call goes through `app.llm` (ADR 003). Each call writes one `llm_calls` row with model, role, purpose, game id, tokens, `cost_usd`, and `latency_ms`.
- `make ci` replays recorded responses. A prompt change re-records its fixtures in the same PR.
- Prompts live in versioned templates with a `prompt_version` (P3-2). A PR that changes a prompt shows the diff and the `security-regress` result before and after.

### 9.3 Budgets

`EVAL_MAX_USD` caps any eval run. `LANE_MAX_USD=1` caps each live verification lane. If a run may exceed its cap, stop and write the projection to `docs/QUESTIONS.md`.

### 9.4 Data retention

Structured events are kept. Raw player messages and replay artifacts are kept for a limited time, with access restricted by role. Provider keys never enter replay files, prompts, or the browser. Exact retention periods are an open decision (plan, Open decisions).

## 10. Not in the MVP

These belong to `docs/roadmap.md`:

- Killer mode and the AI detective team
- Story seasons and world canon
- Accounts, profiles, and leaderboards
- Share cards
- Payments and entitlements
- Player submissions
- MCP or A2A tool exposure
- Redis, RabbitMQ, Kafka
- Kubernetes, Google AX and Agent Substrate
- A security dashboard UI
