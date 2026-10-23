# 016. Bound proactive agents by declared moves and a solver-backed belief engine

## Status

Proposed. It takes effect when stage B1 of `docs/roadmap.md` starts. Stage E1 adds its own ADR for the `planned_moves` schema change.

## Context

The roadmap adds agents that act without the player asking them something: a rival detective in the daily case (stage B1), a detective team that hunts the player in killer mode (stage E), and suspects who hide documents, collude, and approach the player (stage E1). Each of them changes game state, so each of them can break a promise the MVP makes. Every case has exactly one culprit and the evidence proves it. Every player of a daily case gets the same facts. No agent reads the Truth layer.

A detective has to decide what to investigate next, notice contradictions, and know when the evidence is enough. A language model can attempt all three, but its choices are not reproducible, every step costs tokens, and it gives no reason a debrief can show. `engine/rules.lp` already answers "which culprits are still possible given these pinned facts" for the solver checks (ADR 001).

## Decision

**Reasoning runs on the solver.** A pure `belief` module runs `rules.lp` over the facts one agent has found. It never reads the Truth layer, and the agent manifest grants it the player layer only. It returns three things.

- `candidates`: the culprits still possible, each with its number of models.
- `best_query`: among the questions the agent can ask (where a person was in a slot, what a document says), the one whose possible answers split the candidates most evenly. The solve is projected on the culprit and the query's answer, so it counts distinct pairs, not every world. The agent knows the question. The game engine answers it the way it answers a player.
- `conflicts`: claims that have no model together with the facts the agent pinned.

Ties break on a seed derived from `case_version`, so every player of a daily case meets the same agent. Models only phrase an agent's lines and extract claims from a player's answers.

**Suspects act only through declared moves.** A case may list `planned_moves`. A move names its actor, a trigger, an effect (`hide_doc` or `add_clue`), and its line. An effect changes which clues a player can reach and never a fact, so the Truth layer and the proofs over facts stay as they are. A move that hides a `solution_chain` clue adds a clue that reveals the same facts, and the added clue counts as a chain clue in `rule_accusation`.

`check_case` gains a moves check. For each subset of a case's moves, it assumes those moves fired before the player reached anything they hide. It then reruns sufficiency on the chain clues still reachable, through `compile_case(drop_clues=...)`: the clues the subset hides are dropped, and so are the clues that only moves outside the subset would add. A case with 3 moves runs 8 subsets.

Collusion is a declared `planned_lie` that becomes available after a move fires, so the verifier rules in ADR 004 judge it unchanged.

**Player actions trigger agents, not time.** A player action commits an outbox row in the transaction that commits its turn. Trigger rules, which call no model, read the outbox and decide which agent wakes. A Game Master handler applies a move's effect, and a model never writes state. Official play never fires a move on wall-clock time, so two players who take the same actions see the same world.

**Proactive speech is a turn.** A line an agent says without being asked runs the nine-step turn in `docs/spec.md` §5 and is released only after verification. It costs the player no question. Each game has a wake budget and a token budget, and a circuit breaker stops proactive turns when either runs out.

## Rejected

**A runtime action validator.** A model would propose any action and the solver would decide at play time whether the case stays solvable. That puts the solver on the hot path, gives different players different worlds, and leaves nothing to review before release. Declared moves move the proof offline, beside the other checks.

**Model-chosen investigation strategy.** A model that picks the next suspect to question is not reproducible across runs or players, spends tokens on every step, and gives the debrief no reason it can trust. `belief` makes the same choice from the same facts every time, and every step has a reason: its query split the candidates.

**Agents that run in the background.** An agent that polls the game on a timer spends tokens while nothing happens, and makes the daily case depend on when a player plays. Outbox triggers wake an agent only when a player action changes something it watches.

**A message queue first.** RabbitMQ or Kafka between the trigger and the agents adds a service before a measurement asks for one. The Postgres outbox from P3-5 carries the triggers until it misses its queue SLA (`docs/roadmap.md` §6.3).

## Consequences

- `backend/engine/belief.py` lands with stage B1 and is tested on the three hand-written cases. Once P5-1's `DetectiveBot` exists, it can run `belief` as a deterministic baseline beside its model strategy.
- Stage E1 adds `planned_moves` to the `Case` schema. Per `CLAUDE.md`, that PR updates the hand-written cases, the solver, and the tests together and adds its own ADR.
- `make check-case` prints a moves line for cases that have moves, and fails a case whose moves can leave it unsolvable.
- The agent inventory from P3-2 gains entries for the rival detective, the killer-mode detectives, and the trigger rules, each limited to the player layer.
- Proactive turns write `llm_calls` rows tagged with their purpose, so cost per game splits into answers and proactive turns.
