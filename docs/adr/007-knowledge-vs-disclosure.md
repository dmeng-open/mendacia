# 007. Separate knowing a fact from disclosing it, and authorize every fact a suspect sees

## Status

Accepted. This is ADR-S01 of the v2.1 security plan.

## Context

Before this change, `suspect_brief` read the whole `Case`. The brief filtered what it printed through `stateable_facts`, but the code that wrote the prompt could reach `case.culprit`, `case.crime`, and `case.solution_chain`. A bug or a careless edit in the brief would have put the solution in front of the model. Nothing recorded which facts a turn was allowed to use, there was no server-side identity, and `verifier_events` was the only audit trail.

A suspect often knows a fact it must not say yet. Hobbs knows Clara had the letter opener, but saying so names the culprit before the player has found the evidence. Clara knows she was in the study, and her planned lie hides it until the diary page is shown. "Knows" and "may say" are two different questions with two different answers.

## Decision

**Identity.** Every check carries an `AuthContext`: `actor_id`, `actor_type`, `game_id`, `case_version`, and `state_version`. `case_version` is the SHA-256 of the case's canonical JSON (sorted keys, no whitespace). For a suspect turn, `state_version` is the number of committed turns in that suspect's thread.

**Grants.** `grants_for(case)` derives one `KnowledgeGrant(suspect, fact, can_know, can_disclose_when)` per suspect in a fact's `known_by`. `can_disclose_when` is a named rule, never an expression string:

- `always`: the fact is neither the suspect's secret nor the culprit's.
- `after_clue(<ids>)`: the fact is the suspect's secret or the culprit's, and these clues reveal it. Showing any one of them makes it disclosable.
- `never_before_reveal`: the fact is a guarded secret that no clue reveals.

A fact outside `known_by` has no grant. Planned lies are not grants. A lie is authorized by the `tell_lie` rule below, from the lie's owner and the ledger.

**Policy.** `authorize(subject, action, resource, context) -> Decision` returns `allow`, `deny`, or `transition_required`, with a `reason_code` and `POLICY_VERSION` (`p3-2.1`). It applies these checks in order:

1. A resource from another case version is denied with `stale_case`.
2. A context whose `state_version` differs from the subject's is denied with `stale_state`. `commit` authorizes at the version the view was built at. Within one process the per-suspect lock already serializes turns, so this check cannot fail there. Across processes it does not yet close the race: two `Interrogation`s on the same game can each commit turn 1, and one turn is lost. P3-5's transactional commit compares the stored `state_version` inside the transaction that writes the turn; until then this is a known gap.
3. An action not in the table for the actor type is denied with `unknown_action`.
4. A Truth-layer resource for anyone but the game master is denied with `truth_layer`.

Then the table decides. The code's `POLICY` dict is the source, and a test fails when this table and the code disagree.

| Actor | Action | Allowed when |
|---|---|---|
| `suspect` | `know_fact` | a grant names this suspect and fact |
| `suspect` | `disclose_fact` | known, and the grant's disclosure rule holds: always, after one of its clues is shown, or never before the reveal |
| `suspect` | `tell_lie` | the lie is the suspect's own and is not spent |
| `game_master` | `read_truth` | verification, scoring, and the reveal |
| `game_master` | `commit_turn` | the version the turn was authorized at |

Reason codes: `granted`, `not_granted`, `always`, `clue_shown`, `needs_clue` (`transition_required`), `never_before_reveal`, `planned_lie`, `lie_spent`, `not_owner`, `server_rule`, `stale_case`, `stale_state`, `unknown_action`, and `truth_layer`. A lie is spent when a shown clue reveals its hidden fact or the ledger marks it exposed or admitted.

**The view.** The turn's `retrieve` node builds a `SuspectView` only through `authorize`. It holds a public projection of the case (title, summary, people, places, items, and hours), the suspect's stateable facts, its own secrets split into hidden and proven, its planned lies with whether each is spent, the clues shown to it, and the history window. A culprit secret the suspect knows but may not disclose stays out of the view entirely. `suspect_brief` takes the view, not the `Case`. The view's types cannot reach `Case`, `Crime`, `culprit`, `crime`, or `solution_chain`, and a test walks the types to prove it. The rendered brief is byte-identical to the brief before this change for 115 recorded states across the three cases.

**Permitted claims.** A `permitted_claims` node runs between `retrieve` and `generate`. It records the fact ids and lie ids the view permits. `verify` turns any `KNOWN_TRUE`, `ADMISSION`, or `PLANNED_LIE` verdict whose reference is outside that set into a block. The verifier's rules already agree with the policy, so this bound fires only when one of them drifts.

**Canary.** `canary(case)` is `MENDACIA-CANARY-<case_version[:12]>`. It belongs to the Truth layer and is never written into a prompt. `verify` blocks any draft that contains it, ignoring case. The fallback logs `unverified` with the word `canary`, not the token. `log_decisions` refuses any row whose values contain the canary prefix. The canary derives from `case_version`, which a client may see, so a player can type it. A typed canary makes the turn fall back, which costs the player nothing. The canary's job is to show when Truth-layer text reaches an output, not to be a secret.

**Narration.** A draft with more than one paragraph is treated as unchecked and rewritten. The baseline attack run found a reply whose first paragraph was the model's stage reasoning ("...but she must not reveal the letter opener"). The extractor found no claim in it, so the verifier passed it. This is a cheap text-shape guard, not a boundary. The view is the boundary: a model cannot narrate a secret its prompt never held.

**Audit.** `security_events` stores the columns in `docs/spec.md` §6.6. Each turn records a `retrieve` row with the policy decision counts, one `verify` row per draft, and a `commit_turn` row. `decision_trace` lists steps with an outcome and milliseconds. Rows hold counts and reason codes, never fact text, fact ids, prompts, or the player's message. The nodes buffer their rows in the turn's state, and `commit` writes them in one transaction before it acts on its own decision, so a stale commit is recorded before it raises. Separate transactions per node cost about 14 ms a turn; one costs about 3 ms. A turn that crashes before `commit` loses its rows, and it also commits no state (ADR 005).

**Prompt versions.** The suspect, rewrite, and extraction prompts live in `agents/prompts/*.txt` with a `prompt_version` header. `app.llm` records `prompt_version` on every `llm_calls` row. The version is not part of the replay key, so a prompt change still re-records through its text, as ADR 003 says.

**Agent inventory.** `agents/registry.py` declares each agent's model role, purposes, tools, readable layers, sensitivity, modules, and verifier. `make agent-inventory` scans the backend's AST and writes `reports/agent-inventory.json`. It fails when a model call belongs to no agent, when a call uses a purpose or role its manifest does not list, when a module reads `culprit`, `crime`, or `solution_chain` without the Truth layer in its manifest, or when a Truth reader has no verifier.

**Regression.** `make security-regress` replays `evals/attacks/baseline.yaml` against the suspect graph. The file holds 12 attacks: direct injection, role spoofing, spoiler extraction, ledger replay, and canary probing. It also holds 12 normal confrontations. A leak is a released culprit secret or culprit-killed claim, a spent lie told again, system-prompt text, narration, or the canary in a reply or an audit row. A normal confrontation fails when it is screened or answered with the fallback.

## Rejected

**A filtered `Case` copy as the view.** A `Case` with fields blanked still has the fields, so code could read an empty `culprit` and not notice. A separate type without the fields makes the mistake a type error.

**Expression strings for disclosure rules.** A rule such as `"shown('diary_page') and turn > 2"` needs a parser and an evaluator, and anything that can write a case could write code. Named rules are a closed set the policy matches on.

**One `security_events` row per fact decision.** That is one row per fact per turn, and each row would need a fact id. Per-turn rows with counts by reason code keep the trail useful and keep Truth-layer ids out of logs.

## Consequences

- The default for disclosure remains "only a presented clue that reveals the fact" (`docs/plan.md` Open decision 2). A new trigger is a new named rule and a new `POLICY_VERSION`.
- A secret whose owner is missing from its `known_by` gets no grant, so it drops out of the suspect's view instead of appearing under its secrets. The three hand-written cases do not have one. P4-1's generator should reject such a case, or the schema should require owners in `known_by`.
- `model_version` and `replay_ref` stay null in `security_events` until P3-5 threads the resolved model and the replay key from `app.llm` into the turn.
- Extraction can still miss a claim. The view keeps a culprit secret out of every innocent suspect's prompt, so such a miss can only repeat what the suspect was allowed to know.
- P3-5 builds the HTTP session on `AuthContext`, the Tool Broker on `authorize`, and the transactional commit on `state_version`.
